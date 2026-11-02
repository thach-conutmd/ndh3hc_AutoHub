"""Picks the master sheet implementation that fits the workbook: MG1 "Master sheet" or the Mx17 flat layout."""
from __future__ import annotations

import html
import io
import re
import zipfile
from pathlib import Path
from typing import IO

import msoffcrypto
import openpyxl
from openpyxl.utils import column_index_from_string

from autohub.core.variant_schema import VARIANT_FIELD_ORDER

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


def _protected_workbook(path: str) -> io.BytesIO:
    """Decrypt a protected workbook in memory, using the existing Master Sheet password."""
    with open(path, "rb") as file:
        office_file = msoffcrypto.OfficeFile(file)
        office_file.load_key(password=DEFAULT_PASSWORD)
        decrypted = io.BytesIO()
        office_file.decrypt(decrypted)
    decrypted.seek(0)
    return decrypted


def master_sheet_format_error(path: str) -> str:
    """Why `path` is not a Master Sheet AutoHub can read, checked without Excel; empty when it is one."""
    file = Path(path)
    if not file.is_file():
        return f"Master Sheet not found: {path}"
    if file.suffix.lower() not in _WORKBOOK_SUFFIXES:
        return f"'{file.name}' is not an Excel workbook (.xlsx)."
    try:
        source = path if zipfile.is_zipfile(path) else _protected_workbook(path)
        workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
        try:
            names = workbook.sheetnames
            if mx17_layout.MG1_SHEET_NAME in names:
                sheet = workbook[mx17_layout.MG1_SHEET_NAME]
                header_row, columns = 7, ["D", *VARIANT_FIELD_ORDER]
                markers = {"D": "requirement", "J": "dwg", "Q": "ecu", "AX": "sw"}
            elif mx17_layout.is_mx17_sheet_names(names):
                sheet = workbook[mx17_layout.MAIN_SHEET_NAME]
                header_row, columns = 5, sorted(set(mx17_layout.MAIN_COLUMNS.values()))
                markers = {"E": "ecu", "P": "purpose", "W": "customer order", "X": "sw"}
            else:
                return (
                    f"'{file.name}' has neither the '{mx17_layout.MG1_SHEET_NAME}' "
                    f"nor the '{mx17_layout.MAIN_SHEET_NAME}' sheet."
                )
            header = next(sheet.iter_rows(
                min_row=header_row, max_row=header_row,
                max_col=max(column_index_from_string(column) for column in columns), values_only=True,
            ), ())
            values = {
                column: " ".join(str(
                    header[column_index_from_string(column) - 1] or ""
                ).split()).casefold() if header else ""
                for column in columns
            }
            missing = [
                f"{column}{header_row}" for column in columns
                if not values[column] or (column in markers and markers[column] not in values[column])
            ]
            if missing:
                return f"'{file.name}' is missing required Master Sheet columns/headers: {', '.join(missing)}."
            return ""
        finally:
            workbook.close()
    except Exception as error:
        return f"'{file.name}' could not be read as an Excel workbook: {error}"


def open_master_sheet(path: str) -> MasterSheet:
    """The Mx17 layout for the Honda GDI release workbook, the MG1 layout for everything else."""
    if mx17_layout.is_mx17_sheet_names(workbook_sheet_names(path)):
        return Mx17MasterSheet(path)
    return MasterSheet(path)
