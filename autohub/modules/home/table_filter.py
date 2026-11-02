"""Excel-style per-column filter for the variant table: right-click a column header to filter it."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableView, QTableWidget

from autohub.modules.home.filter_dialog import ColumnFilterDialog
from autohub.modules.home.row_filter import RowFilter

_MARK = " ▼"


class TableFilter:
    def __init__(
        self, table: QTableWidget, mirrored_views: tuple[QTableView, ...] = (), first_column: int = 1,
        row_visible: Callable[[int], bool] | None = None,
        on_applied: Callable[[], None] | None = None,
    ):
        """Rows are hidden in `table` and each of `mirrored_views`; columns before `first_column` can't be filtered."""
        self._table = table
        self._views: tuple[QTableView, ...] = (table, *mirrored_views)
        self._first_column = first_column
        self._row_visible = row_visible
        self._on_applied = on_applied
        self._rows = RowFilter()
        for view in self._views:
            header = view.horizontalHeader()
            header.setContextMenuPolicy(Qt.CustomContextMenu)
            header.setToolTip("Right-click a column header to filter")
            header.customContextMenuRequested.connect(lambda pos, h=header: self._open_for(h, pos))

    def is_active(self) -> bool:
        return self._rows.is_active()

    def reset(self) -> None:
        self._rows.clear()
        self._refresh_marks()
        self.apply()

    def apply(self) -> None:
        for row in range(self._table.rowCount()):
            visible = self._rows.matches(self._cells(row)) and (
                self._row_visible is None or self._row_visible(row)
            )
            for view in self._views:
                view.setRowHidden(row, not visible)
        if self._on_applied is not None:
            self._on_applied()

    def column_values(self, column: int) -> list[str]:
        return sorted({self._text(row, column) for row in range(self._table.rowCount())}, key=str.casefold)

    def _text(self, row: int, column: int) -> str:
        item = self._table.item(row, column)
        return item.text() if item else ""

    def _cells(self, row: int) -> list[str]:
        return [self._text(row, column) for column in range(self._table.columnCount())]

    def _open_for(self, header: QHeaderView, pos) -> None:
        column = header.logicalIndexAt(pos)
        if column < self._first_column:
            return
        title = self._title(column)
        dialog = ColumnFilterDialog(title, self.column_values(column), self._rows.get(column), self._table.window())
        dialog.move(header.mapToGlobal(pos))
        if dialog.exec():
            self.set_column_filter(column, dialog.result_filter())

    def set_column_filter(self, column: int, column_filter) -> None:
        self._rows.set(column, column_filter)
        self._refresh_marks()
        self.apply()

    def _title(self, column: int) -> str:
        return self._table.horizontalHeaderItem(column).text().removesuffix(_MARK)

    def _refresh_marks(self) -> None:
        for column in range(self._first_column, self._table.columnCount()):
            item = self._table.horizontalHeaderItem(column)
            title = item.text().removesuffix(_MARK)
            item.setText(title + _MARK if self._rows.is_active(column) else title)
