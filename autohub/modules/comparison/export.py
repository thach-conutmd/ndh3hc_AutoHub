"""Writes the stored comparison result to an Excel workbook."""
from __future__ import annotations

from typing import Iterable, Sequence

from openpyxl import Workbook


def export_rows(path: str, headers: Sequence[str], rows: Iterable[Sequence[str]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Comparison"
    sheet.append(list(headers))
    for row in rows:
        sheet.append(list(row))
    workbook.save(path)
