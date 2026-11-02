"""Turns a Master Sheet request row into the variant dict the WebFlow automation expects (pure)."""
from __future__ import annotations

from typing import Any, Mapping

from autohub.core.normalizers import clean_text, parse_event, project_event
from autohub.core.variant_schema import VARIANT_FIELD_LABELS
from autohub.core.webflow_fields import HARDWARE_FIELDS
from autohub.core.webflow_options import GENERAL_OPTION_FIELDS, normalize_option_value

#: Sheet columns a request row is read from to build a WebFlow variant.
WEBFLOW_SOURCE_COLUMNS = tuple(dict.fromkeys(("C", "O", *VARIANT_FIELD_LABELS, "CR")))

_GENERAL_COLUMNS = {
    "delivery_type": "T", "release_class": "U", "release_scope": "V", "limitations": "W",
    "safety_monitoring": "X", "safety_calibration": "Y", "calibration": "Z", "data_integration": "AA",
}
_ECU_COLUMNS = {
    "indi_spec": "BC", "family_name": "BD", "project_version": "BE",
    "program_version": "BF", "tp_level": "BG",
}
_CUSTOMER_COLUMNS = {
    "ecu_default_id": "BH", "ecu_program_id": "CL", "ecu_rewriting_id": "CM",
    "security_coefficient": "CN", "sw_version": "CQ", "component_id": "CR",
}


def _text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return clean_text(value)


def _checkbox(value: Any, column: str, part_number: str) -> bool:
    text = _text(value).casefold()
    if not text:
        return False
    if text in ("true", "yes", "1", "x"):
        return True
    if text in ("false", "no", "0"):
        return False
    raise ValueError(f"{part_number}: invalid checkbox value {value!r} in Master Sheet column {column}.")


def webflow_variant_from_row(part_number: str, row: Mapping[str, Any]) -> dict:
    general: dict[str, Any] = {key: _text(row.get(column)) for key, column in _GENERAL_COLUMNS.items()}
    for key in ("safety_monitoring", "safety_calibration", "calibration", "data_integration"):
        general[key] = _checkbox(row.get(_GENERAL_COLUMNS[key]), _GENERAL_COLUMNS[key], part_number)
    mapped = {
        "C", "H", "J", "Q", "R", "S", "BI",
        *_GENERAL_COLUMNS.values(), *_ECU_COLUMNS.values(), *_CUSTOMER_COLUMNS.values(),
        *(field[0] for field in HARDWARE_FIELDS),
    }
    project, event_name = project_event(row.get("H"))
    return {
        "part_number": part_number,
        "ecu_generation": _text(row.get("Q")),
        "brand": _text(row.get("R")),
        "ecu_type": _text(row.get("S")),
        "event": parse_event(row.get("H")),
        "project": project,
        "event_name": event_name,
        "created_at": row.get("C"),
        "comparison_result": _text(row.get("O")),
        "general": general,
        "hardware": {
            key: normalize_option_value(key, row.get(column)) if key in GENERAL_OPTION_FIELDS else _text(row.get(column))
            for column, key, _, _ in HARDWARE_FIELDS
        },
        "ecu": {key: _text(row.get(column)) for key, column in _ECU_COLUMNS.items()},
        "customer": {key: _text(row.get(column)) for key, column in _CUSTOMER_COLUMNS.items()},
        "unmapped_fields": {
            f"{column} ({VARIANT_FIELD_LABELS.get(column, column)})": _text(value)
            for column, value in row.items()
            if column in VARIANT_FIELD_LABELS and column not in mapped and _text(value)
        },
    }
