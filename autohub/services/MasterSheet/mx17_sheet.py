"""The Mx17 (MED17) master sheet session: flat main sheet plus per-project Info sheets, through Excel COM.

Same interface as `MasterSheet` (the MG1 layout, which is left as it is), so the Home module treats both alike.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from openpyxl.utils import column_index_from_string, get_column_letter

from autohub.core.normalizers import needs_text_format, normalize_part_number
from autohub.core.records import EcuInfoData, HWLookup, KickOffInfo, SystemMatrixData
from autohub.core.webflow_defaults import WebFlowDefaults
from autohub.services.common.read_only_flag import clear_read_only_recommended
from autohub.services.common.file_access import write_block_reason
from autohub.services.MasterSheet import mx17_layout as layout
from autohub.services.MasterSheet.MasterSheet import MasterSheet
from autohub.services.MasterSheet.row_writer import VariantRowWriter
from autohub.services.MasterSheet.variant_builder import compute_new_variant_rows
from autohub.services.MasterSheet.webflow_variants import webflow_variant_from_row

_XL_CELL_TYPE_CONSTANTS = 2
_XL_READ_WRITE = 2
_LAST_MAIN_INDEX = column_index_from_string(layout.LAST_DATA_COLUMN)
_LAST_INFO_INDEX = column_index_from_string(layout.INFO_LAST_COLUMN)


def _columns(row: tuple, last_index: int) -> dict[str, Any]:
    return {get_column_letter(index + 1): value for index, value in enumerate(row[:last_index])}


class Mx17MasterSheet(MasterSheet):
    sheet_name = layout.MAIN_SHEET_NAME

    def _open_workbook(self, path: str):
        """Opens past a "read-only recommended" flag; a really locked file can still be read, but not written."""
        self.excel_app.DisplayAlerts = False
        if path == self.file_path:
            clear_read_only_recommended(path)  # the flag makes Excel ask "open as read-only?" every time
        self.workbook = self.excel_app.Workbooks.Open(
            path, UpdateLinks=0, ReadOnly=False, IgnoreReadOnlyRecommended=True
        )
        try:
            self.workbook.ReadOnlyRecommended = False  # a later save must not bring the flag back
        except Exception:
            pass
        return self.workbook

    def _require_writable(self) -> None:
        if self.workbook.ReadOnly:
            self._try_read_write()
        if self.workbook.ReadOnly:
            reason = write_block_reason(self.file_path) or "Excel opened it read-only (e.g. another Excel holds it)"
            raise PermissionError(f"Workbook is locked or read-only: {reason}. {self.file_path}")

    def _try_read_write(self) -> None:
        """Asks Excel to reopen the workbook read-write; that fails (and it stays read-only) while it is locked."""
        try:
            self.workbook.ChangeFileAccess(Mode=_XL_READ_WRITE)
            self.workbook = self.excel_app.Workbooks(os.path.basename(self.file_path))
        except Exception:  # still locked; the caller reports why
            pass

    # -- Reading ---------------------------------------------------------------------

    def _last_used_row(self, worksheet) -> int:
        try:
            used = worksheet.UsedRange
            return used.Row + used.Rows.Count - 1
        except Exception as error:
            raise RuntimeError(f"Could not read the used range of {worksheet.Name}: {error}") from error

    def _block(self, worksheet, first_row: int, last_row: int, last_column: str) -> list[tuple]:
        """The cells A{first_row}:{last_column}{last_row} in one call (a COM call per cell would be far too slow)."""
        if last_row < first_row:
            return []
        address = f"A{first_row}:{last_column}{last_row}"
        try:
            value = worksheet.Range(address).Value
        except Exception as error:
            raise RuntimeError(f"Could not read {worksheet.Name}!{address}: {error}") from error
        if not isinstance(value, tuple):
            return [(value,)] if value is not None else []
        return list(value)

    def _main_rows(self) -> list[tuple[int, dict[str, Any]]]:
        worksheet = self._worksheet()
        first = layout.FIRST_DATA_ROW
        block = self._block(worksheet, first, self._last_used_row(worksheet), layout.LAST_DATA_COLUMN)
        rows = [(first + offset, _columns(row, _LAST_MAIN_INDEX)) for offset, row in enumerate(block)]
        return [(row, values) for row, values in rows if normalize_part_number(values.get(layout.PART_NUMBER_COLUMN))]

    def _info_sheets(self) -> list:
        sheets = []
        for index in range(1, self.workbook.Worksheets.Count + 1):
            try:
                worksheet = self.workbook.Worksheets(index)
                marker = worksheet.Range(f"{layout.INFO_MARKER_COLUMN}{layout.INFO_HEADER_ROW}").Value
            except Exception:
                continue  # not a worksheet we can read (e.g. a chart sheet)
            if isinstance(marker, str) and layout.INFO_MARKER_TEXT in marker:
                sheets.append(worksheet)
        return sheets

    def _info_rows(self) -> dict[str, tuple[Any, int, dict[str, Any]]]:
        """Upper-case part number -> (Info sheet, row, {column: value}); the last row of a part number wins."""
        found: dict[str, tuple[Any, int, dict[str, Any]]] = {}
        marker_index = column_index_from_string(layout.INFO_MARKER_COLUMN) - 1
        for worksheet in self._info_sheets():
            first = layout.INFO_FIRST_DATA_ROW
            block = self._block(worksheet, first, self._last_used_row(worksheet), layout.INFO_LAST_COLUMN)
            for offset, row in enumerate(block):
                part_number = normalize_part_number(row[0])
                if part_number and row[marker_index] not in (None, ""):  # title rows have no Delivery Type
                    found[part_number.upper()] = (worksheet, first + offset, _columns(row, _LAST_INFO_INDEX))
        return found

    @staticmethod
    def _home_values(values: dict, info: dict) -> dict:
        """The Home table values of one main sheet row, overlaid with its Info sheet row."""
        home = layout.home_from_main(values)
        home["BA"] = values.get(layout.CONTAINER_CHECKSUM_COLUMN)
        part_number = home["J"] = normalize_part_number(home["J"])
        if part_number.upper() in info:
            home.update(layout.home_overlay_from_info(info[part_number.upper()][2]))
        return home

    def _loaded_variants(self) -> list[tuple[int, dict, Any]]:
        """(main sheet row, Home table values, created date), the latest row per part number."""
        info = self._info_rows()
        latest: dict[str, tuple[int, dict, Any]] = {}
        for row, values in self._main_rows():
            home = self._home_values(values, info)
            latest[home["J"].upper()] = (row, home, values.get("B"))
        return list(latest.values())

    def load_variant_rows(self) -> list[dict]:
        return [{"_row": row, **home} for row, home, _created in self._loaded_variants()]

    def load_webflow_variants(self) -> list[dict]:
        return [
            webflow_variant_from_row(home["J"], {**home, "C": created})
            for _row, home, created in self._loaded_variants()
        ]

    # -- New variants ----------------------------------------------------------------

    def compute_new_variants(
        self,
        system_info: SystemMatrixData,
        ecu_info: EcuInfoData,
        hw_info: HWLookup | None = None,
        kick_off: KickOffInfo | None = None,
        variant_defaults: WebFlowDefaults | None = None,
    ) -> list[dict]:
        """Variants whose part number is not in the main sheet yet (the Purpose column is free text here)."""
        known = {normalize_part_number(values.get(layout.PART_NUMBER_COLUMN)).upper() for _row, values in self._main_rows()}
        rows = compute_new_variant_rows(
            ecu_info, system_info, set(), hw_info, kick_off=kick_off, variant_defaults=variant_defaults
        )
        return [row for row in rows if normalize_part_number(row.get("J")).upper() not in known]

    # -- Writing ---------------------------------------------------------------------

    def write_webflow_numbers(self, numbers: dict[str, dict[str, str]], save: bool = True) -> int:
        self._require_writable()
        rows = {
            normalize_part_number(values.get(layout.PART_NUMBER_COLUMN)).upper(): row
            for row, values in self._main_rows()
        }
        written = VariantRowWriter(self._worksheet(), self.excel_app).write_webflow_numbers(
            rows, numbers, {key: layout.MAIN_COLUMNS[key] for key in ("AX", "AW")}
        )
        if save and written:
            self.save()
        return written

    def write_impl_values(self, updates, save: bool = True):
        raise ValueError("This Master Sheet layout has no IMPL rows to update.")

    def write_container_checksums(self, checksums: dict[str, str], save: bool = True) -> int:
        self._require_writable()
        rows = {
            normalize_part_number(values.get(layout.PART_NUMBER_COLUMN)).upper(): row
            for row, values in self._main_rows()
        }
        written = VariantRowWriter(self._worksheet(), self.excel_app).write_container_checksums(
            rows, checksums, layout.CONTAINER_CHECKSUM_COLUMN
        )
        if save and written:
            self.save()
        return written

    def save_variant_rows(self, variants: list[dict], save: bool = True) -> list[dict]:
        """A "_row" entry updates that main sheet row (and its Info row); otherwise a row is appended to both."""
        self._require_writable()
        worksheet = self._worksheet()
        info = self._info_rows()
        current = {row: self._home_values(values, info) for row, values in self._main_rows()}
        saved = []
        for variant in variants:
            home = {key: value for key, value in variant.items() if not key.startswith("_")}
            row = variant.get("_row")
            written = home  # what the user changed (existing rows) or everything (new rows)
            if row:
                row = int(row)
                before = current.get(row, {})
                changed = written = layout.changed_home_values(before, home)
                if not changed:
                    saved.append({"PartNumber": home.get("J"), "RequestRow": row, "Unmapped": []})
                    continue  # an unchanged variant is not touched
                self._write(worksheet, row, layout.main_values_from_home(changed, keep_blank=True), layout.LAST_DATA_COLUMN)
                known = info.get(normalize_part_number(before.get("J")).upper())
                if known:
                    self._write(
                        known[0], known[1], layout.info_values_from_home(changed, keep_blank=True), layout.INFO_LAST_COLUMN
                    )
                elif layout.needs_info_row(changed):
                    self._append_info_row({**before, **home})  # the edit has no place in the main sheet
            else:
                row = self._append_main_row(worksheet)
                self._write(worksheet, row, layout.new_main_values(home, datetime.now()), layout.LAST_DATA_COLUMN)
                self._append_info_row(home)
            saved.append({"PartNumber": home.get("J"), "RequestRow": row, "Unmapped": layout.unmapped_keys(written)})
        if save:
            self.save()
        return saved

    def delete_variant_rows(self, request_rows: list[int], save: bool = True) -> int:
        """Delete the main sheet rows (one per variant), bottom up; a row without a part number is skipped."""
        self._require_writable()
        worksheet = self._worksheet()
        deleted = 0
        for row in sorted({int(row) for row in request_rows}, reverse=True):
            if row < layout.FIRST_DATA_ROW or not worksheet.Range(f"{layout.PART_NUMBER_COLUMN}{row}").Value:
                continue
            worksheet.Rows(row).Delete()
            deleted += 1
        if save and deleted:
            self.save()
        return deleted

    def delete_variants_by_part_number(self, part_numbers: list[str], save: bool = True) -> int:
        """Deletes the main sheet rows whose part number matches, wherever they are now (never by remembered row).

        Only main sheet rows go; no worksheet is deleted or renamed and the Info rows stay."""
        self._require_writable()
        worksheet = self._worksheet()
        wanted = {normalize_part_number(part).upper() for part in part_numbers if normalize_part_number(part)}
        rows = [
            row for row, values in self._main_rows()
            if normalize_part_number(values.get(layout.PART_NUMBER_COLUMN)).upper() in wanted
        ]
        for row in sorted(rows, reverse=True):
            worksheet.Rows(row).Delete()
        if save and rows:
            self.save()
        return len(rows)

    def _write(self, worksheet, row: int, values: dict[str, Any], last_column: str) -> None:
        """Writes into the existing columns A..`last_column` only; the sheet never gets a new column."""
        limit = column_index_from_string(last_column)
        for column, value in values.items():
            if column_index_from_string(column) > limit:
                continue
            address = f"{column}{row}"
            try:
                self._write_cell(worksheet.Range(address), value)
            except Exception as error:
                raise RuntimeError(f"Could not write {worksheet.Name}!{address}: {error}") from error

    @staticmethod
    def _write_cell(cell, value) -> None:
        if cell.MergeCells:
            anchor = cell.MergeArea.Cells(1, 1)
            if anchor.Address != cell.Address:
                return  # only the top-left cell of a merged area holds a value
            cell = anchor
        if cell.HasFormula:
            return  # formulas (running number, hex of the program id) stay as they are
        if needs_text_format(value):
            cell.NumberFormat = "@"  # keep leading zeros and values like 4E5 as typed
        cell.Value = value

    def _clear_constants(self, worksheet, row: int, last_column: str) -> None:
        """Empties the typed-in cells of a copied row; formulas stay. Merged cells are cleared through their anchor."""
        try:
            worksheet.Range(f"A{row}:{last_column}{row}").SpecialCells(_XL_CELL_TYPE_CONSTANTS).ClearContents()
            return
        except Exception:
            pass  # nothing to clear, or a merged cell stops the bulk clear: go cell by cell
        for index in range(1, column_index_from_string(last_column) + 1):
            cell = worksheet.Cells(row, index)
            if cell.MergeCells:
                cell = cell.MergeArea.Cells(1, 1)
            if not cell.HasFormula and cell.Value not in (None, ""):
                cell.Value = None

    def _copy_row_below(self, worksheet, row: int, last_column: str) -> int:
        """Copies `row` (formats and formulas) to the row below and clears the copied constants."""
        new_row = row + 1
        try:
            worksheet.Rows(row).Copy(worksheet.Rows(new_row))
        except Exception as error:
            raise RuntimeError(f"Could not copy {worksheet.Name} row {row} to row {new_row}: {error}") from error
        self.excel_app.CutCopyMode = False
        self._clear_constants(worksheet, new_row, last_column)
        return new_row

    def _append_main_row(self, worksheet) -> int:
        last = layout.FIRST_DATA_ROW - 1
        for row, _values in self._main_rows():
            last = max(last, row)
        return self._copy_row_below(worksheet, last, layout.LAST_DATA_COLUMN)

    def _sheet_names(self) -> list[str]:
        return [self.workbook.Worksheets(index).Name for index in range(1, self.workbook.Worksheets.Count + 1)]

    def _find_sheet(self, name: str):
        for index in range(1, self.workbook.Worksheets.Count + 1):
            if self.workbook.Worksheets(index).Name == name:
                return self.workbook.Worksheets(index)
        return None

    def _new_info_sheet(self, name: str, title: str):
        """A new Info sheet for a project: a copy of the Mx17_5xFx_Info sheet without its variants."""
        sheets = self._info_sheets()
        if not sheets:
            raise RuntimeError("The Master Sheet has no Info sheet to copy for the new project.")
        template = next((sheet for sheet in sheets if sheet.Name == layout.INFO_TEMPLATE_SHEET), None)
        if template is None:
            raise RuntimeError(f"The Info sheet '{layout.INFO_TEMPLATE_SHEET}' is needed as the template of new Info sheets.")
        before = self._sheet_names()
        template.Copy(None, sheets[-1])  # positional: (Before, After); keyword args may be dropped by COM
        # Found by name: the active sheet is not reliable, and renaming or clearing it could hit the main sheet.
        added = [sheet_name for sheet_name in self._sheet_names() if sheet_name not in before]
        if len(added) != 1:
            raise RuntimeError(f"Copying '{template.Name}' did not add exactly one sheet (added: {added}).")
        worksheet = self._find_sheet(added[0])
        if worksheet.Name in before:
            raise RuntimeError("Refusing to rename a sheet that already existed.")
        worksheet.Name = name
        last = max(self._last_used_row(worksheet), layout.INFO_TITLE_ROW)
        cleared = worksheet.Range(f"A{layout.INFO_TITLE_ROW}:{layout.INFO_LAST_COLUMN}{last}")
        try:
            cleared.ClearContents()
        except Exception:  # a partly covered merged cell blocks the clear
            cleared.UnMerge()
            cleared.ClearContents()
        self._write(worksheet, layout.INFO_TITLE_ROW, {"A": title}, layout.INFO_LAST_COLUMN)
        return worksheet

    def _append_info_row(self, home: dict) -> None:
        name = layout.info_sheet_name(home.get("AB"))
        try:
            self._append_info_row_to(name, home)
        except Exception as error:
            raise RuntimeError(f"Could not add {home.get('J')} to the Info sheet '{name}': {error}") from error

    def _append_info_row_to(self, name: str, home: dict) -> None:
        worksheet = self._find_sheet(name)
        if worksheet is None:
            worksheet = self._new_info_sheet(name, home.get("H") or name)
            row = layout.INFO_FIRST_DATA_ROW
        else:
            last = layout.INFO_FIRST_DATA_ROW - 1
            for offset, values in enumerate(
                self._block(worksheet, layout.INFO_FIRST_DATA_ROW, self._last_used_row(worksheet), "A")
            ):
                if values[0] not in (None, ""):
                    last = layout.INFO_FIRST_DATA_ROW + offset
            row = (
                self._copy_row_below(worksheet, last, layout.INFO_LAST_COLUMN)
                if last >= layout.INFO_FIRST_DATA_ROW
                else layout.INFO_FIRST_DATA_ROW
            )
        self._write(
            worksheet, row, layout.info_values_from_home(home, defaults_for_blanks=True), layout.INFO_LAST_COLUMN
        )
