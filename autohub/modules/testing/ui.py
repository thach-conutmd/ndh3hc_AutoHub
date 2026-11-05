"""Test page: one button per standalone test feature."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from autohub.modules.testing.features import TestFeature


class TestingWidget(QWidget):
    def __init__(self, features: list[TestFeature], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._features = features
        for feature in features:
            button = QPushButton(feature.title)
            button.clicked.connect(lambda _checked=False, f=feature: f.create_dialog(self).exec())
            layout.addWidget(button)
