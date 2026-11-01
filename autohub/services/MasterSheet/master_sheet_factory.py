"""Picks the master sheet implementation that fits the workbook: MG1 "Master sheet" or the Mx17 flat layout."""
from __future__ import annotations

import html
import io
import re
import zipfile
from pathlib import Path
from typing import IO

import msoffcrypto

from autohub.services.common.workbook import DEFAULT_PASSWORD
from autohub.services.MasterSheet import mx17_layout
from autohub.services.MasterSheet.MasterSheet import MasterSheet
from autohub.services.MasterSheet.mx17_sheet import Mx17MasterSheet

_SHEET_TAG = re.compile(r'<sheet\b[^>]*?\bname="([^"]*)"')


_WORKBOOK_SUFFIXES = (".xlsx", ".xlsm")


def workbook_sheet_names(path: str | IO[bytes]) -> list[str]:
    """Sheet names read straight from the .xlsx package (no Excel); empty when the file is not a plain xlsx."""
    try:
        with zipfile.ZipFile(path) as package:
            xml = package.read("xl/workbook.xml").decode("utf-8", errors="replace")
    except (OSError, KeyError, zipfile.BadZipFile):
        return []
    return [html.unescape(name) for name in _SHEET_TAG.findall(xml)]


def _protected_sheet_names(path: str) -> list[str]:
    """Sheet names of a password-protected workbook, decrypted in memory; empty when it cannot be read."""
    try:
        with open(path, "rb") as file:
            office_file = msoffcrypto.OfficeFile(file)
            if not office_file.is_encrypted():
                return []
            office_file.load_key(password=DEFAULT_PASSWORD)
            decrypted = io.BytesIO()
            office_file.decrypt(decrypted)
    except Exception:
        return []
    return workbook_sheet_names(decrypted)


def master_sheet_format_error(path: str) -> str:
    """Why `path` is not a Master Sheet AutoHub can read, checked without Excel; empty when it is one."""
    file = Path(path)
    if not file.is_file():
        return f"Master Sheet not found: {path}"
    if file.suffix.lower() not in _WORKBOOK_SUFFIXES:
        return f"'{file.name}' is not an Excel workbook (.xlsx)."
    names = workbook_sheet_names(path) or _protected_sheet_names(path)
    if not names:
        return f"'{file.name}' could not be read as an Excel workbook."
    if mx17_layout.MG1_SHEET_NAME in names or mx17_layout.is_mx17_sheet_names(names):
        return ""
    return (
        f"'{file.name}' has neither the '{mx17_layout.MG1_SHEET_NAME}' "
        f"nor the '{mx17_layout.MAIN_SHEET_NAME}' sheet."
    )


def open_master_sheet(path: str) -> MasterSheet:
    """The Mx17 layout for the Honda GDI release workbook, the MG1 layout for everything else."""
    if mx17_layout.is_mx17_sheet_names(workbook_sheet_names(path)):
        return Mx17MasterSheet(path)
    return MasterSheet(path)
