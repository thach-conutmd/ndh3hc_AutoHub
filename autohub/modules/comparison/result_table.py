"""Comparison result table with Home's shared frozen-column overlay."""
from PySide6.QtWidgets import QAbstractItemView, QTableWidget

from autohub.modules.home.frozen_columns import FrozenColumns


class ResultTable(QTableWidget):
    def __init__(self, rows: int, columns: int):
        super().__init__(rows, columns)
        self.frozen = FrozenColumns(self, 1)
        self.frozen.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.frozen.view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.frozen.view.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def updateGeometries(self) -> None:
        super().updateGeometries()
        if hasattr(self, "frozen"):
            self.frozen.update_geometry()

    def moveCursor(self, action, modifiers):
        current = super().moveCursor(action, modifiers)
        self.frozen.keep_cursor_visible(action, current)
        return current

    def scrollTo(self, index, hint=QAbstractItemView.EnsureVisible) -> None:
        if not hasattr(self, "frozen") or not self.frozen.is_frozen(index.column()):
            super().scrollTo(index, hint)
