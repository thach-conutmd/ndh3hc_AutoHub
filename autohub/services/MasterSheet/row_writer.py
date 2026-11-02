"""Writes request rows into the Master Sheet worksheet (COM): insert from the template or update in place."""
from __future__ import annotations

from datetime import datetime

from autohub.core.impl_values import normalize_impl_value
from autohub.core.impl_update import ImplOutcome, ImplUpdate
from autohub.core.webflow_links import webflow_link_text
from autohub.core.normalizers import clean_text, needs_text_format, normalize_part_number

FIRST_DATA_ROW = 11  # rows above hold the template and examples

LAST_DATA_COLUMN = "CZ"
WEBFLOW_LINK_COLUMN = "I"  # "Webflow No. with Link"
_ROWS_PER_VARIANT = 3  # request, implementation and comparison rows
_INSERT_SHIFT_DOWN = -4121  # xlShiftDown
_TEMPLATE_ROW_TYPES = {"REQ", "IMPL"}
_PRESERVED_COLUMNS = {2, 4}  # No. and the REQ/IMPL mark
SOFTWARE_PART_COLUMN = "AX"


class VariantRowWriter:
    def __init__(self, worksheet, excel_app):
        self._worksheet = worksheet
        self._excel_app = excel_app

    def copy_one_variant_template(self, row_count: int = _ROWS_PER_VARIANT) -> dict:
        """Copy the last `row_count` rows below themselves as an empty variant; returns the row ranges."""
        if row_count < 1:
            raise ValueError("row_count must be greater than zero.")

        worksheet = self._worksheet
        used = worksheet.UsedRange
        last_row = used.Row + used.Rows.Count - 1
        first_row = last_row - row_count + 1
        if first_row < used.Row:
            raise ValueError("The worksheet does not contain enough rows to copy.")

        destination_row = last_row + 1
        worksheet.Rows(f"{first_row}:{last_row}").Copy()
        inserted_rows = f"{destination_row}:{destination_row + row_count - 1}"
        worksheet.Rows(inserted_rows).Insert(Shift=_INSERT_SHIFT_DOWN)
        self._excel_app.CutCopyMode = False
        self._clear_copied_values(destination_row, destination_row + row_count - 1)
        return {"SourceRows": f"{first_row}:{last_row}", "InsertedRows": inserted_rows}

    def save_rows(self, variants: list[dict]) -> list[dict]:
        """Write each (possibly user-edited) row; a "_row" entry updates that row, otherwise a new one is inserted."""
        saved = []
        for variant in variants:
            existing_row = variant.get("_row")
            values = {key: value for key, value in variant.items() if not key.startswith("_")}

            if existing_row:
                request_row = int(existing_row)
                self.write_values(request_row, values)
            else:
                copied = self.copy_one_variant_template()
                request_row = int(copied["InsertedRows"].split(":", 1)[0])
                self.write_values(request_row, {**values, "C": datetime.now()})

            saved.append(
                {
                    "PartNumber": values.get("J"),
                    "RequestRow": request_row,
                    "ImplementationRow": request_row + 1,
                    "ComparisonRow": request_row + 2,
                }
            )
        return saved

    def delete_variants(self, request_rows: list[int]) -> int:
        """Delete the REQ row and its implementation and comparison rows for each given request row.

        Rows go from the bottom up so the numbers still to delete stay valid; returns how many variants went."""
        deleted = 0
        for request_row in sorted({int(row) for row in request_rows}, reverse=True):
            if request_row < FIRST_DATA_ROW or str(self._worksheet.Cells(request_row, 4).Value).strip().upper() != "REQ":
                continue  # not a request row any more, never delete something else
            self._worksheet.Rows(f"{request_row}:{request_row + _ROWS_PER_VARIANT - 1}").Delete()
            deleted += 1
        return deleted

    def write_webflow_links(self, rows_by_part_number: dict[str, int], links: dict[str, str]) -> int:
        written = 0
        for part_number, link in links.items():
            row = rows_by_part_number.get(normalize_part_number(part_number).upper())
            if row is None or not link:
                continue
            cell = self._worksheet.Range(f"{WEBFLOW_LINK_COLUMN}{row}")
            if cell.HasFormula:
                continue
            text = webflow_link_text(link)
            try:
                # positional (Anchor, Address, SubAddress, ScreenTip, TextToDisplay): COM can drop keyword arguments
                self._worksheet.Hyperlinks.Add(cell, link, "", "", text or link)
            except Exception:  # a plain-text link is still better than none
                cell.Value = link
            written += 1
        return written

    def write_webflow_numbers(
        self, rows_by_part_number: dict[str, int], numbers: dict[str, dict[str, str]],
        columns: dict[str, str] | None = None,
    ) -> int:
        columns = columns if columns is not None else {"AX": "AX", "AW": "AW"}
        pending = []
        for part, values in numbers.items():
            row = rows_by_part_number.get(normalize_part_number(part).upper())
            if row is None:
                raise ValueError(f"No Master Sheet row found for {part}.")
            for key, value in values.items():
                if key not in columns:
                    raise ValueError(f"Unsupported WebFlow number column: {key}")
                address = f"{columns[key]}{row}"
                cell = self._worksheet.Range(address)
                if key == "AX" and columns[key] == "AX" and cell.HasFormula:
                    formula = str(cell.Formula).replace("$", "").strip().upper()
                    if formula == f"=K{row}":
                        address = f"K{row}"
                        cell = self._worksheet.Range(address)
                if cell.HasFormula:
                    raise ValueError(f"Cannot overwrite formula in {address}.")
                pending.append((cell, value))
        for cell, value in pending:
            cell.NumberFormat = "@"
            cell.Value = str(value)
        return len(numbers)

    def write_impl_values(
        self, request_rows: dict[str, list[int]], updates: dict[str, ImplUpdate]
    ) -> dict[str, ImplOutcome]:
        """Writes each variant's values into the IMPL row under its REQ row, after checking that row is the right one."""
        worksheet = self._worksheet
        outcomes: dict[str, ImplOutcome] = {}
        plan = []
        for part, update in updates.items():
            rows = request_rows.get(normalize_part_number(part).upper(), [])
            if len(rows) != 1:
                outcomes[part] = ImplOutcome(error="No Master Sheet row found." if not rows else
                                             "The variant appears in several Master Sheet rows.")
                continue
            impl_row = rows[0] + 1
            software = normalize_part_number(worksheet.Range(f"{SOFTWARE_PART_COLUMN}{rows[0]}").Value).upper()
            if clean_text(worksheet.Cells(impl_row, 4).Value).upper() != "IMPL":
                outcomes[part] = ImplOutcome(error="The row below the request row is not an IMPL row.")
            elif software != normalize_part_number(update.software).upper():
                outcomes[part] = ImplOutcome(error="The Master Sheet SW Part Number no longer matches the comparison.")
            else:
                plan.append((part, rows[0], impl_row, update))
        for part, request_row, impl_row, update in plan:
            written = skipped = 0
            try:
                for column, value in update.values.items():
                    cell = worksheet.Range(f"{column}{impl_row}")
                    if cell.HasFormula:
                        skipped += 1
                        continue
                    value = normalize_impl_value(
                        update.kinds.get(column, ""), value, (cell.Value, worksheet.Range(f"{column}{request_row}").Value)
                    )
                    if isinstance(value, str) and needs_text_format(value):
                        cell.NumberFormat = "@"
                    cell.Value = value
                    written += 1
            except Exception as error:
                outcomes[part] = ImplOutcome(written, skipped, str(error))
            else:
                outcomes[part] = ImplOutcome(written, skipped)
        return outcomes

    def write_values(self, row: int, values: dict) -> None:
        worksheet = self._worksheet
        last_data_column = worksheet.Range(f"{LAST_DATA_COLUMN}1").Column
        for column_name, value in values.items():
            if value in (None, ""):
                continue
            cell = worksheet.Range(f"{column_name}{row}")
            if cell.Column <= last_data_column and not cell.HasFormula:
                if needs_text_format(value):
                    cell.NumberFormat = "@"  # keep leading zeros and values like 4E5 as typed
                cell.Value = value

    def _clear_copied_values(self, first_row: int, last_row: int) -> None:
        worksheet = self._worksheet
        last_column = worksheet.Range(f"{LAST_DATA_COLUMN}1").Column
        for row in range(first_row, last_row + 1):
            if str(worksheet.Cells(row, 4).Value).strip().upper() not in _TEMPLATE_ROW_TYPES:
                continue
            for column in range(worksheet.UsedRange.Column, last_column + 1):
                cell = worksheet.Cells(row, column)
                if column not in _PRESERVED_COLUMNS and not cell.HasFormula:
                    cell.ClearContents()
