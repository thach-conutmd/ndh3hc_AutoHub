"""Hexdump page: check a capture settings file and look up the line range of a key in a dump file."""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
    QWidget,
)

from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.ports import HexdumpAnalysis
from autohub.core.workers import TaskRunner
from autohub.ui.theme import set_muted

_logger = logging.getLogger(__name__)
_TOML_FILTER = "TOML settings (*.toml);;All files (*)"
_ANY_FILTER = "All files (*)"


class HexdumpWidget(QWidget):
    def __init__(self, service: HexdumpAnalysis, dialogs: Dialogs | None = None):
        super().__init__()
        self._service = service
        self._dialogs = dialogs or QtDialogs(self)
        self._tasks = TaskRunner()
        self._busy = False

        title = QLabel("Hexdump")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel("Check a capture settings file, or find the line range of a key in a dump file.")
        subtitle.setWordWrap(True)
        set_muted(subtitle, True)

        self._settings_path = QLineEdit()
        self._settings_path.setPlaceholderText("Path to a .toml settings file")
        self._settings_check_btn = QPushButton("Check Settings")
        self._settings_check_btn.clicked.connect(self._check_settings)
        self._browse_settings_btn = self._browse_button(self._settings_path, "Select settings file", _TOML_FILTER)
        self._settings_result = QPlainTextEdit()
        self._settings_result.setReadOnly(True)
        self._settings_result.setMinimumHeight(140)
        settings_group = self._group("Settings check", [
            self._path_row(self._settings_path, self._browse_settings_btn, self._settings_check_btn),
            self._settings_result,
        ])

        self._mode = QComboBox()
        self._mode.addItems(list(self._service.modes()))
        self._dump_path = QLineEdit()
        self._dump_path.setPlaceholderText("Path to the dump file")
        self._browse_dump_btn = self._browse_button(self._dump_path, "Select dump file", _ANY_FILTER)
        self._key = QLineEdit()
        self._key.setPlaceholderText("Key (block name, parameter name, block id or FEE key)")
        self._find_btn = QPushButton("Find Range")
        self._find_btn.clicked.connect(self._find_range)
        self._range_result = QLabel("")
        self._range_result.setWordWrap(True)
        lookup_grid = QGridLayout()
        lookup_grid.setHorizontalSpacing(12)
        lookup_grid.setVerticalSpacing(8)
        lookup_grid.addWidget(QLabel("Mode"), 0, 0)
        lookup_grid.addWidget(self._mode, 0, 1)
        lookup_grid.addWidget(QLabel("Dump file"), 1, 0)
        lookup_grid.addLayout(self._path_row(self._dump_path, self._browse_dump_btn), 1, 1)
        lookup_grid.addWidget(QLabel("Key"), 2, 0)
        lookup_grid.addWidget(self._key, 2, 1)
        lookup_grid.setColumnStretch(1, 1)
        lookup_footer = QHBoxLayout()
        lookup_footer.addWidget(self._range_result, 1)
        lookup_footer.addWidget(self._find_btn)
        range_group = self._group("Find line range", [lookup_grid, lookup_footer])

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(settings_group)
        root.addWidget(range_group)
        root.addStretch(1)

    @staticmethod
    def _group(title: str, rows: list) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet(
            "QGroupBox { font-size: 16px; font-weight: 600; border: 1px solid palette(mid);"
            " border-radius: 8px; margin-top: 8px; padding: 12px; }"
        )
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        for row in rows:
            if isinstance(row, QWidget):
                layout.addWidget(row)
            else:
                layout.addLayout(row)
        return group

    def _browse_button(self, target: QLineEdit, title: str, file_filter: str) -> QPushButton:
        button = QPushButton("Browse…")
        button.clicked.connect(lambda: self._pick(target, title, file_filter))
        return button

    def _path_row(self, field: QLineEdit, *widgets: QPushButton) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(field, 1)
        for widget in widgets:
            row.addWidget(widget)
        return row

    def _pick(self, target: QLineEdit, title: str, file_filter: str) -> None:
        path = self._dialogs.pick_file(title, file_filter)
        if path:
            target.setText(path)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in (self._settings_check_btn, self._find_btn, self._browse_settings_btn, self._browse_dump_btn):
            button.setEnabled(not busy)

    def _check_settings(self) -> None:
        if self._busy:
            return
        path = self._settings_path.text().strip()
        if not path:
            self._settings_result.setPlainText("Select a settings file first.")
            return
        self._set_busy(True)
        self._settings_result.setPlainText("Checking…")
        self._tasks.start(
            lambda: self._service.check_settings(path),
            self._on_settings_ok,
            self._on_settings_error,
        )

    def _on_settings_ok(self, summary: str) -> None:
        self._set_busy(False)
        self._settings_result.setPlainText(summary)

    def _on_settings_error(self, message: str) -> None:
        self._set_busy(False)
        self._settings_result.setPlainText(f"Settings are invalid:\n{message}")

    def _find_range(self) -> None:
        if self._busy:
            return
        mode, path, key = self._mode.currentText(), self._dump_path.text().strip(), self._key.text().strip()
        if not path or not key:
            self._range_result.setText("Enter a dump file and a key.")
            return
        self._set_busy(True)
        self._range_result.setText("Searching…")
        self._tasks.start(
            lambda: self._service.find_range(mode, path, key),
            self._on_range_ok,
            self._on_range_error,
        )

    def _on_range_ok(self, result: tuple[int, int]) -> None:
        self._set_busy(False)
        start, end = result
        self._range_result.setText(f"Lines {start} – {end}")

    def _on_range_error(self, message: str) -> None:
        self._set_busy(False)
        self._range_result.setText(f"Not found: {message}")
