"""Multi-variant comparison workspace; browser work runs off the UI thread."""
from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from threading import Event

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QHBoxLayout, QHeaderView, QLabel,
    QListWidget, QListWidgetItem, QMenu, QPushButton, QStyle, QStyledItemDelegate, QStyleOptionButton, QStyleOptionViewItem,
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
from autohub.modules.home.table_clipboard import TableClipboard
from autohub.ui.theme import set_muted
from autohub.ui.hover_cursor import HoverCursor
from autohub.ui.webflow_link_delegate import WebFlowLinkDelegate, format_webflow_link_item

from .comparison import ComparisonRow, Status
from .impl_update import ImplRefresh, MasterImplUpdater, build_impl_update
from .matching import master_parameters, validate_link
from .report import build_report
from .review import Review
from .result_table import ResultTable
from .progress import ComparisonProgressDialog
from .service import ComparisonService, VariantResult, compare_xml_files
from .xml_parser import ParameterValue

_STATUS_COLUMN = 5
_TARGET_HEADERS = ("Part Number", "Parameter", "Master", "Base", "Target", "Status", "Comment")
_MANUAL_HEADERS = ("Parameter", "Base", "Target", "Status", "Comment")
_VARIANT_HEADERS = ("Select", "Part Number", "WebFlow", "Base WebFlow Link", "Status", "Error")


@dataclass
class _ResultState:
    rows: list[tuple[str, str, ComparisonRow]]
    reviews: dict[tuple[str, str], Review]
    impl_updates: dict[str, ImplUpdate]
    base_variants: set[tuple[str, str]]


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
        self._manual_mode = False
        self._mode_results: dict[bool, _ResultState] = {}
        self._xml_paths = {"Base": ""}
        self._target_paths: list[str] = []
        self._compared_files: tuple[str, ...] | None = None
        self._run_files: tuple[str, ...] = ()

        title = QLabel("Comparison")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        subtitle = QLabel(
            "Select linked variants to export WebFlow XML automatically and compare with Master. "
            "Jobs are processed sequentially using the existing WebFlow browser and authentication."
        )
        subtitle.setWordWrap(True)
        set_muted(subtitle, True)
        self._subtitle = subtitle
        self._master_mode_btn = QPushButton("Master Sheet Compare")
        self._manual_mode_btn = QPushButton("Manual XML Compare")
        self._mode_group = QButtonGroup(self)
        mode_selection = QHBoxLayout()
        for button in (self._master_mode_btn, self._manual_mode_btn):
            button.setCheckable(True)
            self._mode_group.addButton(button)
            mode_selection.addWidget(button)
        self._master_mode_btn.setChecked(True)
        mode_selection.addStretch(1)
        self._manual_sources = QWidget()
        manual_layout = QVBoxLayout(self._manual_sources)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        self._xml_buttons: dict[str, QPushButton] = {}
        self._xml_labels: dict[str, QLabel] = {}
        for label in ("Base", "Target"):
            source_row = QHBoxLayout()
            source_row.addWidget(QLabel(f"{label} XML:"))
            button = QPushButton("Select XML(s)..." if label == "Target" else "Select XML...")
            button.clicked.connect(lambda _=False, source=label: self._select_xml(source))
            filename = QLabel("No file selected")
            filename.setTextFormat(Qt.PlainText)
            source_row.addWidget(button)
            source_row.addWidget(filename, 1)
            manual_layout.addLayout(source_row)
            self._xml_buttons[label] = button
            self._xml_labels[label] = filename
        self._target_list = QListWidget()
        self._target_list.setMaximumHeight(120)
        self._target_list.hide()
        manual_layout.addWidget(self._target_list)
        self._clear_targets_btn = QPushButton("Clear All")
        self._clear_targets_btn.clicked.connect(self._clear_targets)
        self._clear_targets_btn.hide()
        manual_layout.addWidget(self._clear_targets_btn, 0, Qt.AlignLeft)
        self._manual_sources.hide()
        self._file_info = QLabel()
        self._file_info.setTextFormat(Qt.PlainText)
        self._file_info.setWordWrap(True)
        self._file_info.hide()
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
        self._table = ResultTable(0, len(_TARGET_HEADERS))
        self._table.setHorizontalHeaderLabels(_TARGET_HEADERS)
        self._table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setWordWrap(False)
        self._table.setTextElideMode(Qt.ElideRight)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._result_clipboard = TableClipboard(self._table)
        self._table.installEventFilter(self)
        self._table.viewport().installEventFilter(self)
        self._table.frozen.view.installEventFilter(self)
        self._table.frozen.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.frozen.view.customContextMenuRequested.connect(self._open_frozen_result_menu)
        self._table.frozen.view.clicked.connect(lambda _: self._table.setFocus())
        self._summary = QLabel("Load a Master Sheet on Home and select linked variants.")
        self._summary.setTextFormat(Qt.PlainText)
        self._summary.setWordWrap(True)
        self._header_filter = TableFilter(
            self._table, (self._table.frozen.view,), first_column=0,
            on_applied=self._update_filter_summary,
        )
        self._layout = layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addLayout(mode_selection)
        layout.addWidget(subtitle)
        layout.addWidget(self._variants_table)
        layout.addWidget(self._manual_sources)
        layout.addLayout(sources)
        layout.addWidget(self._file_info)
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
        self._table.model().layoutChanged.connect(self._apply_filters)
        self._progress.connect(self._on_progress)
        self._manual_mode_btn.toggled.connect(self._change_mode)
        self._refresh_variants()
        self._variants_table.setFocus()

    @property
    def _status_column(self) -> int:
        return len(self._result_headers()) - 2

    @property
    def _comment_column(self) -> int:
        return len(self._result_headers()) - 1

    def _result_headers(self) -> tuple[str, ...]:
        if not self._manual_mode:
            return _TARGET_HEADERS
        if self._compared_files is None or len(self._compared_files) == 2:
            return _MANUAL_HEADERS
        return (
            "Parameter", "Base",
            *(f"Target {index}: {os.path.basename(path)}" for index, path in enumerate(self._compared_files[1:], 1)),
            "Status", "Comment",
        )

    def _change_mode(self, manual: bool) -> None:
        self._mode_results[self._manual_mode] = _ResultState(
            self._rows, self._reviews, self._impl_updates, self._base_variants,
        )
        self._manual_mode = manual
        state = self._mode_results.get(manual, _ResultState([], {}, {}, set()))
        self._rows, self._reviews = state.rows, state.reviews
        self._impl_updates, self._base_variants = state.impl_updates, state.base_variants
        for widget in (self._subtitle, self._variants_table, self._select_all_btn,
                       self._clear_selection_btn, self._impl_btn):
            widget.setVisible(not manual)
        self._manual_sources.setVisible(manual)
        self._layout.removeWidget(self._summary)
        if manual:
            self._layout.insertWidget(self._layout.indexOf(self._table), self._summary)
        else:
            self._layout.addWidget(self._summary)
        self._compare_btn.setText("Compare" if manual else "Compare selected")
        self._render_results()
        self._set_running(False)

    def _select_xml(self, source: str) -> None:
        if source == "Target":
            paths = self._dialogs.pick_files("Select Target WebFlow Export XML files", "XML Files (*.xml)")
            try:
                for path in paths:
                    if not any(
                        os.path.realpath(path) == os.path.realpath(existing)
                        or (os.path.exists(path) and os.path.exists(existing) and os.path.samefile(path, existing))
                        for existing in self._target_paths
                    ):
                        self._target_paths.append(path)
            except OSError as error:
                self._dialogs.error("Comparison", f"Could not add Target XML files: {error}")
            self._refresh_target_files()
            return
        path = self._dialogs.pick_file(f"Select {source} WebFlow Export XML", "XML Files (*.xml)")
        if path:
            self._xml_paths[source] = path
            self._xml_labels[source].setText(os.path.basename(path))
            self._xml_labels[source].setToolTip(path)
            self._source_changed()

    def _refresh_target_files(self) -> None:
        self._target_list.clear()
        for path in self._target_paths:
            item = QListWidgetItem(self._target_list)
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(6, 2, 6, 2)
            label = QLabel(os.path.basename(path))
            label.setTextFormat(Qt.PlainText)
            label.setToolTip(path)
            row.addWidget(label, 1)
            remove = QPushButton("x")
            remove.setToolTip(f"Remove {os.path.basename(path)}")
            remove.setAccessibleName(f"Remove {os.path.basename(path)}")
            remove.clicked.connect(lambda _=False, value=path: self._remove_target(value))
            row.addWidget(remove)
            item.setSizeHint(container.sizeHint())
            self._target_list.setItemWidget(item, container)
        count = len(self._target_paths)
        self._xml_labels["Target"].setText(f"{count} file{'s' if count != 1 else ''} selected")
        self._xml_labels["Target"].setToolTip("")
        self._target_list.setVisible(count > 0)
        self._clear_targets_btn.setVisible(count > 1)
        self._source_changed()

    def _remove_target(self, path: str) -> None:
        self._target_paths.remove(path)
        self._refresh_target_files()

    def _clear_targets(self) -> None:
        self._target_paths.clear()
        self._refresh_target_files()

    def _result_values(self, index: int) -> tuple[str, ...]:
        part, software, row = self._rows[index]
        if self._manual_mode:
            return (row.parameter, _display(row.base), *(_display(value) for value in (row.targets or (row.target,))),
                    self._effective_status(index).value, self._comment(index))
        return (part, row.parameter, _display(row.master),
                _display(row.base) if (part, software) in self._base_variants else "",
                _display(row.target), self._effective_status(index).value, self._comment(index))

    def _update_file_info(self) -> None:
        self._file_info.setVisible(self._manual_mode and self._compared_files is not None)
        if self._compared_files is not None:
            base, *targets = self._compared_files
            self._file_info.setText(
                f"Base: {os.path.basename(base)}\nTarget: " + ", ".join(os.path.basename(path) for path in targets)
            )
            self._file_info.setToolTip(f"Base: {base}\nTarget: " + "\n".join(targets))

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
            initial = "Completed" if str(variant.get("comparison_result") or "").strip().upper() == "OK" else "Pending"
            for column, text in enumerate((identity[0], identity[2], base_link, initial, ""), 1):
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
        if self._manual_mode:
            self._mode_results.pop(False, None)
            self._source_changed()
            return
        self._revision += 1
        self._rows = []
        self._reviews = {}
        self._impl_updates = {}
        self._base_variants = set()
        self._table.setRowCount(0)
        self._header_filter.reset()
        self._source_changed()

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
        try:
            if self._manual_mode and self._compared_files is not None:
                if any(
                    os.path.realpath(path) == os.path.realpath(source)
                    or (os.path.exists(path) and os.path.exists(source) and os.path.samefile(path, source))
                    for source in (*self._compared_files, self._xml_paths["Base"], *self._target_paths)
                ):
                    self._dialogs.error("Comparison", "Choose a report destination other than a source XML file.")
                    return
        except OSError as error:
            self._dialogs.error("Comparison", f"Could not validate the report destination: {error}")
            return
        report = build_report(
            self._result_headers(),
            [self._result_values(index) for index in range(len(self._rows))],
            [self._is_deviation(index) for index in range(len(self._rows))],
            list(dict.fromkeys(part for part, _, _ in self._rows)),
            now,
            [
                row.status.value if self._effective_status(index) != row.status else ""
                for index, (_, _, row) in enumerate(self._rows)
            ],
            self._reviewer(),
            xml_files=(
                tuple(os.path.basename(path) for path in self._compared_files)
                if self._manual_mode and self._compared_files is not None else None
            ),
            target_statuses=(
                [tuple(status.value for status in row.target_statuses) for _, _, row in self._rows]
                if self._manual_mode else ()
            ),
        )
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(report)
        except OSError as error:
            self._dialogs.error("Comparison", f"Could not export the comparison result: {error}")
            return
        self._dialogs.info("Comparison", f"Comparison result exported to {path}.")

    def _update_impl(self) -> None:
        if self._manual_mode or self._running or not self._impl_updates or self._impl_updater is None:
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

    def _refresh_impl_data(self, variants: list[dict], parts: set[str]) -> None:
        refreshed = {}
        for variant in variants:
            identity = (str(variant["part_number"]), str(variant.get("hardware", {}).get("software_part_number") or ""))
            if identity in refreshed:
                raise ValueError(f"Ambiguous refreshed Master Sheet variant: {identity[0]}.")
            refreshed[identity] = variant
        replacements = {}
        for index, variant in enumerate(self._variants):
            part = str(variant["part_number"])
            if part not in parts:
                continue
            identity = (part, str(variant.get("hardware", {}).get("software_part_number") or ""))
            if identity not in refreshed:
                raise ValueError(f"Updated variant not found in refreshed Master Sheet: {part}.")
            replacements[index] = deepcopy(refreshed[identity])
        masters = {
            (str(variant["part_number"]), str(variant.get("hardware", {}).get("software_part_number") or "")):
            master_parameters(variant)
            for variant in replacements.values()
        }
        for index, variant in replacements.items():
            self._variants[index] = variant
        for row in range(self._variants_table.rowCount()):
            index = self._variants_table.item(row, 0).data(Qt.UserRole)
            if index in replacements:
                value = str(replacements[index].get("comparison_result") or "").strip().upper()
                self._set_variant_status(row, "Completed" if value == "OK" else "Pending", "")
        self._rows = [
            (part, software, replace(row, master=masters[(part, software)].get(row.parameter)))
            if (part, software) in masters else (part, software, row)
            for part, software, row in self._rows
        ]
        self._table.blockSignals(True)
        try:
            for visual_row in range(self._table.rowCount()):
                index = self._table.item(visual_row, 0).data(Qt.UserRole)
                item = self._table.item(visual_row, 2)
                value = _display(self._rows[index][2].master)
                item.setText(value)
                item.setToolTip(value)
        finally:
            self._table.blockSignals(False)

    def _finish_impl(self, result: ImplRefresh) -> None:
        outcomes = result.outcomes
        try:
            self._refresh_impl_data(result.variants, {part for part, outcome in outcomes.items() if outcome.written})
        except Exception as error:
            self._fail_impl(f"Master Sheet refresh failed: {error}")
            return
        self._end_impl_worker()
        written = sum(bool(outcome.written) and not outcome.error for outcome in outcomes.values())
        problems = [f"{variant}: {outcome.error}" for variant, outcome in outcomes.items() if outcome.error]
        text = f"Master Sheet updated successfully for {written} of {len(outcomes)} variant(s)."
        if problems:
            text = f"Master Sheet update failed for {len(problems)} of {len(outcomes)} variant(s)."
        self._summary.setText(text)
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
        self._master_mode_btn.setEnabled(not running)
        self._manual_mode_btn.setEnabled(not running)
        for button in self._xml_buttons.values():
            button.setEnabled(not running)
        self._target_list.setEnabled(not running)
        self._clear_targets_btn.setEnabled(not running)
        self._variants_table.setEnabled(not running)
        self._select_all_btn.setEnabled(not running and self._variants_table.rowCount() > 0)
        self._clear_selection_btn.setEnabled(not running and bool(self._selected_rows()))
        ready = bool(self._xml_paths["Base"] and self._target_paths) if self._manual_mode else bool(self._selected_rows())
        self._compare_btn.setEnabled(not running and ready)
        self._export_btn.setEnabled(not running and bool(self._rows))
        self._impl_btn.setEnabled(not running and not self._manual_mode and bool(self._impl_updates))

    def _compare(self) -> None:
        if self._running:
            return
        if self._manual_mode:
            self._compare_manual()
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

    def _compare_manual(self) -> None:
        self._run_files = (self._xml_paths["Base"], *self._target_paths)
        self._run_rows = []
        self._run_revision = self._revision
        self._cancel = Event()
        self._set_running(True)
        self._summary.setText("Comparing XML files...")
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog.deleteLater()
        self._progress_dialog = ComparisonProgressDialog(
            [os.path.basename(path) for path in self._target_paths], self, identity_header="Target XML",
        )
        self._progress_dialog.cancel_requested.connect(self._cancel.set)
        self._progress_dialog.show()
        base, *targets = self._run_files
        self._worker = FunctionWorker(
            lambda: compare_xml_files(
                base, targets, progress=self._progress.emit, cancelled=self._cancel.is_set,
            ), self,
        )
        self._worker.finished_ok.connect(self._finish_manual)
        self._worker.finished_error.connect(self._fail)
        self._worker.start()

    def _finish_manual(self, rows: list[ComparisonRow] | None) -> None:
        if self._worker is not None:
            self._worker.wait()
            self._worker.deleteLater()
            self._worker = None
        if self._progress_dialog is not None:
            self._progress_dialog.finish()
        if rows is not None:
            self._rows = [("", "", row) for row in rows]
            self._reviews = {}
            self._compared_files = self._run_files
            self._render_results()
        else:
            self._summary.setText("Comparison cancelled. Previous results retained.")
        self._set_running(False)

    def _set_variant_status(self, row: int, status: str, error: str) -> None:
        self._variants_table.item(row, 4).setText(status)
        self._variants_table.item(row, 5).setText(error)
        self._variants_table.item(row, 5).setToolTip(error)

    def _on_progress(self, index: int, status: str, error: str) -> None:
        if self._progress_dialog is not None:
            self._progress_dialog.update_status(index, status, error)
        if self._manual_mode:
            return
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
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        headers = self._result_headers()
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        for column in range(len(headers)):
            self._table.frozen.view.setColumnHidden(column, column != 0)
        self._header_filter.reset()
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._rows))
        for index, (part, software, row) in enumerate(self._rows):
            values = self._result_values(index)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if self._manual_mode and 2 <= column < self._status_column and row.target_statuses:
                    status = row.target_statuses[column - 2]
                    item.setToolTip(f"{value}\nCalculated: {status.value}")
                    if status != Status.MATCH:
                        item.setForeground(QColor("#b42318"))
                        item.setBackground(QColor("#fde2e1"))
                if column != self._comment_column:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(index, column, item)
            self._table.item(index, 0).setData(Qt.UserRole, index)
            self._refresh_status_item(index, self._table.item(index, self._status_column))
        self._table.blockSignals(False)
        self._table.setSortingEnabled(self._manual_mode)
        self._size_result_columns()
        self._update_file_info()
        self._apply_filters()

    def _size_result_columns(self) -> None:
        widths = {
            0: 260, **{column: 160 for column in range(1, self._status_column)},
            self._status_column: 180,
        } if self._manual_mode else {
            0: max(100, self._table.sizeHintForColumn(0)),
            _STATUS_COLUMN: max(90, self._table.sizeHintForColumn(_STATUS_COLUMN)),
            1: 160, 2: 110, 3: 110, 4: 110,
        }
        for column, width in widths.items():
            self._table.setColumnWidth(column, width)
        self._table.setColumnWidth(
            self._comment_column, max(260, self._table.viewport().width() - sum(widths.values()))
        )

    def eventFilter(self, watched, event) -> bool:
        if watched is self._table.viewport() and event.type() == QEvent.Resize:
            self._size_result_columns()
        if watched in (self._table, self._table.frozen.view) and event.type() == QEvent.KeyPress:
            if event.matches(QKeySequence.Copy):
                self._copy_result()
                return True
            if event.matches(QKeySequence.Paste):
                self._paste_result()
                return True
            if event.matches(QKeySequence.Cut):
                self._clear_result_comments(cut=True)
                return True
            if event.key() == Qt.Key_Delete:
                self._clear_result_comments()
                return True
        return super().eventFilter(watched, event)

    def _copy_result(self) -> None:
        cells = self._result_clipboard.selected_cells()
        if len(cells) == 1:
            QApplication.clipboard().setText(self._table.item(*cells[0]).text())
        else:
            self._result_clipboard.copy_selection()

    def _copy_result_row(self, row: int) -> None:
        QApplication.clipboard().setText("\t".join(
            self._table.item(row, column).text().replace("\t", " ").replace("\r", " ").replace("\n", " ")
            for column in range(self._table.columnCount())
        ))

    def _clear_result_comments(self, cut: bool = False) -> None:
        if self._running:
            return
        cells = [
            (row, column) for row, column in self._result_clipboard.selected_cells()
            if column == self._comment_column and not self._table.isRowHidden(row)
        ]
        if cut and cells:
            QApplication.clipboard().setText("\n".join(self._table.item(*cell).text() for cell in cells))
        indices = [self._model_index(row) for row, _ in cells]
        for index in indices:
            self._set_comment(index, "")

    def _paste_result(self) -> None:
        if self._running:
            return
        current = self._table.currentItem()
        if current is None or current.column() not in (self._comment_column, self._status_column):
            return
        text = QApplication.clipboard().text()
        if not text:
            return
        grid = [line.split("\t") for line in text.splitlines()]
        cells = self._result_clipboard.selected_cells()
        edits = []
        if len(grid) == 1 and len(grid[0]) == 1:
            edits = [(self._model_index(row), column, text) for row, column in cells
                     if column in (self._comment_column, self._status_column) and not self._table.isRowHidden(row)]
        else:
            visible = [row for row in range(current.row(), self._table.rowCount()) if not self._table.isRowHidden(row)]
            for row, values in zip(visible, grid):
                for offset, value in enumerate(values):
                    column = current.column() + offset
                    if column in (self._comment_column, self._status_column):
                        edits.append((self._model_index(row), column, value))
        for index, column, value in edits:
            if column == self._status_column and value not in {status.value for status in self._allowed_statuses(index)}:
                self._dialogs.error("Paste", f"Unsupported comparison status: {value}")
                return
        for index, column, value in edits:
            if column == self._comment_column:
                self._set_comment(index, value)
            else:
                self._set_status(index, Status(value))

    def _review(self, index: int) -> Review | None:
        part, _, row = self._rows[index]
        return self._reviews.get((part, row.parameter))

    def _effective_status(self, index: int) -> Status:
        review = self._review(index)
        return review.status if review and review.status else self._rows[index][2].status

    def _comment(self, index: int) -> str:
        review = self._review(index)
        return review.comment if review else self._default_comment(index)

    def _default_comment(self, index: int) -> str:
        row = self._rows[index][2]
        if not self._manual_mode or self._compared_files is None or len(self._compared_files) <= 2:
            return ""
        return "; ".join(
            f"Target {target + 1} ({os.path.basename(path)}): {status.value}"
            for target, (path, status) in enumerate(zip(self._compared_files[1:], row.target_statuses))
            if status != Status.MATCH
        )

    def _is_deviation(self, index: int) -> bool:
        return replace(self._rows[index][2], status=self._effective_status(index)).deviation

    def _store_review(self, index: int, status: Status | None = None, comment: str | None = None) -> None:
        part, _, row = self._rows[index]
        default_comment = self._default_comment(index)
        current = self._reviews.get((part, row.parameter), Review(comment=default_comment))
        updated = Review(
            current.status if status is None else (None if status == row.status else status),
            current.comment if comment is None else comment,
        )
        if updated.status is None and updated.comment == default_comment:
            self._reviews.pop((part, row.parameter), None)
        else:
            self._reviews[(part, row.parameter)] = updated

    def _refresh_status_item(self, index: int, item: QTableWidgetItem | None = None) -> None:
        if item is None:
            item = self._result_item(index, self._status_column)
        calculated = self._rows[index][2].status
        effective = self._effective_status(index)
        font = item.font()
        font.setItalic(effective != calculated)
        item.setFont(font)
        item.setText(effective.value)
        item.setToolTip(
            f"Calculated: {calculated.value} | Manually changed" if effective != calculated else effective.value
        )
        if self._manual_mode:
            item.setForeground(QColor("#b42318" if self._is_deviation(index) else "#1b7f3b"))
            item.setBackground(QColor("#fde2e1" if self._is_deviation(index) else "#e3f6e8"))

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
        item = self._result_item(index, self._comment_column)
        item.setText(self._comment(index))
        item.setToolTip(self._comment(index))
        self._table.blockSignals(False)
        self._apply_filters()

    def _comment_edited(self, item: QTableWidgetItem) -> None:
        if item.column() == self._comment_column and not self._running:
            self._set_comment(self._model_index(item.row()), item.text())

    def _model_index(self, table_row: int) -> int:
        return int(self._table.item(table_row, 0).data(Qt.UserRole))

    def _result_item(self, index: int, column: int) -> QTableWidgetItem:
        for row in range(self._table.rowCount()):
            if self._model_index(row) == index:
                return self._table.item(row, column)
        raise ValueError(f"Comparison row is not displayed: {index}")

    def _allowed_statuses(self, index: int) -> tuple[Status, ...]:
        if self._manual_mode:
            return (Status.MATCH, Status.VALUE_MISMATCH, Status.MISSING_IN_BASE, Status.MISSING_IN_TARGET)
        part, software, _ = self._rows[index]
        if (part, software) in self._base_variants:
            return tuple(status for status in Status if status not in (Status.MISSING_IN_BASE, Status.MISSING_IN_TARGET))
        return (Status.MATCH, Status.VALUE_MISMATCH, Status.MISSING_IN_MASTER, Status.MISSING_IN_WEBFLOW)

    def _result_menu(self, table_row: int, column: int) -> QMenu | None:
        if self._running or table_row < 0:
            return None
        index = self._model_index(table_row)
        menu = QMenu(self._table)
        if column == self._status_column:
            change = menu.addMenu("Change Status")
            for status in self._allowed_statuses(index):
                action = change.addAction(status.value)
                action.setCheckable(True)
                action.setChecked(status == self._effective_status(index))
                action.triggered.connect(lambda _=False, value=status: self._set_status(index, value))
            reset = menu.addAction("Reset Status")
            reset.setEnabled(self._effective_status(index) != self._rows[index][2].status)
            reset.triggered.connect(lambda: self._reset_status(index))
        elif column == self._comment_column:
            edit = menu.addAction("Edit Comment")
            edit.triggered.connect(lambda: self._table.editItem(self._table.item(table_row, column)))
            clear = menu.addAction("Clear Comment")
            clear.setEnabled(bool(self._comment(index)))
            clear.triggered.connect(lambda: self._set_comment(index, ""))
        if menu.actions():
            menu.addSeparator()
        menu.addAction("Copy", self._copy_result)
        menu.addAction("Copy Row", lambda: self._copy_result_row(table_row))
        return menu

    def _open_result_menu(self, pos) -> None:
        item = self._table.itemAt(pos)
        if item is not None and not item.isSelected():
            self._table.setCurrentItem(item)
        menu = self._result_menu(item.row(), item.column()) if item is not None else None
        if menu is not None:
            menu.exec(self._table.viewport().mapToGlobal(pos))

    def _open_frozen_result_menu(self, pos) -> None:
        view = self._table.frozen.view
        index = view.indexAt(pos)
        if not index.isValid():
            return
        item = self._table.item(index.row(), index.column())
        if not item.isSelected():
            self._table.setCurrentItem(item)
        menu = self._result_menu(index.row(), index.column())
        if menu is not None:
            menu.exec(view.viewport().mapToGlobal(pos))

    def _apply_filters(self, *_args) -> None:
        self._header_filter.apply()

    def _update_filter_summary(self) -> None:
        visible = sum(not self._table.isRowHidden(index) for index in range(self._table.rowCount()))
        deviations = sum(self._is_deviation(index) for index in range(len(self._rows)))
        if self._manual_mode:
            prefix = "Overall: " if self._compared_files and len(self._compared_files) > 2 else "Summary: "
            self._summary.setText(
                f"{prefix}Total: {len(self._rows)} | Match: {len(self._rows) - deviations} | Deviation: {deviations}"
                f" | {visible} / {len(self._rows)} parameters shown"
                + "".join(
                    f"\nTarget {target + 1} ({os.path.basename(path)}): Match: {matches} | Deviation: {len(self._rows) - matches}"
                    for target, path, matches in self._per_target_summary()
                )
            )
            return
        self._summary.setText(
            f"{visible} / {len(self._rows)} parameters shown; "
            f"{sum(self._is_deviation(index) for index in range(len(self._rows)))} deviations from Master."
        )

    def _per_target_summary(self) -> list[tuple[int, str, int]]:
        if not self._manual_mode or not self._compared_files or len(self._compared_files) <= 2:
            return []
        return [
            (target, path, sum(row.target_statuses[target] == Status.MATCH for _, _, row in self._rows))
            for target, path in enumerate(self._compared_files[1:])
        ]

    def confirm_leave(self) -> bool:
        if self._running:
            self._dialogs.info("Comparison", "Wait for the current XML exports and comparisons to finish.")
            return False
        return True

    def shutdown(self) -> None:
        self._cancel.set()
        if self._worker is not None:
            self._worker.wait()
