"""Layout of the Mx17 (MED17) master sheet "Honda_GDI_container_release_info" and how it maps to the Home table.

Pure data and conversions, no Excel. The Home table is keyed by the MG1 Master Sheet column letters
(`variant_schema`); here each of those keys is tied to a column of the Mx17 main sheet (one flat row per
variant) and of the per-project "Info" sheets (the webFLOW job fields, one row per variant).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping

from autohub.core.normalizers import clean_text, normalize_model_year
from autohub.core.webflow_defaults import WEBFLOW_DEFAULTS

MAIN_SHEET_NAME = "ECU Container Release Honda GDI"
MG1_SHEET_NAME = "Master sheet"
FIRST_DATA_ROW = 7  # rows 1-5 are the header, row 6 is the "Example" row
LAST_DATA_COLUMN = "DA"
PART_NUMBER_COLUMN = "W"  # Customer order number: the variant's part number
CONTAINER_CHECKSUM_COLUMN = "Z"

INFO_HEADER_ROW = 4
INFO_TITLE_ROW = 5
INFO_FIRST_DATA_ROW = 6
INFO_LAST_COLUMN = "AK"
INFO_MARKER_COLUMN = "B"  # "[General] Delivery Type" in the header, a value on every variant row
INFO_MARKER_TEXT = "Delivery Type"
INFO_TEMPLATE_SHEET = "Mx17_5xFx_Info"
INFO_SHEET_SUFFIX = "_Info"
_SHEET_NAME_LIMIT = 31

#: Home table key -> Mx17 main sheet column.
MAIN_COLUMNS: dict[str, str] = {
    "J": "W",
    "H": "P",
    "S": "E",
    "AP": "E",
    "AT": "F",
    "AF": "G",
    "AJ": "H",
    "AG": "D",
    "AI": "J",
    "AH": "N",
    "BC": "Q",
    "AN": "U",
    "AO": "V",
    "AQ": "W",
    "AX": "X",
    "AW": "Y",
    "BI": "AC",
    "CS": "AD",
    "CT": "AE",
    "CU": "AF",
    "CV": "AG",
    "CX": "AI",
    "CY": "AJ",
    "CZ": "AK",
}

#: Home table key -> Info sheet column. The Info sheet's "ECU hardware name" holds the Bosch HW number here.
INFO_COLUMNS: dict[str, str] = {
    "J": "A",
    "T": "B",
    "U": "C",
    "V": "D",
    "W": "E",
    "X": "F",
    "Y": "G",
    "Z": "H",
    "AA": "I",
    "AB": "J",
    "AG": "K",
    "AC": "L",
    "AH": "M",
    "AD": "N",
    "AI": "O",
    "AE": "P",
    "AJ": "Q",
    "AF": "R",
    "AK": "S",
    "AL": "T",
    "AM": "U",
    "AN": "V",
    "AT": "W",
    "AV": "Y",
    "AY": "Z",
    "BC": "AD",
    "BD": "AE",
    "BE": "AF",
    "BF": "AG",
    "BH": "AH",
    "CL": "AI",
    "CM": "AJ",
    "CN": "AK",
}

_MAIN_CONSTANTS = {"C": "HONDA GDI"}
_INFO_CONSTANTS = {"X": 1, "AA": "Customer requirement"}  # "Number of Variants", "Change Reason"
_PROGRAM_ID_COLUMNS = ("BR", "BS", "BT", "BU", "BV", "BW", "BX", "BY", "BZ", "CA", "CB", "CC", "CD", "CE")
_SECURITY_PARTS = ("CW", "CX", "CY")  # the security coefficient as three byte-swapped 16-bit words


def needs_info_row(changed: Mapping[str, Any]) -> bool:
    """True when an edit touches a field that only exists on the Info sheets."""
    return any(key in INFO_COLUMNS and key not in MAIN_COLUMNS for key in changed)


def unmapped_keys(home: Mapping[str, Any]) -> list[str]:
    """Home keys with a value that neither sheet has a column for (they are not written)."""
    return [
        key for key, value in home.items()
        if not key.startswith("_") and key not in MAIN_COLUMNS and key not in INFO_COLUMNS and value not in (None, "")
    ]


def _text(value: Any) -> Any:
    """Cell value as the Home table holds it: whole numbers without ".0", dates and blanks untouched."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return clean_text(value) if isinstance(value, str) else value


def _model_year_label(year: str) -> str:
    year = normalize_model_year(year)
    return f"MY{year[-2:]}" if re.fullmatch(r"\d{4}", year) else year


def is_mx17_sheet_names(sheet_names: list[str]) -> bool:
    """The Mx17 workbook has the flat main sheet and no MG1 "Master sheet"."""
    return MAIN_SHEET_NAME in sheet_names and MG1_SHEET_NAME not in sheet_names


def home_from_main(values: Mapping[str, Any]) -> dict:
    """Home table values from a main sheet row given as {column letter: value}."""
    home = {key: _text(values.get(column)) for key, column in MAIN_COLUMNS.items()}
    home["AF"] = normalize_model_year(home["AF"])
    ecu_type = clean_text(values.get("E"))
    home["Q"] = ecu_type.split(".")[0] if ecu_type else ""
    home["R"] = "Honda"
    return {key: value for key, value in home.items() if value is not None}


def home_overlay_from_info(values: Mapping[str, Any]) -> dict:
    """Home table values an Info sheet row holds (only the non-blank ones, they win over the main sheet)."""
    home = {key: _text(values.get(column)) for key, column in INFO_COLUMNS.items()}
    if home.get("AF") not in (None, ""):
        home["AF"] = normalize_model_year(home["AF"])
    return {key: value for key, value in home.items() if value not in (None, "")}


def main_values_from_home(home: Mapping[str, Any], keep_blank: bool = False) -> dict:
    """Main sheet {column: value} for a Home row; blanks are left out (unless `keep_blank`) so cells are not erased."""
    values: dict[str, Any] = {}
    for key, column in MAIN_COLUMNS.items():
        if key not in home:
            continue
        value = home[key]
        if value in (None, ""):
            if keep_blank:
                values[column] = None
        else:
            values[column] = _model_year_label(value) if key == "AF" else value
    return values


def _text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # COM returns 159 as 159.0
    return "" if value is None else str(value).strip()


def changed_home_values(current: Mapping[str, Any], edited: Mapping[str, Any]) -> dict:
    """The Home keys of `edited` whose text differs from `current`.

    Several Home keys share one sheet column (e.g. S and AP); writing only what changed stops an untouched key
    from overwriting the edit of its twin."""
    return {
        key: value for key, value in edited.items() if not key.startswith("_") and _text(value) != _text(current.get(key))
    }


def new_main_values(home: Mapping[str, Any], created: datetime | None = None) -> dict:
    """Everything a brand-new main sheet row needs: mapped values, date, constants and the derived columns."""
    values = {**_MAIN_CONSTANTS, "B": created or datetime.now(), **main_values_from_home(home)}
    program_id = clean_text(home.get("CV"))
    for column, character in zip(_PROGRAM_ID_COLUMNS, program_id):
        values[column] = character
    security = clean_text(home.get("CN"))
    if re.fullmatch(r"[0-9A-Fa-f]{12}", security):
        for index, column in enumerate(_SECURITY_PARTS):
            word = security[index * 4 : index * 4 + 4]
            values[column] = (word[2:] + word[:2]).upper()  # SeccCoeff3_Boot swaps the bytes back
    return values


def info_values_from_home(home: Mapping[str, Any], defaults_for_blanks: bool = False, keep_blank: bool = False) -> dict:
    """Info sheet {column: value} for a Home row; with `defaults_for_blanks` the usual job defaults fill gaps."""
    merged = {**_job_defaults(), **{k: v for k, v in home.items() if v not in (None, "")}} if defaults_for_blanks else home
    values = {
        column: (merged[key] if merged[key] != "" else None)
        for key, column in INFO_COLUMNS.items()
        if key in merged and (keep_blank or merged[key] not in (None, ""))
    }
    if defaults_for_blanks:
        for column, value in _INFO_CONSTANTS.items():
            values.setdefault(column, value)
    return values


def _job_defaults() -> dict:
    general = WEBFLOW_DEFAULTS.general()
    yes_no = lambda flag: "Yes" if flag else "No"  # noqa: E731
    return {
        "T": general["delivery_type"],
        "U": general["release_class"],
        "V": general["release_scope"],
        "W": general["limitations"],
        "X": yes_no(general["safety_monitoring"]),
        "Y": yes_no(general["safety_calibration"]),
        "Z": yes_no(general["calibration"]),
        "AA": yes_no(general["data_integration"]),
    }


def info_sheet_name(project: str) -> str:
    """Name of the Info sheet created for a project, e.g. "5BFT" -> "5BFT_Info" (Excel's naming limits applied)."""
    base = re.sub(r"[\[\]:*?/\\]", "", clean_text(project)) or "New"
    return base[: _SHEET_NAME_LIMIT - len(INFO_SHEET_SUFFIX)] + INFO_SHEET_SUFFIX
