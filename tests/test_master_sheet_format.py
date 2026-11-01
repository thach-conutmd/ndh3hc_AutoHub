"""Master Sheet format check used before loading variants at startup (no Excel)."""
import io
import sys
import types

import openpyxl
import pytest

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
