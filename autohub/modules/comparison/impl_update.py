"""Builds the Master Sheet IMPL updates from stored comparison results and applies them through a sheet port."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from urllib.parse import unquote

from autohub.core.impl_update import ImplOutcome, ImplUpdate, ImplValueWriter
from autohub.core.variant_schema import VARIANT_FIELD_LABELS
from autohub.core.webflow_fields import HARDWARE_FIELDS

from .comparison import ComparisonRow
from .matching import _HARDWARE_NAMES

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


def _value(target: object, column: str) -> str | bool | None:
    if isinstance(target, tuple):
        text = "|".join(str(item) for item in target)
    elif isinstance(target, str):
        text = target.strip()
    else:
        return None
    if not text or text == "---":
        return None
    if column in _CHECKBOX_COLUMNS and text.casefold() in ("true", "false"):
        return text.casefold() == "true"
    return text


def build_impl_update(software: str, rows: Iterable[ComparisonRow]) -> ImplUpdate:
    """Target values for Master parameters only; a missing Target value is never invented."""
    values: dict[str, str | bool] = {}
    for row in rows:
        column = impl_column(row.parameter)
        value = _value(row.target, column) if column else None
        if value is not None:
            values[column] = value
    return ImplUpdate(software, values)


class MasterImplUpdater:
    def __init__(self, master_sheet_factory: Callable[[str], object], session_factory: Callable[[], AbstractContextManager]):
        self._factory = master_sheet_factory
        self._session = session_factory

    def update(self, path: str, updates: dict[str, ImplUpdate]) -> dict[str, ImplOutcome]:
        with self._session():
            sheet = self._factory(path)
            try:
                sheet.open()
                if not isinstance(sheet, ImplValueWriter):
                    raise ValueError("This Master Sheet layout cannot update IMPL rows.")
                return sheet.write_impl_values(updates)
            finally:
                sheet.close()
