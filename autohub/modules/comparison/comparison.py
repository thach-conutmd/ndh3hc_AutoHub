"""Parameter-map comparison of Master, target and optional base exports."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from autohub.core.webflow_options import resolve_option_values

from .matching import OPTION_PATHS
from .xml_parser import ParameterValue


class Status(str, Enum):
    MATCH = "MATCH"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    MISSING_IN_MASTER = "MISSING_IN_MASTER"
    MISSING_IN_WEBFLOW = "MISSING_IN_WEBFLOW"
    MATCHES_MASTER = "MATCHES_MASTER"
    MATCHES_BASE = "MATCHES_BASE"
    MATCHES_BOTH = "MATCHES_BOTH"
    MATCHES_NEITHER = "MATCHES_NEITHER"


@dataclass(frozen=True)
class ComparisonRow:
    parameter: str
    master: ParameterValue
    target: ParameterValue
    status: Status
    base: ParameterValue = None

    @property
    def deviation(self) -> bool:
        return self.status not in (Status.MATCH, Status.MATCHES_MASTER, Status.MATCHES_BOTH)


def _present(value: ParameterValue) -> bool:
    return value not in (None, "", (), "---")


def _equal(path: str, reference: ParameterValue, target: ParameterValue) -> bool:
    if not _present(reference) or not _present(target):
        return False
    if path == "ECU/TP_Level" and isinstance(reference, str) and isinstance(target, str):
        return reference.upper().removeprefix("TP") == target.upper().removeprefix("TP")
    if isinstance(reference, tuple) and isinstance(target, tuple):
        if path in OPTION_PATHS:
            try:
                return resolve_option_values(OPTION_PATHS[path], "|".join(reference), target) == set(target)
            except ValueError:
                return False
        return set(reference) == set(target)
    return reference == target


def compare_parameters(
    master: Mapping[str, ParameterValue],
    target: Mapping[str, ParameterValue],
    base: Mapping[str, ParameterValue] | None = None,
) -> list[ComparisonRow]:
    """Blank/absent target values are never a match, even if the references are also blank."""
    paths = master.keys() | target.keys() | (base.keys() if base is not None else set())
    rows = []
    for path in sorted(paths):
        master_value, target_value = master.get(path), target.get(path)
        base_value = base.get(path) if base is not None else None
        master_match = _equal(path, master_value, target_value)
        if base is not None:
            base_match = _equal(path, base_value, target_value)
            status = (
                Status.MATCHES_BOTH if master_match and base_match
                else Status.MATCHES_MASTER if master_match
                else Status.MATCHES_BASE if base_match
                else Status.MATCHES_NEITHER
            )
        elif not _present(target_value):
            status = Status.MISSING_IN_WEBFLOW
        elif not _present(master_value):
            status = Status.MISSING_IN_MASTER
        else:
            status = Status.MATCH if master_match else Status.VALUE_MISMATCH
        rows.append(ComparisonRow(path, master_value, target_value, status, base_value))
    return rows
