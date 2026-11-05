"""Hexdump module: navigation entry with a placeholder page until the feature is built."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from autohub.core.module_base import AutoHubModule


class HexdumpModule(AutoHubModule):
    display_name = "Hexdump"
    icon_file = "hexdump.svg"

    def create_widget(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel("Coming Soon")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()
        return page
