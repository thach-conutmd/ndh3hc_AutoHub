"""Parameter-map comparison of Master, target and optional base exports."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from autohub.core.webflow_options import resolve_option_values
from autohub.core.settings_keys import DEFAULT_XML_COMPARISON_EXCLUSIONS

from .matching import OPTION_PATHS
from .xml_parser import ParameterValue, comparison_parameters


class Status(str, Enum):
    MATCH = "MATCH"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    MISSING_IN_MASTER = "MISSING_IN_MASTER"
    MISSING_IN_WEBFLOW = "MISSING_IN_WEBFLOW"
    MATCHES_MASTER = "MATCHES_MASTER"
    MATCHES_BASE = "MATCHES_BASE"
    MATCHES_BOTH = "MATCHES_BOTH"
    MATCHES_NEITHER = "MATCHES_NEITHER"
    MISSING_IN_BASE = "MISSING_IN_BASE"
    MISSING_IN_TARGET = "MISSING_IN_TARGET"


@dataclass(frozen=True)
class ComparisonRow:
    parameter: str
    master: ParameterValue
    target: ParameterValue
    status: Status
    base: ParameterValue = None
    targets: tuple[ParameterValue, ...] = ()
    target_statuses: tuple[Status, ...] = ()

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
    *, exclusions: Sequence[str] = DEFAULT_XML_COMPARISON_EXCLUSIONS,
) -> list[ComparisonRow]:
    """Blank/absent target values are never a match, even if the references are also blank."""
    paths = comparison_parameters(master, exclusions).keys()
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


def compare_xml_parameters(
    base: Mapping[str, ParameterValue], target: Mapping[str, ParameterValue],
    *, exclusions: Sequence[str] = DEFAULT_XML_COMPARISON_EXCLUSIONS,
) -> list[ComparisonRow]:
    """Compare every XML path, using the same value semantics as Master comparison."""
    base, target = comparison_parameters(base, exclusions), comparison_parameters(target, exclusions)
    rows = []
    for path in sorted(base.keys() | target.keys()):
        base_value, target_value = base.get(path), target.get(path)
        if path not in base:
            status = Status.MISSING_IN_BASE
        elif path not in target or not _present(target_value):
            status = Status.MISSING_IN_TARGET
        elif not _present(base_value):
            status = Status.MISSING_IN_BASE
        else:
            status = Status.MATCH if _equal(path, base_value, target_value) else Status.VALUE_MISMATCH
        rows.append(ComparisonRow(path, None, target_value, status, base_value))
    return rows


def compare_xml_datasets(
    base: Mapping[str, ParameterValue], targets: Iterable[Mapping[str, ParameterValue]],
    on_target: Callable[[int], None] = lambda _: None,
    *, exclusions: Sequence[str] = DEFAULT_XML_COMPARISON_EXCLUSIONS,
) -> list[ComparisonRow]:
    """Align the union of paths, retaining each target's calculated two-way status."""
    base = comparison_parameters(base, exclusions)
    compared = []
    for index, target in enumerate(targets):
        compared.append({row.parameter: row for row in compare_xml_parameters(base, target, exclusions=exclusions)})
        on_target(index)
    if not compared:
        raise ValueError("Select at least one Target XML dataset.")
    paths = base.keys() | {path for result in compared for path in result}
    rows = []
    for path in sorted(paths):
        statuses = tuple(
            result[path].status if path in result else Status.MISSING_IN_TARGET
            for result in compared
        )
        values = tuple(result[path].target if path in result else None for result in compared)
        status = statuses[0] if len(set(statuses)) == 1 else Status.VALUE_MISMATCH
        rows.append(ComparisonRow(
            path, None, values[0], status, base.get(path), values, statuses,
        ))
    return rows
