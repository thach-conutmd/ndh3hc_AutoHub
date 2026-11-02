"""Multi-variant comparison workspace; browser work runs off the UI thread."""
from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from threading import Event

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QPushButton, QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionButton, QStyleOptionViewItem,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from autohub.core.impl_update import ImplUpdate
from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.settings import SettingsStore
from autohub.core.webflow_environment import webflow_base_url
from autohub.core.webflow_links import is_link
from autohub.core.webflow_numbers import NUMBER_FIELDS
from autohub.core.workers import FunctionWorker
from autohub.modules.home.table_filter import TableFilter
from autohub.ui.theme import set_muted
from autohub.ui.hover_cursor import HoverCursor
from autohub.ui.webflow_link_delegate import WebFlowLinkDelegate, format_webflow_link_item

from .comparison import ComparisonRow, Status
from .impl_update import MasterImplUpdater, build_impl_update
from .matching import validate_link
from .report import build_report
from .review import Review
from .progress import ComparisonProgressDialog
from .service import ComparisonService, VariantResult
from .xml_parser import ParameterValue

_COMMENT_COLUMN = 6
_STATUS_COLUMN = 5
_TARGET_HEADERS = ("Variant", "Parameter", "Master", "Base", "Target", "Status", "Comment")
_VARIANT_HEADERS = ("Select", "Variant", "WebFlow", "Base WebFlow Link", "Status", "Error")


def _display(value: ParameterValue) -> str:
    if value in (None, "", (), "---"):
        return "(missing)"
    return " | ".join(value) if isinstance(value, tuple) else value


class _CenteredCheckDelegate(QStyledItemDelegate):
    def _centered_option(self, option, index):
        centered = QStyleOptionViewItem(option)
        self.initStyleOption(centered, index)
        style = centered.widget.style()
        indicator = style.subElementRect(QStyle.SE_ItemViewItemCheckIndicator, centered, centered.widget)
        centered.rect.translate(option.rect.center().x() - indicator.center().x(), 0)
        return centered

    def paint(self, painter, option, index) -> None:
        background = QStyleOptionViewItem(option)
        self.initStyleOption(background, index)
        background.features &= ~QStyleOptionViewItem.HasCheckIndicator
        background.widget.style().drawControl(QStyle.CE_ItemViewItem, background, painter, background.widget)
        centered = self._centered_option(option, index)
        indicator = QStyleOptionButton()
        indicator.rect = background.widget.style().subElementRect(
            QStyle.SE_ItemViewItemCheckIndicator, centered, background.widget,
        )
        indicator.state = option.state | (
            QStyle.State_On if index.data(Qt.CheckStateRole) == Qt.Checked.value else QStyle.State_Off
        )
        background.widget.style().drawPrimitive(
            QStyle.PE_IndicatorItemViewItemCheck, indicator, painter, background.widget,
        )

    def editorEvent(self, event, model, option, index) -> bool:
        return super().editorEvent(event, model, self._centered_option(option, index), index)


class ComparisonWidget(QWidget):
    _progress = Signal(int, str, str)
    #: asks Home to reload the Master Sheet after IMPL values were written.
    masterReloadRequested = Signal()

    def __init__(
        self, dialogs: Dialogs | None = None, service: ComparisonService | None = None,
        settings: SettingsStore | None = None, impl_updater: MasterImplUpdater | None = None,
    ):
        super().__init__()
        self._dialogs = dialogs or QtDialogs(self)
        self._service = service
        self._settings = settings
        self._impl_updater = impl_updater
        self._impl_updates: dict[str, ImplUpdate] = {}
        self._keep_results = False
        self._variants: list[dict] = []
        self._rows: list[tuple[str, str, ComparisonRow]] = []
        self._reviews: dict[tuple[str, str], Review] = {}
        self._worker: FunctionWorker | None = None
        self._running = False
        self._revision = 0
        self._run_revision = 0
        self._run_rows: list[int] = []
        self._base_variants: set[tuple[str, str]] = set()
        self._run_base: set[tuple[str, str]] = set()
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
        header = self._variants_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setResizeContentsPrecision(-1)
        for column in (0, 1, 2, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        for column in (3, 5):
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        self._check_delegate = _CenteredCheckDelegate(self._variants_table)
        self._variants_table.setItemDelegateForColumn(0, self._check_delegate)
        self._link_delegate = WebFlowLinkDelegate(self._variants_table, (2, 3))
        self._link_cursor = HoverCursor(
            (self._variants_table,),
            lambda index: index.isValid() and index.column() in (2, 3) and is_link(index.data(Qt.UserRole) or ""),
        )
        self._variants_table.setMaximumHeight(160)
        self._select_all_btn = QPushButton("Select all")
        self._clear_selection_btn = QPushButton("Clear selection")
        self._export_btn = QPushButton("Export Comparison")
        self._export_btn.setEnabled(False)
        self._impl_btn = QPushButton("Update Master Sheet")
        self._impl_btn.setToolTip("Write the exported Target values of successfully compared variants into the Master Sheet.")
        self._impl_btn.setEnabled(False)
        self._compare_btn = QPushButton("Compare selected")
        sources = QHBoxLayout()
        sources.addWidget(self._select_all_btn)
        sources.addWidget(self._clear_selection_btn)
        sources.addStretch(1)
        sources.addWidget(self._export_btn)
        sources.addWidget(self._impl_btn)
        sources.addWidget(self._compare_btn)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search parameters, values, variants or status...")
        self._variant_filter = QComboBox()
        self._variant_filter.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._variant_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._variant_filter.setMaximumWidth(420)
        self._variant_filter.view().setTextElideMode(Qt.ElideNone)
        self._status_filter = QComboBox()
        self._status_filter.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._status_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._deviations = QCheckBox("Deviations only")
        self._deviations.setToolTip("Hide target values matching Master, including matches to both Master and Base.")
        filters = QHBoxLayout()
        filters.addWidget(self._search, 1)
        filters.addWidget(self._variant_filter)
        filters.addWidget(self._status_filter)
        filters.addWidget(self._deviations)
        self._table = QTableWidget(0, len(_TARGET_HEADERS))
        self._table.setHorizontalHeaderLabels(_TARGET_HEADERS)
        self._table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._summary = QLabel("Load a Master Sheet on Home and select linked variants.")
        self._summary.setWordWrap(True)
        self._header_filter = TableFilter(
            self._table, first_column=0, row_visible=self._matches_global_filters,
            on_applied=self._update_filter_summary,
        )
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
        self._table.itemChanged.connect(self._comment_edited)
        self._table.customContextMenuRequested.connect(self._open_result_menu)
        self._compare_btn.clicked.connect(self._compare)
        self._export_btn.clicked.connect(self._export)
        self._impl_btn.clicked.connect(self._update_impl)
        self._search.textChanged.connect(self._apply_filters)
        self._variant_filter.currentIndexChanged.connect(self._apply_filters)
        self._status_filter.currentTextChanged.connect(self._apply_filters)
        self._deviations.toggled.connect(self._apply_filters)
        self._progress.connect(self._on_progress)
        self._refresh_variants()

    def set_variants(self, variants: list[dict]) -> None:
        keep, self._keep_results = self._keep_results, False
        self._variants = deepcopy(variants)
        self._refresh_variants(keep_results=keep)

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

    def _refresh_variants(self, keep_results: bool = False) -> None:
        previous = {
            self._variants_table.item(row, 0).data(Qt.UserRole + 1): (
                self._variants_table.item(row, 0).checkState(),
                self._variants_table.item(row, 3).data(Qt.UserRole) or "",
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
                if column in (2, 3):
                    format_webflow_link_item(item, str(text), editable=column == 3)
                self._variants_table.setItem(row, column, item)
        self._variants_table.blockSignals(False)
        if keep_results:
            self._source_changed()
        else:
            self._clear_results()

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
            if item.column() == 3:
                self._link_delegate.format_item(item)
            self._variants_table.blockSignals(False)
            self._source_changed()

    def _source_changed(self, *_args) -> None:
        if not self._rows:
            self._summary.setText("")
        self._set_running(self._running)

    def _clear_results(self) -> None:
        self._revision += 1
        self._rows = []
        self._reviews = {}
        self._impl_updates = {}
        self._base_variants = set()
        self._table.setRowCount(0)
        self._header_filter.reset()
        self._variant_filter.blockSignals(True)
        self._variant_filter.clear()
        self._variant_filter.addItem("All variants", None)
        self._variant_filter.blockSignals(False)
        self._size_variant_filter()
        self._fill_status_filter()
        self._source_changed()

    def _fill_status_filter(self) -> None:
        self._status_filter.blockSignals(True)
        self._status_filter.clear()
        self._status_filter.addItem("All statuses")
        statuses = (
            tuple(Status)
            if self._base_variants else
            (Status.MATCH, Status.VALUE_MISMATCH, Status.MISSING_IN_MASTER, Status.MISSING_IN_WEBFLOW)
        )
        self._status_filter.addItems([status.value for status in statuses])
        self._status_filter.blockSignals(False)

    def _reviewer(self) -> str:
        saved = self._settings.load() if self._settings is not None else {}
        name = str(saved.get("change_engineer", "")).strip()
        return name or os.environ.get("USERNAME") or os.environ.get("USER") or ""

    def _export(self) -> None:
        if self._running or not self._rows:
            return
        now = datetime.now()
        path = self._dialogs.save_file(
            "Export comparison result", f"Comparison_Result_{now:%Y%m%d_%H%M%S}.html", "HTML Files (*.html)"
        )
        if not path:
            return
        report = build_report(
            _TARGET_HEADERS,
            [
                (part, row.parameter, _display(row.master),
                 _display(row.base) if (part, software) in self._base_variants else "",
                 _display(row.target), self._effective_status(index).value, self._comment(index))
                for index, (part, software, row) in enumerate(self._rows)
            ],
            [self._is_deviation(index) for index in range(len(self._rows))],
            list(dict.fromkeys(part for part, _, _ in self._rows)),
            now,
            [
                row.status.value if self._effective_status(index) != row.status else ""
                for index, (_, _, row) in enumerate(self._rows)
            ],
            self._reviewer(),
        )
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(report)
        except OSError as error:
            self._dialogs.error("Comparison", f"Could not export the comparison result: {error}")
            return
        self._dialogs.info("Comparison", f"Comparison result exported to {path}.")

    def _update_impl(self) -> None:
        if self._running or not self._impl_updates or self._impl_updater is None:
            return
        path = str(self._settings.load().get("master_sheet_path", "")).strip() if self._settings is not None else ""
        if not path:
            self._dialogs.error("Update Master Sheet", "Load a Master Sheet on Home first.")
            return
        updates = dict(self._impl_updates)
        listing = "\n".join(f"  {variant} ({len(update.values)} values)" for variant, update in updates.items())
        if not self._dialogs.confirm(
            "Update Master Sheet",
            f"Write the exported Target values into the IMPL rows of {len(updates)} compared "
            f"variant(s) in the Master Sheet?\n\n{listing}\n\nBase values are not written.",
        ):
            return
        self._set_running(True)
        self._summary.setText("Updating Master Sheet values...")
        self._worker = FunctionWorker(lambda: self._impl_updater.update(path, updates), self)
        self._worker.finished_ok.connect(self._finish_impl)
        self._worker.finished_error.connect(self._fail_impl)
        self._worker.start()

    def _end_impl_worker(self) -> None:
        if self._worker is not None:
            self._worker.wait()
            self._worker.deleteLater()
            self._worker = None
        self._set_running(False)

    def _finish_impl(self, outcomes: dict) -> None:
        self._end_impl_worker()
        written = sum(bool(outcome.written) and not outcome.error for outcome in outcomes.values())
        problems = [f"{variant}: {outcome.error}" for variant, outcome in outcomes.items() if outcome.error]
        skipped = sum(outcome.skipped for outcome in outcomes.values())
        text = f"Master Sheet updated for {written} of {len(outcomes)} variant(s)."
        if skipped:
            text += f" {skipped} formula cell(s) were left unchanged."
        self._summary.setText(text)
        if any(outcome.written for outcome in outcomes.values()):
            self._keep_results = True
            self.masterReloadRequested.emit()
        if problems:
            self._dialogs.error("Update Master Sheet", text + "\n\n" + "\n".join(problems))
        else:
            self._dialogs.info("Update Master Sheet", text)

    def _fail_impl(self, error: str) -> None:
        self._end_impl_worker()
        self._summary.setText(f"Master Sheet update failed: {error}")
        self._dialogs.error("Update Master Sheet", error)

    def _set_running(self, running: bool) -> None:
        self._running = running
        self._variants_table.setEnabled(not running)
        self._select_all_btn.setEnabled(not running and self._variants_table.rowCount() > 0)
        self._clear_selection_btn.setEnabled(not running and bool(self._selected_rows()))
        self._compare_btn.setEnabled(not running and bool(self._selected_rows()))
        self._export_btn.setEnabled(not running and bool(self._rows))
        self._impl_btn.setEnabled(not running and bool(self._impl_updates))

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
            variant["base_webflow_link"] = self._variants_table.item(row, 3).data(Qt.UserRole) or ""
        masters = deepcopy(self._variants)
        saved = self._settings.load() if self._settings is not None else {}
        connection = {"driver_path": ""}
        connection["base_url"] = webflow_base_url(saved)
        self._run_base = {
            tuple(self._variants_table.item(row, 0).data(Qt.UserRole + 1)[:2])
            for row in rows if self._variants_table.item(row, 3).data(Qt.UserRole)
        }
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
        rows = [(result.variant, result.software, row) for result in results for row in result.rows]
        if rows:
            self._rows = rows
            self._reviews = {}
            self._base_variants = self._run_base
            self._impl_updates = {
                result.variant: build_impl_update(result.software, result.rows)
                for result in results if result.rows and not result.error and not result.cancelled
            }
            self._fill_status_filter()
            self._render_results()
        self._set_running(False)
        self._summary.setText(self._summary.text() if rows else "No comparison results were produced.")
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
        self._table.setRowCount(0)
        self._header_filter.reset()
        self._variant_filter.blockSignals(True)
        self._variant_filter.clear()
        self._variant_filter.addItem("All variants", None)
        for part in dict.fromkeys(part for part, _, _ in self._rows):
            self._variant_filter.addItem(part, part)
        self._variant_filter.blockSignals(False)
        self._size_variant_filter()
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._rows))
        for index, (part, software, row) in enumerate(self._rows):
            values = (
                (part, row.parameter, _display(row.master),
                 _display(row.base) if (part, software) in self._base_variants else "",
                 _display(row.target), self._effective_status(index).value, self._comment(index))
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column != _COMMENT_COLUMN:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(index, column, item)
            self._table.item(index, 0).setData(Qt.UserRole, index)
            self._refresh_status_item(index)
        self._table.blockSignals(False)
        self._table.resizeColumnsToContents()
        for column in range(self._table.columnCount()):
            self._table.setColumnWidth(column, min(300, self._table.columnWidth(column)))
        self._apply_filters()

    def _review(self, index: int) -> Review | None:
        part, _, row = self._rows[index]
        return self._reviews.get((part, row.parameter))

    def _effective_status(self, index: int) -> Status:
        review = self._review(index)
        return review.status if review and review.status else self._rows[index][2].status

    def _comment(self, index: int) -> str:
        review = self._review(index)
        return review.comment if review else ""

    def _is_deviation(self, index: int) -> bool:
        return replace(self._rows[index][2], status=self._effective_status(index)).deviation

    def _store_review(self, index: int, status: Status | None = None, comment: str | None = None) -> None:
        part, _, row = self._rows[index]
        current = self._reviews.get((part, row.parameter), Review())
        updated = Review(
            current.status if status is None else (None if status == row.status else status),
            current.comment if comment is None else comment,
        )
        if updated.status is None and not updated.comment:
            self._reviews.pop((part, row.parameter), None)
        else:
            self._reviews[(part, row.parameter)] = updated

    def _refresh_status_item(self, index: int) -> None:
        item = self._table.item(index, _STATUS_COLUMN)
        calculated = self._rows[index][2].status
        effective = self._effective_status(index)
        font = item.font()
        font.setItalic(effective != calculated)
        item.setFont(font)
        item.setText(effective.value)
        item.setToolTip(
            f"Calculated: {calculated.value} | Manually changed" if effective != calculated else effective.value
        )

    def _set_status(self, index: int, status: Status) -> None:
        self._store_review(index, status=status)
        self._table.blockSignals(True)
        self._refresh_status_item(index)
        self._table.blockSignals(False)
        self._apply_filters()

    def _reset_status(self, index: int) -> None:
        self._set_status(index, self._rows[index][2].status)

    def _set_comment(self, index: int, comment: str) -> None:
        self._store_review(index, comment=comment.strip())
        self._table.blockSignals(True)
        item = self._table.item(index, _COMMENT_COLUMN)
        item.setText(self._comment(index))
        item.setToolTip(self._comment(index))
        self._table.blockSignals(False)
        self._apply_filters()

    def _comment_edited(self, item: QTableWidgetItem) -> None:
        if item.column() == _COMMENT_COLUMN and not self._running:
            self._set_comment(self._model_index(item.row()), item.text())

    def _model_index(self, table_row: int) -> int:
        return int(self._table.item(table_row, 0).data(Qt.UserRole))

    def _allowed_statuses(self, index: int) -> tuple[Status, ...]:
        part, software, _ = self._rows[index]
        if (part, software) in self._base_variants:
            return tuple(Status)
        return (Status.MATCH, Status.VALUE_MISMATCH, Status.MISSING_IN_MASTER, Status.MISSING_IN_WEBFLOW)

    def _result_menu(self, table_row: int, column: int) -> QMenu | None:
        if self._running or table_row < 0 or column not in (_STATUS_COLUMN, _COMMENT_COLUMN):
            return None
        index = self._model_index(table_row)
        menu = QMenu(self._table)
        if column == _STATUS_COLUMN:
            change = menu.addMenu("Change Status")
            for status in self._allowed_statuses(index):
                action = change.addAction(status.value)
                action.setCheckable(True)
                action.setChecked(status == self._effective_status(index))
                action.triggered.connect(lambda _=False, value=status: self._set_status(index, value))
            reset = menu.addAction("Reset Status")
            reset.setEnabled(self._effective_status(index) != self._rows[index][2].status)
            reset.triggered.connect(lambda: self._reset_status(index))
        else:
            edit = menu.addAction("Edit Comment")
            edit.triggered.connect(lambda: self._table.editItem(self._table.item(table_row, column)))
            clear = menu.addAction("Clear Comment")
            clear.setEnabled(bool(self._comment(index)))
            clear.triggered.connect(lambda: self._set_comment(index, ""))
        return menu

    def _open_result_menu(self, pos) -> None:
        item = self._table.itemAt(pos)
        menu = self._result_menu(item.row(), item.column()) if item is not None else None
        if menu is not None:
            menu.exec(self._table.viewport().mapToGlobal(pos))

    def _size_variant_filter(self) -> None:
        width = self._variant_filter.sizeHint().width()
        self._variant_filter.setMinimumWidth(min(420, max(200, width)))
        self._variant_filter.view().setMinimumWidth(max(200, width))

    def _apply_filters(self, *_args) -> None:
        self._header_filter.apply()

    def _matches_global_filters(self, index: int) -> bool:
        search = self._search.text().strip().casefold()
        status = self._status_filter.currentText()
        variant = self._variant_filter.currentData()
        part, _, row = self._rows[index]
        text = " ".join(self._table.item(index, column).text() for column in range(self._table.columnCount()))
        return (
            (not search or search in text.casefold())
            and (variant is None or variant == part)
            and (status == "All statuses" or status == self._effective_status(index).value)
            and (not self._deviations.isChecked() or self._is_deviation(index))
        )

    def _update_filter_summary(self) -> None:
        visible = sum(not self._table.isRowHidden(index) for index in range(self._table.rowCount()))
        self._summary.setText(
            f"{visible} / {len(self._rows)} parameters shown; "
            f"{sum(self._is_deviation(index) for index in range(len(self._rows)))} deviations from Master."
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
