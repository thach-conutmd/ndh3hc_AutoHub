"""Builds the Master Sheet IMPL updates from stored comparison results and applies them through a sheet port."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import unquote

from autohub.core.impl_update import ImplOutcome, ImplUpdate, ImplValueWriter
from autohub.core.impl_values import CHECKBOX, TP_LEVEL, option_kind
from autohub.core.ports import SheetSession, VariantReader
from autohub.core.variant_schema import VARIANT_FIELD_LABELS
from autohub.core.webflow_fields import HARDWARE_FIELDS

from .comparison import ComparisonRow
from .matching import _HARDWARE_NAMES, OPTION_PATHS

_COLUMNS = {
    "Job Information/ECUGeneration": "Q", "Job Information/Brand": "R", "Job Information/ECUType": "S",
    "General/DeliveryType_CF": "T", "General/ReleaseClass": "U", "General/ReleaseScope": "V",
    "General/Limitations": "W", "Check/Safety_Monitoring_SW_by_RB": "X",
    "Check/SafetyCalibrationResponsibility": "Y", "Check/CalibrationResponsibility": "Z",
    "Check/DataIntegrationResponsibility": "AA",
    "ECU/IndiSpec": "BC", "ECU/FamilyName": "BD", "ECU/FSWID_ProjectVersion": "BE",
    "ECU/FSWID_ProgramVersion": "BF", "ECU/TP_Level": "BG",
    "Customer/ECU_default_ID": "BH", "Customer/ECU_rewriting_ID": "CM", "Customer/ECU_progam_ID": "CL",
    "Customer/SecurityCoefficient": "CN", "Customer/SW_Version": "CQ", "Customer/Component_ID": "CR",
    **{f"General/{_HARDWARE_NAMES[key]}": column for column, key, _, _ in HARDWARE_FIELDS},
}
_CHECKBOX_COLUMNS = {"X", "Y", "Z", "AA"}
_UNMAPPED_PREFIX = "Master/"


def impl_column(parameter: str) -> str | None:
    """Sheet column of a Master parameter; None when it has no known column (it is then never written)."""
    if parameter in _COLUMNS:
        return _COLUMNS[parameter]
    if parameter.startswith(_UNMAPPED_PREFIX):
        column = unquote(parameter[len(_UNMAPPED_PREFIX):]).split(" ", 1)[0]
        return column if column in VARIANT_FIELD_LABELS else None
    return None


def impl_kind(parameter: str, column: str) -> str:
    """How a Target value must be converted to the Master Sheet's own representation (explicit, per parameter)."""
    if column in _CHECKBOX_COLUMNS:
        return CHECKBOX
    if parameter == "ECU/TP_Level":
        return TP_LEVEL
    if parameter in OPTION_PATHS:
        return option_kind(OPTION_PATHS[parameter])
    return ""


def _value(target: object) -> str | None:
    if isinstance(target, tuple):
        text = "|".join(str(item) for item in target)
    elif isinstance(target, str):
        text = target.strip()
    else:
        return None
    return None if not text or text == "---" else text


def build_impl_update(software: str, rows: Iterable[ComparisonRow]) -> ImplUpdate:
    """Raw Target values for Master parameters only; a missing Target value is never invented."""
    values: dict[str, str] = {}
    kinds: dict[str, str] = {}
    for row in rows:
        column = impl_column(row.parameter)
        value = _value(row.target) if column else None
        if value is not None:
            values[column] = value
            kinds[column] = impl_kind(row.parameter, column)
    return ImplUpdate(software, values, kinds)


class ImplSheet(SheetSession, VariantReader, ImplValueWriter, Protocol):
    pass


@dataclass(frozen=True)
class ImplRefresh:
    outcomes: dict[str, ImplOutcome]
    variants: list[dict]


class MasterImplUpdater:
    def __init__(self, master_sheet_factory: Callable[[str], ImplSheet], session_factory: Callable[[], AbstractContextManager]):
        self._factory = master_sheet_factory
        self._session = session_factory

    def update(self, path: str, updates: dict[str, ImplUpdate]) -> ImplRefresh:
        with self._session():
            sheet = self._factory(path)
            try:
                sheet.open()
                if not isinstance(sheet, ImplValueWriter):
                    raise ValueError("This Master Sheet layout cannot update IMPL rows.")
                # The sheet writer saves before returning; read formula-backed state only afterwards.
                outcomes = sheet.write_impl_values(updates)
                parts = {part for part, outcome in outcomes.items() if outcome.written}
                variants = [
                    variant for variant in sheet.load_webflow_variants()
                    if variant["part_number"] in parts
                ] if parts else []
                return ImplRefresh(outcomes, variants)
            finally:
                sheet.close()
