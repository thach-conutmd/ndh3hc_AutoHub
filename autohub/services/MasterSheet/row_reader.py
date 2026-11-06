"""Reads request ("REQ") rows from the Master Sheet worksheet (COM)."""
from __future__ import annotations

from typing import Iterator

from autohub.core.normalizers import clean_text, normalize_part_number
from autohub.core.webflow_links import is_link
from autohub.core.variant_schema import  VARIANT_FIELD_ORDER
from autohub.services.MasterSheet.variant_builder import variant_key
from autohub.services.MasterSheet.webflow_variants import WEBFLOW_SOURCE_COLUMNS, webflow_variant_from_row

from autohub.services.MasterSheet.row_writer import FIRST_DATA_ROW, HEX_LINK_COLUMN, WEBFLOW_LINK_COLUMN  # rows above hold the template, not variants
_REQUEST_MARK = "REQ"


class VariantRowReader:
    def __init__(self, worksheet):
        self._worksheet = worksheet

    def _used_rows(self) -> tuple[int, int]:
        used = self._worksheet.UsedRange
        return used.Row, used.Row + used.Rows.Count - 1

    def _value(self, column: str, row: int):
        return self._worksheet.Range(f"{column}{row}").Value

    def _is_request_row(self, row: int) -> bool:
        return clean_text(self._value("D", row)).upper() == _REQUEST_MARK

    def request_rows_with_part_number(self) -> Iterator[tuple[int, str]]:
        first_used, last_row = self._used_rows()
        for row in range(max(FIRST_DATA_ROW, first_used), last_row + 1):
            if not self._is_request_row(row):
                continue
            part_number = normalize_part_number(self._value("J", row))
            if part_number:
                yield row, part_number

    def _hyperlink_address(self, column: str, row: int) -> str:
        cell = self._worksheet.Range(f"{column}{row}")
        try:
            if cell.Hyperlinks.Count:
                return clean_text(cell.Hyperlinks(1).Address)
        except Exception:
            pass
        return ""

    def _webflow_link(self, row: int) -> str:
        """The address of the cell's hyperlink; a cell holding the plain link text counts too."""
        address = self._hyperlink_address(WEBFLOW_LINK_COLUMN, row)
        if address:
            return address
        text = clean_text(self._worksheet.Range(f"{WEBFLOW_LINK_COLUMN}{row}").Value)
        return text if is_link(text) else ""

    def latest_request_rows(self) -> dict[str, int]:
        """Upper-case part number -> its last REQ row (the one the WebFlow variant is built from)."""
        return {part.upper(): row for row, part in self.request_rows_with_part_number()}

    def load_variant_rows(self) -> list[dict]:
        """REQ rows as column-letter dicts for the UI table; each carries its Excel row as "_row"."""
        rows_by_part_number: dict[str, dict] = {}
        for row, part_number in self.request_rows_with_part_number():
            rows_by_part_number[part_number.upper()] = {
                "_row": row,
                "_webflow_link": self._webflow_link(row),
                **{
                    column: self._value(column, row)
                    for column in VARIANT_FIELD_ORDER
                    if not column.startswith("_")
                },
            }
        return list(rows_by_part_number.values())

    def load_webflow_variants(self) -> list[dict]:
        """WebFlow-ready variants; rows are appended chronologically, so the latest per part number wins."""
        variants_by_part_number: dict[str, dict] = {}
        for row, part_number in self.request_rows_with_part_number():
            values = {column: self._value(column, row) for column in WEBFLOW_SOURCE_COLUMNS}
            variant = webflow_variant_from_row(part_number, values)
            variant["webflow_link"] = self._webflow_link(row)
            hex_path = self._hyperlink_address(HEX_LINK_COLUMN, row)
            if hex_path:
                variant["_calibration_hex_path"] = hex_path
            variants_by_part_number[part_number.upper()] = variant
        return list(variants_by_part_number.values())

    def existing_variant_keys(self) -> set[tuple[str, str, str]]:
        """Keys of every REQ row, template and example rows included, so those are never recreated."""
        first_used, last_row = self._used_rows()
        keys: set[tuple[str, str, str]] = set()
        for row in range(first_used, last_row + 1):
            if not self._is_request_row(row):
                continue
            key = variant_key(self._value("H", row), self._value("J", row), self._value("BI", row))
            if all(key):
                keys.add(key)
        return keys
