"""Editable variant table: displays rows, tracks their sheet row numbers and detects user edits.

Clipboard, search, column filters, the context menu and the frozen leading columns are separate classes wired up here.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QApplication, QTableWidget, QTableWidgetItem

from autohub.core.variant_choices import VARIANT_CHOICES
from autohub.core.webflow_fields import GENERAL_OPTION_COLUMNS
from autohub.core.variant_schema import VARIANT_FIELD_LABELS, VARIANT_FIELD_ORDER
from autohub.modules.home.choice_delegate import ChoiceDelegate, MultiChoiceDelegate
from autohub.modules.home.column_limits import ColumnLimits
from autohub.modules.home.frozen_columns import FrozenColumns
from autohub.ui.hover_cursor import HoverCursor
from autohub.ui.webflow_link_delegate import WebFlowLinkContextMenu, format_webflow_link_item, open_webflow_link
from autohub.modules.home.table_actions import TableActions
from autohub.modules.home.table_clipboard import TableClipboard
from autohub.modules.home.table_filter import TableFilter
from autohub.modules.home.table_search import TableSearch

# "No." + "Part Number" (and the WebFlow link, when shown) stay visible while the other columns scroll horizontally.
_FROZEN_COLUMNS = 2


class VariantTable(QTableWidget):
    #: emitted only for user edits, never while `populate` fills the table.
    userEdited = Signal()

    def __init__(self):
        super().__init__(0, 2 + len(VARIANT_FIELD_ORDER))
        self._link_column = 1 + len(VARIANT_FIELD_ORDER)
        self.setHorizontalHeaderLabels(
            ["No."] + [VARIANT_FIELD_LABELS[column] for column in VARIANT_FIELD_ORDER] + ["WebFlow Link"]
        )
        self.setColumnHidden(self._link_column, True)
        self.cellDoubleClicked.connect(self._open_link)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setMinimumHeight(160)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        #: Excel row per table row (None means "not yet in the sheet", insert on update).
        self._row_numbers: list[int | None] = []
        self._webflow_option_choices: dict[str, tuple[str, ...]] = {}
        self.itemChanged.connect(lambda _item: self.userEdited.emit())

        for col, column_name in enumerate(VARIANT_FIELD_ORDER):
            if column_name in VARIANT_CHOICES:
                self.setItemDelegateForColumn(col + 1, ChoiceDelegate(VARIANT_CHOICES[column_name], self))

        self._limits = ColumnLimits(self)
        self._frozen = FrozenColumns(self, _FROZEN_COLUMNS, extra=(self._link_column,))
        self._frozen.set_hidden(self._link_column, True)
        self._link_context_menu = WebFlowLinkContextMenu.for_table(
            self, (self._link_column,), (self._frozen.view,),
        )
        self._frozen.view.doubleClicked.connect(
            lambda index: self._open_link(index.row(), index.column())
        )
        self._link_cursor = HoverCursor((self, self._frozen.view), self._is_link_cell)
        self._clipboard = TableClipboard(self)
        self._search = TableSearch(self, self._clipboard.set_cell_text)
        self._filter = TableFilter(self, (self._frozen.view,))
        self._find_dialog = None
        self._actions = TableActions(self, self._clipboard, self.show_find_dialog, (self._frozen.view,))

    # -- Rows ------------------------------------------------------------------

    def populate(self, variants: list[dict]) -> None:
        self._filter.reset()
        self._row_numbers = [variant.get("_row") for variant in variants]
        self.blockSignals(True)
        self.setRowCount(len(variants))
        for row, values in enumerate(variants):
            no_item = QTableWidgetItem(str(row + 1))
            no_item.setFlags(no_item.flags() & ~Qt.ItemIsEditable)
            self.setItem(row, 0, no_item)
            for col, column_name in enumerate(VARIANT_FIELD_ORDER):
                value = values.get(column_name, "")
                if isinstance(value, float) and value.is_integer():
                    value = int(value)  # COM returns 159 as 159.0
                item = QTableWidgetItem("" if value is None else str(value))
                self.setItem(row, col + 1, item)
            self._set_link_item(row, values.get("_webflow_link") or "")
        self.blockSignals(False)
        self._limits.apply()
        self._frozen.update_geometry()

    def set_webflow_link_visible(self, visible: bool) -> None:
        self._frozen.set_hidden(self._link_column, not visible)
        if visible:
            self._limits.apply()
            self.setColumnWidth(self._link_column, max(self.columnWidth(self._link_column), 110))

    def set_webflow_option_choices(self, choices: dict) -> None:
        """Install multi-select editors for General-info columns with cached WebFlow options."""
        if not isinstance(choices, dict):
            choices = {}
        self._webflow_option_choices = {
            key: tuple(dict.fromkeys(value.strip() for value in values if isinstance(value, str) and value.strip()))
            for key, values in choices.items()
            if key in GENERAL_OPTION_COLUMNS.values() and isinstance(values, (list, tuple))
        }
        for column, key in GENERAL_OPTION_COLUMNS.items():
            index = VARIANT_FIELD_ORDER.index(column) + 1
            options = self._webflow_option_choices.get(key, ())
            self.setItemDelegateForColumn(index, MultiChoiceDelegate(options, self) if options else None)

    def set_webflow_links(self, links: dict[str, str]) -> None:
        part_column = 1 + VARIANT_FIELD_ORDER.index("J")
        blocked = self.blockSignals(True)
        try:
            for row in range(self.rowCount()):
                part = self.item(row, part_column)
                if part is not None and part.text() in links:
                    self._set_link_item(row, links[part.text()])
        finally:
            self.blockSignals(blocked)

    def set_webflow_numbers(self, numbers: dict[str, dict[str, str]]) -> None:
        part_column = 1 + VARIANT_FIELD_ORDER.index("J")
        blocked = self.blockSignals(True)
        try:
            for row in range(self.rowCount()):
                part = self.item(row, part_column)
                for key, value in numbers.get(part.text() if part else "", {}).items():
                    column = 1 + VARIANT_FIELD_ORDER.index(key)
                    item = self.item(row, column)
                    if item is not None:
                        item.setText(value)
        finally:
            self.blockSignals(blocked)

    def _set_link_item(self, row: int, link: str) -> None:
        """The link column is read-only: it shows "WF<number>" and opens on double-click."""
        item = QTableWidgetItem()
        format_webflow_link_item(item, link)
        if link:  # looks like a link
            font = item.font()
            font.setUnderline(True)
            item.setFont(font)
            item.setForeground(QApplication.palette().link())
        self.setItem(row, self._link_column, item)

    def _is_link_cell(self, index) -> bool:
        return index.isValid() and index.column() == self._link_column and bool(index.data(Qt.UserRole))

    def _open_link(self, row: int, column: int) -> None:
        item = self.item(row, column)
        link = item.data(Qt.UserRole) if column == self._link_column and item else ""
        if link:
            open_webflow_link(link)

    def clear_rows(self) -> None:
        self._filter.reset()
        self._row_numbers = []
        self.blockSignals(True)
        self.setRowCount(0)
        self.blockSignals(False)
        self._frozen.update_geometry()

    def selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.selectedIndexes()})

    def remove_rows(self, rows: list[int]) -> None:
        """Removes the given table rows (not signalling an edit) and renumbers the rest."""
        self.blockSignals(True)
        for row in sorted(set(rows), reverse=True):
            self.removeRow(row)
            if row < len(self._row_numbers):
                del self._row_numbers[row]
        for row in range(self.rowCount()):
            self.item(row, 0).setText(str(row + 1))
        self.blockSignals(False)
        self._frozen.update_geometry()

    def read(self) -> list[dict]:
        variants = []
        for row in range(self.rowCount()):
            values = {"_row": self._row_numbers[row] if row < len(self._row_numbers) else None}
            for col, column_name in enumerate(VARIANT_FIELD_ORDER):
                item = self.item(row, col + 1)
                values[column_name] = item.text() if item else ""
            link_item = self.item(row, self._link_column)
            if link_item is not None and link_item.data(Qt.UserRole):
                values["_webflow_link"] = link_item.data(Qt.UserRole)
            variants.append(values)
        return variants

    def set_column_filter(self, column: int, column_filter) -> None:
        self._filter.set_column_filter(column, column_filter)

    # -- Editing operations, delegated -------------------------------------------

    def copy_selection(self) -> None:
        self._clipboard.copy_selection()

    def paste_clipboard(self) -> int:
        return self._clipboard.paste()

    def delete_selection(self) -> int:
        return self._clipboard.delete_selection()

    def find_next(self, needle: str, match_case: bool = False) -> bool:
        return self._search.find_next(needle, match_case)

    def replace_current(self, needle: str, replacement: str, match_case: bool = False) -> bool:
        return self._search.replace_current(needle, replacement, match_case)

    def replace_all(self, needle: str, replacement: str, match_case: bool = False) -> int:
        return self._search.replace_all(needle, replacement, match_case)

    def show_find_dialog(self, replace: bool) -> None:
        from autohub.modules.home.find_replace_dialog import FindReplaceDialog

        if self._find_dialog is None:
            self._find_dialog = FindReplaceDialog(self, self.window())
        self._find_dialog.open_for(replace)

    # -- Qt hooks for the frozen overlay ---------------------------------------------

    def updateGeometries(self) -> None:
        super().updateGeometries()
        if hasattr(self, "_frozen"):  # fires during base __init__, before the overlay exists
            self._frozen.update_geometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._frozen.update_geometry()

    def moveCursor(self, cursor_action, modifiers):
        current = super().moveCursor(cursor_action, modifiers)
        self._frozen.keep_cursor_visible(cursor_action, current)
        return current

    def scrollTo(self, index, hint=QAbstractItemView.EnsureVisible) -> None:
        # Frozen cells are always visible; scrolling for them would only jerk the table.
        if not self._frozen.is_frozen(index.column()):
            super().scrollTo(index, hint)
