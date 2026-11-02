"""Variant checklist with event filter; the selection is cleared whenever the variants are reloaded."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from autohub.core.latest_event import NO_EVENT, latest_event
from autohub.core.webflow_numbers import NUMBER_FIELDS
from autohub.ui.link_label import LinkLabel

_ALL_EVENTS = "All events"
_NO_EVENT = NO_EVENT
_HEADERS = (
    "Select", "Part Number", "Family Name", "FSWID Project Version", "FSWID Program Version", "WebFlow Link",
    "SW Part Number", "ECR Number",
)


class CreationTable(QTableWidget):
    def __init__(self):
        super().__init__(0, len(_HEADERS))
        self.setHorizontalHeaderLabels(_HEADERS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.horizontalHeader().setMinimumSectionSize(1)
        self.horizontalHeader().setResizeContentsPrecision(-1)
        self.horizontalHeader().setStretchLastSection(False)

    def fit_columns(self) -> None:
        header = self.horizontalHeader()
        widths = [
            max(header.sectionSizeHint(column), self.sizeHintForColumn(column))
            for column in range(self.columnCount())
        ]
        widths[1] = max(widths[1], max(widths[:1] + widths[2:]) + 24)
        available = self.viewport().width()
        total = sum(widths)
        if total > available:
            widths = [int(width * available / total) for width in widths]
        widths[1] += available - sum(widths)
        for column, width in enumerate(widths):
            self.setColumnWidth(column, width)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_columns()


class VariantChecklist(QWidget):
    selectionChanged = Signal(int, int)

    def __init__(self):
        super().__init__()
        # Only the latest variant per part number is kept by MasterSheet; this is the
        # full set, independent of whatever the event filter is currently showing.
        self._variants: list[dict] = []
        self._checkboxes: dict[str, QCheckBox] = {}
        self._links: dict[str, str] = {}  # part number -> WebFlow job link
        self._selected: set[str] = set()

        self._event_filter = QComboBox()
        self._event_filter.addItem(_ALL_EVENTS)
        self._event_filter.currentTextChanged.connect(self._apply_filter)
        self._event_filter.activated.connect(self._on_event_chosen)
        self._event_chosen = False  # once the user picks an event, reloads keep it
        self._select_visible_btn = QPushButton("Select visible")
        self._select_visible_btn.setEnabled(False)
        self._select_visible_btn.setToolTip("Select every variant in the current event filter.")
        self._select_visible_btn.clicked.connect(lambda: self._set_all(True))
        self._clear_selection_btn = QPushButton("Clear selection")
        self._clear_selection_btn.setEnabled(False)
        self._clear_selection_btn.clicked.connect(self.clear_selection)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.addWidget(QLabel("Event:"))
        toolbar.addWidget(self._event_filter)
        self._event_filter.setMinimumWidth(180)
        toolbar.addStretch(1)
        toolbar.addWidget(self._select_visible_btn)
        toolbar.addWidget(self._clear_selection_btn)

        self._table = CreationTable()
        self._table.setShowGrid(True)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setMinimumHeight(150)
        self._empty_label = QLabel("Load variants from a Master Sheet on Home, or create them from all three files.")
        self._empty_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self._table)
        layout.addWidget(self._empty_label)

    @property
    def has_variants(self) -> bool:
        return bool(self._variants)

    @property
    def variant_count(self) -> int:
        return len(self._variants)

    def selected_variants(self) -> list[dict]:
        return [v for v in self._variants if v["part_number"] in self._selected]

    def has_link(self, part_number: str) -> bool:
        return bool(self._links.get(part_number))

    def clear_selection(self) -> None:
        """Unchecks every variant, including ones hidden by the event filter."""
        self._selected.clear()
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(False)
        self._emit_selection_changed()

    def set_variants(self, variants: list[dict]) -> None:
        """Shows a fresh variant list; any previous selection is cleared."""
        self._variants = variants
        self._selected.clear()
        self._links = {
            variant["part_number"]: variant["webflow_link"]
            for variant in variants
            if variant.get("webflow_link")
        }

        events = sorted({v.get("event") or _NO_EVENT for v in variants})
        self._event_filter.blockSignals(True)
        current = self._event_filter.currentText() if self._event_chosen else (latest_event(variants) or _ALL_EVENTS)
        self._event_filter.clear()
        self._event_filter.addItem(_ALL_EVENTS)
        self._event_filter.addItems(events)
        self._event_filter.setCurrentText(current if current in events or current == _ALL_EVENTS else _ALL_EVENTS)
        self._event_filter.blockSignals(False)

        self._apply_filter()

    def _on_event_chosen(self, _index: int) -> None:
        self._event_chosen = True

    def _apply_filter(self, *_args) -> None:
        self._checkboxes.clear()
        self._table.setRowCount(0)

        event_filter = self._event_filter.currentText() or _ALL_EVENTS
        if event_filter == _ALL_EVENTS:
            filtered = self._variants
        else:
            filtered = [v for v in self._variants if (v.get("event") or _NO_EVENT) == event_filter]

        self._empty_label.setVisible(not filtered)
        self._table.setRowCount(len(filtered))
        if filtered:
            for row, variant in enumerate(filtered):
                part_number = variant["part_number"]
                checkbox = QCheckBox()
                checkbox.setAccessibleName(f"Select {part_number}")
                checkbox.setChecked(part_number in self._selected)
                checkbox.toggled.connect(lambda checked, pn=part_number: self._on_toggled(pn, checked))
                self._checkboxes[part_number] = checkbox
                container = QWidget()
                layout = QHBoxLayout(container)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(checkbox, alignment=Qt.AlignCenter)
                self._table.setCellWidget(row, 0, container)
                ecu = variant.get("ecu", {})
                for column, value in enumerate((
                    part_number,
                    ecu.get("family_name") or variant["ecu_type"],
                    ecu.get("project_version", ""),
                    ecu.get("program_version", ""),
                ), start=1):
                    item = QTableWidgetItem(str(value or ""))
                    item.setTextAlignment(Qt.AlignCenter)
                    self._table.setItem(row, column, item)
                link = self._links.get(part_number, "")
                if link:
                    label = LinkLabel(link, link)
                    label.setAlignment(Qt.AlignCenter)
                    self._table.setCellWidget(row, 5, label)
                for column, (_name, (_sheet_column, key)) in enumerate(NUMBER_FIELDS.items(), start=6):
                    item = QTableWidgetItem(str(variant.get("hardware", {}).get(key) or ""))
                    item.setTextAlignment(Qt.AlignCenter)
                    self._table.setItem(row, column, item)
        self._table.fit_columns()
        self._emit_selection_changed()

    def set_numbers(self, numbers: dict[str, dict[str, str]]) -> None:
        for variant in self._variants:
            values = numbers.get(variant["part_number"], {})
            for column, key in NUMBER_FIELDS.values():
                if column in values:
                    variant.setdefault("hardware", {})[key] = values[column]
        self._apply_filter()

    def set_links(self, links: dict[str, str]) -> None:
        """Shows the WebFlow job link of the variants that just got a job."""
        self._links.update(links)
        for variant in self._variants:
            if variant["part_number"] in links:
                variant["webflow_link"] = links[variant["part_number"]]
        self._apply_filter()

    def _on_toggled(self, part_number: str, checked: bool) -> None:
        if checked:
            self._selected.add(part_number)
        else:
            self._selected.discard(part_number)
        self._emit_selection_changed()

    def _set_all(self, checked: bool) -> None:
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(checked)
        self._emit_selection_changed()

    def _emit_selection_changed(self) -> None:
        self._select_visible_btn.setEnabled(any(not checkbox.isChecked() for checkbox in self._checkboxes.values()))
        self._clear_selection_btn.setEnabled(bool(self._selected))
        self.selectionChanged.emit(len(self._selected), len(self._variants))
