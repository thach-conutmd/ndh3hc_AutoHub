"""Master Sheet format check used before loading variants at startup (no Excel)."""
import io
import sys
import types

import openpyxl
import pytest

from autohub.core.variant_schema import VARIANT_FIELD_LABELS
from autohub.services.MasterSheet import mx17_layout

try:
    import win32com.client  # noqa: F401
except ImportError:  # Windows-only; the format check never touches Excel
    _win32com = types.ModuleType("win32com")
    _win32com.client = types.ModuleType("win32com.client")
    sys.modules.setdefault("win32com", _win32com)
    sys.modules.setdefault("win32com.client", _win32com.client)

from autohub.services.MasterSheet.master_sheet_factory import master_sheet_format_error  # noqa: E402

MX17 = "datas/mastersheet/Honda_GDI_container_release_info_latest.xlsx"
MG1 = "datas/mastersheet/Honda_6SAY_Container_MasterSheet_r00.xlsx"


def _workbook(path, *sheets):
    book = openpyxl.Workbook()
    book.active.title = sheets[0]
    for name in sheets[1:]:
        book.create_sheet(name)
    if "Master sheet" in sheets:
        sheet = book["Master sheet"]
        for column, label in VARIANT_FIELD_LABELS.items():
            sheet[f"{column}7"] = label
        sheet["D7"] = "Requirement or Implementation?"
        sheet["J7"] = "DWG NO."
    if mx17_layout.MAIN_SHEET_NAME in sheets:
        sheet = book[mx17_layout.MAIN_SHEET_NAME]
        for key, column in mx17_layout.MAIN_COLUMNS.items():
            sheet[f"{column}5"] = VARIANT_FIELD_LABELS[key]
        for column, label in {"E": "ECU", "P": "Purpose", "W": "Customer order number", "X": "BOSCH SW No."}.items():
            sheet[f"{column}5"] = label
    book.save(path)
    return path


@pytest.mark.parametrize("path", [MG1, MX17])
def test_sample_master_sheets_are_valid(path):
    assert master_sheet_format_error(path) == ""


def test_layout_sheets_decide_validity(tmp_path):
    assert master_sheet_format_error(str(_workbook(tmp_path / "mg1.xlsx", "Cover", "Master sheet"))) == ""
    assert master_sheet_format_error(str(_workbook(tmp_path / "mx.xlsx", "ECU Container Release Honda GDI"))) == ""
    error = master_sheet_format_error(str(_workbook(tmp_path / "other.xlsx", "Sheet1")))
    assert "neither the 'Master sheet' nor the 'ECU Container Release Honda GDI' sheet" in error


def test_missing_wrong_type_and_corrupt_files_are_rejected(tmp_path):
    assert "not found" in master_sheet_format_error(str(tmp_path / "missing.xlsx"))
    text = tmp_path / "notes.txt"
    text.write_text("x")
    assert "not an Excel workbook" in master_sheet_format_error(str(text))
    corrupt = tmp_path / "corrupt.xlsx"
    corrupt.write_bytes(b"not a zip")
    assert "could not be read" in master_sheet_format_error(str(corrupt))


def test_password_protected_master_sheet_is_read_in_memory(tmp_path):
    from msoffcrypto.format.ooxml import OOXMLFile

    from autohub.services.common.workbook import DEFAULT_PASSWORD

    plain = _workbook(tmp_path / "plain.xlsx", "Master sheet")
    protected = tmp_path / "protected.xlsx"
    with open(plain, "rb") as source, open(protected, "wb") as target:
        OOXMLFile(source).encrypt(DEFAULT_PASSWORD, target)
    assert master_sheet_format_error(str(protected)) == ""
    with open(plain, "rb") as source, open(tmp_path / "other.xlsx", "wb") as target:
        OOXMLFile(source).encrypt("another password", target)
    assert "could not be read" in master_sheet_format_error(str(tmp_path / "other.xlsx"))


@pytest.mark.parametrize("sheet_name,cell", [
    ("Master sheet", "D7"), ("Master sheet", "J7"), ("Master sheet", "CZ7"),
    (mx17_layout.MAIN_SHEET_NAME, "W5"), (mx17_layout.MAIN_SHEET_NAME, "X5"),
])
def test_missing_required_column_headers_are_rejected(tmp_path, sheet_name, cell):
    path = _workbook(tmp_path / "missing-column.xlsx", sheet_name)
    workbook = openpyxl.load_workbook(path)
    workbook[sheet_name][cell] = None
    workbook.save(path)
    workbook.close()
    error = master_sheet_format_error(str(path))
    assert "missing required Master Sheet columns/headers" in error and cell in error


@pytest.mark.parametrize("sheet_name", ["Master sheet", mx17_layout.MAIN_SHEET_NAME])
def test_a_named_but_empty_sheet_is_not_a_valid_master(tmp_path, sheet_name):
    workbook = openpyxl.Workbook()
    workbook.active.title = sheet_name
    path = tmp_path / "empty.xlsx"
    workbook.save(path)
    workbook.close()
    assert "missing required Master Sheet columns/headers" in master_sheet_format_error(str(path))


def test_shifted_identity_column_is_rejected(tmp_path):
    path = _workbook(tmp_path / "shifted.xlsx", "Master sheet")
    workbook = openpyxl.load_workbook(path)
    workbook["Master sheet"].delete_cols(10)
    workbook.save(path)
    workbook.close()
    assert "J7" in master_sheet_format_error(str(path))
