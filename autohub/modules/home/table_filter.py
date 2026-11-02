"""Shared per-column filtering with native header icons and click/context-menu access."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette
from PySide6.QtWidgets import QHeaderView, QTableView, QTableWidget

from autohub.config import ICONS_DIR
from autohub.modules.home.filter_dialog import ColumnFilterDialog
from autohub.modules.home.row_filter import RowFilter


class TableFilter(QObject):
    def __init__(
        self, table: QTableWidget, mirrored_views: tuple[QTableView, ...] = (), first_column: int = 1,
        row_visible: Callable[[int], bool] | None = None,
        on_applied: Callable[[], None] | None = None,
    ):
        """Rows are hidden in `table` and each of `mirrored_views`; columns before `first_column` can't be filtered."""
        super().__init__(table)
        self._table = table
        self._views: tuple[QTableView, ...] = (table, *mirrored_views)
        self._first_column = first_column
        self._row_visible = row_visible
        self._on_applied = on_applied
        self._rows = RowFilter()
        for view in self._views:
            header = view.horizontalHeader()
            header.setIconSize(QSize(14, 14))
            header.setSectionsClickable(True)
            header.setContextMenuPolicy(Qt.CustomContextMenu)
            header.customContextMenuRequested.connect(lambda pos, h=header: self._open_for(h, pos))
            header.sectionClicked.connect(lambda column, h=header: self._open_column(h, column))
        table.installEventFilter(self)
        self._refresh_icons()

    def is_active(self) -> bool:
        return self._rows.is_active()

    def reset(self) -> None:
        self._rows.clear()
        self._refresh_icons()
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
        self._open_column(header, column, pos)

    def _open_column(self, header: QHeaderView, column: int, pos: QPoint | None = None) -> None:
        if not self._first_column <= column < self._table.columnCount():
            return
        if pos is None:
            pos = QPoint(header.sectionViewportPosition(column), header.height())
        title = self._title(column)
        dialog = ColumnFilterDialog(title, self.column_values(column), self._rows.get(column), self._table.window())
        dialog.move(header.mapToGlobal(pos))
        if dialog.exec():
            self.set_column_filter(column, dialog.result_filter())

    def set_column_filter(self, column: int, column_filter) -> None:
        self._rows.set(column, column_filter)
        self._refresh_icons()
        self.apply()

    def _title(self, column: int) -> str:
        return self._table.horizontalHeaderItem(column).text()

    def _icon(self, active: bool) -> QIcon:
        palette = self._table.palette()
        color = palette.color(QPalette.Highlight if active else QPalette.PlaceholderText)
        pixmap = QIcon(str(ICONS_DIR / "filter.svg")).pixmap(QSize(28, 28))
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), color)
        painter.end()
        return QIcon(pixmap)

    def _refresh_icons(self) -> None:
        icons = {active: self._icon(active) for active in (False, True)}
        for column in range(self._first_column, self._table.columnCount()):
            item = self._table.horizontalHeaderItem(column)
            active = self._rows.is_active(column)
            item.setIcon(icons[active])
            item.setToolTip("Filter active - click to modify" if active else f"Filter {item.text()}")

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.PaletteChange:
            self._refresh_icons()
        return super().eventFilter(watched, event)
