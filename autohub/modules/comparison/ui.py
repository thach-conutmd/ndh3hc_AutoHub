"""Multi-variant comparison workspace; browser work runs off the UI thread."""
from __future__ import annotations

from copy import deepcopy
from threading import Event

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.settings import SettingsStore
from autohub.core.webflow_numbers import NUMBER_FIELDS
from autohub.core.workers import FunctionWorker
from autohub.ui.theme import set_muted

from .comparison import ComparisonRow, Status
from .matching import validate_link
from .progress import ComparisonProgressDialog
from .service import ComparisonService, VariantResult
from .xml_parser import ParameterValue

_TARGET_HEADERS = ("Variant", "Parameter", "Master", "Base", "Target", "Status")
_VARIANT_HEADERS = ("Select", "Variant", "WebFlow", "Base WebFlow Link", "Status", "Error")


def _display(value: ParameterValue) -> str:
    if value in (None, "", (), "---"):
        return "(missing)"
    return " | ".join(value) if isinstance(value, tuple) else value


class ComparisonWidget(QWidget):
    _progress = Signal(int, str, str)

    def __init__(
        self, dialogs: Dialogs | None = None, service: ComparisonService | None = None,
        settings: SettingsStore | None = None,
    ):
        super().__init__()
        self._dialogs = dialogs or QtDialogs(self)
        self._service = service
        self._settings = settings
        self._variants: list[dict] = []
        self._rows: list[tuple[str, str, ComparisonRow]] = []
        self._worker: FunctionWorker | None = None
        self._running = False
        self._revision = 0
        self._run_revision = 0
        self._run_rows: list[int] = []
        self._base_mode = False
        self._base_variants: set[tuple[str, str]] = set()
        self._cancel = Event()
        self._progress_dialog: ComparisonProgressDialog | None = None

        title = QLabel("Comparison")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        subtitle = QLabel(
            "Select linked variants to export WebFlow XML automatically and compare with Master. "
            "Jobs are processed sequentially using the existing WebFlow browser and authentication."
        )
        subtitle.setWordWrap(True)
        set_muted(subtitle, True)
        self._variants_table = QTableWidget(0, len(_VARIANT_HEADERS))
        self._variants_table.setHorizontalHeaderLabels(_VARIANT_HEADERS)
        self._variants_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked
        )
        self._variants_table.setTextElideMode(Qt.ElideRight)
        self._variants_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._variants_table.verticalHeader().setVisible(False)
        self._variants_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for column, width in enumerate((55, 130, 240, 240, 125, 180)):
            self._variants_table.setColumnWidth(column, width)
        self._variants_table.setMaximumHeight(160)
        self._select_all_btn = QPushButton("Select all")
        self._clear_selection_btn = QPushButton("Clear selection")
        self._compare_btn = QPushButton("Compare selected")
        sources = QHBoxLayout()
        sources.addWidget(self._select_all_btn)
        sources.addWidget(self._clear_selection_btn)
        sources.addStretch(1)
        sources.addWidget(self._compare_btn)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search parameters, values, variants or status...")
        self._variant_filter = QComboBox()
        self._status_filter = QComboBox()
        self._deviations = QCheckBox("Deviations only")
        self._deviations.setToolTip("Hide target values matching Master, including matches to both Master and Base.")
        filters = QHBoxLayout()
        filters.addWidget(self._search, 1)
        filters.addWidget(self._variant_filter)
        filters.addWidget(self._status_filter)
        filters.addWidget(self._deviations)
        self._table = QTableWidget(0, len(_TARGET_HEADERS))
        self._table.setHorizontalHeaderLabels(_TARGET_HEADERS)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._summary = QLabel("Load a Master Sheet on Home and select linked variants.")
        self._summary.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._variants_table)
        layout.addLayout(sources)
        layout.addLayout(filters)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._summary)
        self._select_all_btn.clicked.connect(self._select_all)
        self._clear_selection_btn.clicked.connect(self._clear_selection)
        self._variants_table.itemChanged.connect(self._selection_changed)
        self._compare_btn.clicked.connect(self._compare)
        self._search.textChanged.connect(self._apply_filters)
        self._variant_filter.currentIndexChanged.connect(self._apply_filters)
        self._status_filter.currentTextChanged.connect(self._apply_filters)
        self._deviations.toggled.connect(self._apply_filters)
        self._progress.connect(self._on_progress)
        self._refresh_variants()

    def set_variants(self, variants: list[dict]) -> None:
        self._variants = deepcopy(variants)
        self._refresh_variants()

    def set_webflow_links(self, links: dict[str, str]) -> None:
        for variant in self._variants:
            if variant["part_number"] in links:
                variant["webflow_link"] = links[variant["part_number"]]
        self._refresh_variants()

    def set_webflow_numbers(self, numbers: dict[str, dict[str, str]], persisted: bool = True) -> None:
        for variant in self._variants:
            values = numbers.get(variant["part_number"], {})
            for column, key in NUMBER_FIELDS.values():
                if column in values:
                    variant.setdefault("hardware", {})[key] = values[column]
        self._refresh_variants()

    def _refresh_variants(self) -> None:
        previous = {
            self._variants_table.item(row, 0).data(Qt.UserRole + 1): (
                self._variants_table.item(row, 0).checkState(),
                self._variants_table.item(row, 3).text(),
            )
            for row in range(self._variants_table.rowCount())
        }
        self._variants_table.blockSignals(True)
        self._variants_table.setRowCount(0)
        for index, variant in enumerate(self._variants):
            try:
                validate_link(str(variant.get("webflow_link") or ""))
            except ValueError:
                continue
            row = self._variants_table.rowCount()
            self._variants_table.insertRow(row)
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            software = str(variant.get("hardware", {}).get("software_part_number") or "")
            identity = (str(variant["part_number"]), software, str(variant["webflow_link"]))
            checked, base_link = previous.get(identity, (Qt.Unchecked, ""))
            checkbox.setCheckState(checked)
            checkbox.setData(Qt.UserRole, index)
            checkbox.setData(Qt.UserRole + 1, identity)
            self._variants_table.setItem(row, 0, checkbox)
            for column, text in enumerate((identity[0], identity[2], base_link, "Pending", ""), 1):
                item = QTableWidgetItem(str(text))
                if column != 3:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setToolTip(str(text))
                self._variants_table.setItem(row, column, item)
        self._variants_table.blockSignals(False)
        self._source_changed()

    def _selected_rows(self) -> list[int]:
        return [
            row for row in range(self._variants_table.rowCount())
            if self._variants_table.item(row, 0).checkState() == Qt.Checked
        ]

    def _select_all(self) -> None:
        self._set_selection(Qt.Checked)

    def _clear_selection(self) -> None:
        self._set_selection(Qt.Unchecked)

    def _set_selection(self, state: Qt.CheckState) -> None:
        self._variants_table.blockSignals(True)
        for row in range(self._variants_table.rowCount()):
            self._variants_table.item(row, 0).setCheckState(state)
        self._variants_table.blockSignals(False)
        self._source_changed()

    def _selection_changed(self, item: QTableWidgetItem) -> None:
        if item.column() in (0, 3):
            self._variants_table.blockSignals(True)
            item.setToolTip(item.text())
            self._variants_table.blockSignals(False)
            self._source_changed()

    def _source_changed(self, *_args) -> None:
        self._revision += 1
        self._rows = []
        self._table.setRowCount(0)
        self._summary.setText("Select linked variants, then Compare selected.")
        self._base_variants = {
            tuple(self._variants_table.item(row, 0).data(Qt.UserRole + 1)[:2])
            for row in self._selected_rows() if self._variants_table.item(row, 3).text().strip()
        }
        self._base_mode = bool(self._base_variants)
        self._table.setColumnCount(len(_TARGET_HEADERS))
        self._table.setHorizontalHeaderLabels(_TARGET_HEADERS)
        self._variant_filter.blockSignals(True)
        self._variant_filter.clear()
        self._variant_filter.addItem("All variants", None)
        self._variant_filter.blockSignals(False)
        self._status_filter.blockSignals(True)
        self._status_filter.clear()
        self._status_filter.addItem("All statuses")
        statuses = (
            tuple(Status)
            if self._base_mode else
            (Status.MATCH, Status.VALUE_MISMATCH, Status.MISSING_IN_MASTER, Status.MISSING_IN_WEBFLOW)
        )
        self._status_filter.addItems([status.value for status in statuses])
        self._status_filter.blockSignals(False)
        self._set_running(self._running)

    def _set_running(self, running: bool) -> None:
        self._running = running
        self._variants_table.setEnabled(not running)
        self._select_all_btn.setEnabled(not running and self._variants_table.rowCount() > 0)
        self._clear_selection_btn.setEnabled(not running and bool(self._selected_rows()))
        self._compare_btn.setEnabled(not running and bool(self._selected_rows()))

    def _compare(self) -> None:
        if self._running:
            return
        if self._service is None:
            self._dialogs.error("Comparison", "The WebFlow comparison service is not configured.")
            return
        rows = self._selected_rows()
        if not rows:
            return
        selected = deepcopy([
            self._variants[self._variants_table.item(row, 0).data(Qt.UserRole)] for row in rows
        ])
        for row, variant in zip(rows, selected):
            variant["base_webflow_link"] = self._variants_table.item(row, 3).text().strip()
        masters = deepcopy(self._variants)
        saved = self._settings.load() if self._settings is not None else {}
        connection = {"driver_path": ""}
        if saved.get("webflow_base_url"):
            connection["base_url"] = str(saved["webflow_base_url"]).strip()
        self._source_changed()
        self._run_rows = rows
        self._run_revision = self._revision
        self._set_running(True)
        for row in rows:
            self._set_variant_status(row, "Pending", "")
        self._summary.setText(f"Comparing {len(rows)} selected variants...")
        self._cancel = Event()
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog.deleteLater()
        self._progress_dialog = ComparisonProgressDialog([
            str(variant["part_number"])
            for variant in selected
        ], self)
        self._progress_dialog.cancel_requested.connect(self._cancel.set)
        self._progress_dialog.show()
        self._worker = FunctionWorker(
            lambda: self._service.run(
                selected, masters, connection=connection, progress=self._progress.emit,
                cancelled=self._cancel.is_set,
            ),
            self,
        )
        self._worker.finished_ok.connect(self._finish)
        self._worker.finished_error.connect(self._fail)
        self._worker.start()

    def _set_variant_status(self, row: int, status: str, error: str) -> None:
        self._variants_table.item(row, 4).setText(status)
        self._variants_table.item(row, 5).setText(error)
        self._variants_table.item(row, 5).setToolTip(error)

    def _on_progress(self, index: int, status: str, error: str) -> None:
        if self._progress_dialog is not None:
            self._progress_dialog.update_status(index, status, error)
        if self._run_revision != self._revision:
            return
        if 0 <= index < len(self._run_rows):
            self._set_variant_status(self._run_rows[index], status, error)

    def _finish(self, results: list[VariantResult]) -> None:
        if self._worker is not None:
            self._worker.wait()
            self._worker.deleteLater()
            self._worker = None
        self._set_running(False)
        if self._progress_dialog is not None:
            self._progress_dialog.finish()
        if self._run_revision != self._revision:
            self._summary.setText("Master data changed during comparison. Select variants and compare again.")
            return
        self._rows = [(result.variant, result.software, row) for result in results for row in result.rows]
        self._render_results()
        failed = sum(bool(result.error) for result in results)
        cancelled = sum(result.cancelled for result in results)
        self._summary.setText(
            f"{len(results) - failed - cancelled} completed; {failed} failed. "
            + (f"{cancelled} cancelled. " if cancelled else "") + self._summary.text()
        )

    def _fail(self, error: str) -> None:
        if self._worker is not None:
            self._worker.wait()
            self._worker.deleteLater()
            self._worker = None
        self._set_running(False)
        if self._progress_dialog is not None:
            self._progress_dialog.finish(error)
        if self._run_revision == self._revision:
            for row in self._run_rows:
                self._set_variant_status(row, "Failed", error)
        self._summary.setText(f"Comparison failed: {error}")
        self._dialogs.error("Comparison", error)

    def _render_results(self) -> None:
        self._variant_filter.blockSignals(True)
        self._variant_filter.clear()
        self._variant_filter.addItem("All variants", None)
        for part in dict.fromkeys(part for part, _, _ in self._rows):
            self._variant_filter.addItem(part, part)
        self._variant_filter.blockSignals(False)
        self._table.setRowCount(len(self._rows))
        for index, (part, software, row) in enumerate(self._rows):
            values = (
                (part, row.parameter, _display(row.master),
                 _display(row.base) if (part, software) in self._base_variants else "",
                 _display(row.target), row.status.value)
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self._table.setItem(index, column, item)
        self._table.resizeColumnsToContents()
        for column in range(self._table.columnCount()):
            self._table.setColumnWidth(column, min(300, self._table.columnWidth(column)))
        self._apply_filters()

    def _apply_filters(self, *_args) -> None:
        search = self._search.text().strip().casefold()
        status = self._status_filter.currentText()
        variant = self._variant_filter.currentData()
        visible = 0
        for index, (part, software, row) in enumerate(self._rows):
            text = " ".join(self._table.item(index, column).text() for column in range(self._table.columnCount()))
            show = (
                (not search or search in text.casefold())
                and (variant is None or variant == part)
                and (status == "All statuses" or status == row.status.value)
                and (not self._deviations.isChecked() or row.deviation)
            )
            self._table.setRowHidden(index, not show)
            visible += int(show)
        self._summary.setText(
            f"{visible} / {len(self._rows)} parameters shown; "
            f"{sum(row.deviation for _, _, row in self._rows)} deviations from Master."
        )

    def confirm_leave(self) -> bool:
        if self._running:
            self._dialogs.info("Comparison", "Wait for the current XML exports and comparisons to finish.")
            return False
        return True

    def shutdown(self) -> None:
        self._cancel.set()
        if self._worker is not None:
            self._worker.wait()
