"""Comparison workspace over the variants published by Home; XML upload is the export fallback."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.webflow_numbers import NUMBER_FIELDS
from autohub.ui.theme import set_muted

from .comparison import ComparisonRow, Status, compare_parameters
from .matching import (
    master_parameters, match_variant, validate_export_link, validate_link, variant_identity,
)
from .xml_parser import MAX_XML_BYTES, ParameterMap, ParameterValue, parse_xml

_TARGET_HEADERS = ("Variant", "SW Part Number", "Parameter", "Master", "Webflow", "Status")
_BASE_HEADERS = ("Parameter", "Master", "Base", "Target", "Status")


def _display(value: ParameterValue) -> str:
    if value in (None, "", (), "---"):
        return "(missing)"
    return " | ".join(value) if isinstance(value, tuple) else value


class ComparisonWidget(QWidget):
    def __init__(self, dialogs: Dialogs | None = None):
        super().__init__()
        self._dialogs = dialogs or QtDialogs(self)
        self._variants: list[dict] = []
        self._target: ParameterMap | None = None
        self._base: ParameterMap | None = None
        self._rows: list[ComparisonRow] = []
        self._base_mode = False

        title = QLabel("Comparison")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        subtitle = QLabel(
            "Load a Master Sheet on Home, then select a linked variant. Automatic export is not "
            "available: open the job, use WebFlow's Export XML action, and upload the exported file."
        )
        subtitle.setWordWrap(True)
        set_muted(subtitle, True)

        self._variant_selector = QComboBox()
        self._variant_selector.setMinimumWidth(200)
        self._variant_selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._variant_selector.setToolTip("Variant | SW Part Number (only variants with a WebFlow link)")
        self._open_target_btn = QPushButton("Open target WebFlow")
        self._upload_target_btn = QPushButton("Upload target XML")
        self._target_file = QLabel("No target XML")
        self._target_file.setWordWrap(True)
        target_actions = QHBoxLayout()
        target_actions.addWidget(self._open_target_btn)
        target_actions.addWidget(self._upload_target_btn)
        target_actions.addWidget(self._target_file, 1)

        self._base_link = QLineEdit()
        self._base_link.setPlaceholderText("Optional: https://host/app/ShowJob/123")
        self._open_base_btn = QPushButton("Open base WebFlow")
        self._upload_base_btn = QPushButton("Upload base XML")
        self._base_file = QLabel("No base XML")
        self._base_file.setWordWrap(True)
        base_actions = QHBoxLayout()
        base_actions.addWidget(self._open_base_btn)
        base_actions.addWidget(self._upload_base_btn)
        base_actions.addWidget(self._base_file, 1)

        sources = QFormLayout()
        sources.addRow("Variant | SW Part Number:", self._variant_selector)
        sources.addRow(target_actions)
        sources.addRow("Base WebFlow Link:", self._base_link)
        sources.addRow(base_actions)
        self._compare_btn = QPushButton("Compare")
        self._compare_btn.setEnabled(False)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search parameters, values, variants or status...")
        self._status_filter = QComboBox()
        self._deviations = QCheckBox("Deviations only")
        self._deviations.setToolTip("Hide target values that match Master, including matches to both Master and Base.")
        filters = QHBoxLayout()
        filters.addWidget(self._search, 1)
        filters.addWidget(self._status_filter)
        filters.addWidget(self._deviations)
        filters.addWidget(self._compare_btn)
        self._table = QTableWidget(0, len(_TARGET_HEADERS))
        self._table.setHorizontalHeaderLabels(_TARGET_HEADERS)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(sources)
        layout.addLayout(filters)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._summary)

        self._variant_selector.currentIndexChanged.connect(self._selection_changed)
        self._open_target_btn.clicked.connect(self._open_target)
        self._open_base_btn.clicked.connect(self._open_base)
        self._upload_target_btn.clicked.connect(self._upload_target)
        self._upload_base_btn.clicked.connect(self._upload_base)
        self._base_link.textChanged.connect(self._base_changed)
        self._compare_btn.clicked.connect(self._compare)
        self._search.textChanged.connect(self._apply_filters)
        self._status_filter.currentTextChanged.connect(self._apply_filters)
        self._deviations.toggled.connect(self._apply_filters)
        self._refresh_status_filter()
        self._refresh_variants()
        self._base_changed()

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

    def _selected(self) -> dict | None:
        index = self._variant_selector.currentData()
        return self._variants[index] if index is not None else None

    def _refresh_variants(self) -> None:
        self._variant_selector.blockSignals(True)
        self._variant_selector.clear()
        for index, variant in enumerate(self._variants):
            if not str(variant.get("webflow_link") or "").strip():
                continue
            software = variant.get("hardware", {}).get("software_part_number") or "(missing SW Part Number)"
            self._variant_selector.addItem(f"{variant['part_number']} | {software}", index)
        self._variant_selector.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self, *_args) -> None:
        self._target = None
        self._target_file.setText("No target XML")
        self._open_target_btn.setEnabled(self._selected() is not None)
        self._upload_target_btn.setEnabled(self._selected() is not None)
        self._clear_results()

    def _base_changed(self, *_args) -> None:
        self._base = None
        self._base_file.setText("No base XML")
        enabled = bool(self._base_link.text().strip())
        self._open_base_btn.setEnabled(enabled)
        self._upload_base_btn.setEnabled(enabled)
        self._clear_results()

    def _clear_results(self) -> None:
        self._rows = []
        self._base_mode = bool(self._base_link.text().strip())
        headers = _BASE_HEADERS if self._base_mode else _TARGET_HEADERS
        self._table.setRowCount(0)
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._refresh_status_filter()
        self._compare_btn.setEnabled(self._target is not None and (not self._base_mode or self._base is not None))
        self._summary.setText(
            "Upload exported XML to compare against the loaded Master Sheet."
            if self._selected() is not None else "No linked variants. Load a Master Sheet on Home first."
        )

    def _refresh_status_filter(self) -> None:
        self._status_filter.blockSignals(True)
        self._status_filter.clear()
        self._status_filter.addItem("All statuses")
        statuses = (
            (Status.MATCHES_MASTER, Status.MATCHES_BASE, Status.MATCHES_BOTH, Status.MATCHES_NEITHER)
            if self._base_mode else
            (Status.MATCH, Status.VALUE_MISMATCH, Status.MISSING_IN_MASTER, Status.MISSING_IN_WEBFLOW)
        )
        self._status_filter.addItems([status.value for status in statuses])
        self._status_filter.blockSignals(False)

    def _open_target(self) -> None:
        selected = self._selected()
        if selected is not None:
            self._open_link(selected.get("webflow_link", ""))

    def _open_base(self) -> None:
        self._open_link(self._base_link.text())

    def _open_link(self, link: str) -> None:
        try:
            validated = validate_link(link)
        except ValueError as error:
            self._dialogs.error("Open WebFlow", str(error))
            return
        if not QDesktopServices.openUrl(QUrl(validated)):
            self._dialogs.error("Open WebFlow", "Could not open the WebFlow link in the default browser.")

    def _read_xml(self, path: str) -> ParameterMap:
        with Path(path).open("rb") as source:
            return parse_xml(source.read(MAX_XML_BYTES + 1))

    def _validate_target(self, target: ParameterMap) -> dict:
        selected = self._selected()
        if selected is None:
            raise ValueError("Select a linked Master Sheet variant first.")
        matched = match_variant(self._variants, target)
        if variant_identity(matched) != variant_identity(selected):
            raise ValueError("The uploaded XML does not match the selected Variant + SW Part Number.")
        validate_export_link(target, selected.get("webflow_link", ""))
        return matched

    def _upload_target(self) -> None:
        path = self._dialogs.pick_file("Upload WebFlow target XML", "WebFlow XML (*.xml)")
        if not path:
            return
        self._target = None
        self._target_file.setText("No target XML")
        self._clear_results()
        try:
            target = self._read_xml(path)
            self._validate_target(target)
        except (OSError, ValueError) as error:
            self._dialogs.error("Target XML", str(error))
            return
        self._target = target
        self._target_file.setText(Path(path).name)
        self._clear_results()

    def _upload_base(self) -> None:
        path = self._dialogs.pick_file("Upload WebFlow base XML", "WebFlow XML (*.xml)")
        if not path:
            return
        self._base = None
        self._base_file.setText("No base XML")
        self._clear_results()
        try:
            base = self._read_xml(path)
            validate_export_link(base, self._base_link.text())
        except (OSError, ValueError) as error:
            self._dialogs.error("Base XML", str(error))
            return
        self._base = base
        self._base_file.setText(Path(path).name)
        self._clear_results()

    def _compare(self) -> None:
        self._clear_results()
        try:
            if self._target is None:
                raise ValueError("Upload the target WebFlow Export XML first.")
            matched = self._validate_target(self._target)
            base = None
            if self._base_mode:
                if self._base is None:
                    raise ValueError("Upload Export XML for the Base WebFlow Link first.")
                validate_export_link(self._base, self._base_link.text())
                base = self._base
            self._rows = compare_parameters(master_parameters(matched), self._target, base)
        except ValueError as error:
            self._dialogs.error("Comparison", str(error))
            return
        self._render_results()

    def _render_results(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        self._table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            values = (
                (row.parameter, _display(row.master), _display(row.base), _display(row.target), row.status.value)
                if self._base_mode else
                (selected["part_number"], selected.get("hardware", {}).get("software_part_number", ""),
                 row.parameter, _display(row.master), _display(row.target), row.status.value)
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self._table.setItem(index, column, item)
        self._table.resizeColumnsToContents()
        for column in range(self._table.columnCount()):
            self._table.setColumnWidth(column, min(300, self._table.columnWidth(column)))
        self._apply_filters()

    def _apply_filters(self, *_args) -> None:
        search = self._search.text().strip().casefold()
        status = self._status_filter.currentText()
        visible = 0
        for index, row in enumerate(self._rows):
            text = " ".join(self._table.item(index, column).text() for column in range(self._table.columnCount()))
            show = (
                (not search or search in text.casefold())
                and (status == "All statuses" or status == row.status.value)
                and (not self._deviations.isChecked() or row.deviation)
            )
            self._table.setRowHidden(index, not show)
            visible += int(show)
        if self._rows:
            deviations = sum(row.deviation for row in self._rows)
            self._summary.setText(
                f"{visible} / {len(self._rows)} parameters shown; {deviations} deviations from Master."
            )
