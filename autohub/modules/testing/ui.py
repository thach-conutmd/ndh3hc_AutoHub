"""Test page: one group per area (e.g. WebFlow), each holding a compact button per standalone test feature."""
from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from autohub.modules.testing.features import TestFeature

_ACTION_WIDTH = 240


class TestingWidget(QWidget):
    def __init__(self, features: list[TestFeature], parent: QWidget | None = None):
        super().__init__(parent)
        self._features = features
        page = QVBoxLayout(self)
        page.setAlignment(Qt.AlignmentFlag.AlignTop)
        for group_title, group_features in _grouped(features).items():
            page.addWidget(self._build_group(group_title, group_features))

    def _build_group(self, title: str, features: list[TestFeature]) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet(
            "QGroupBox { border: 1px solid palette(mid); border-radius: 8px; "
            "margin-top: 12px; font-weight: 600; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }"
        )
        group.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        for feature in features:
            layout.addWidget(self._action_button(feature), 0, Qt.AlignmentFlag.AlignLeft)
        return group

    def _action_button(self, feature: TestFeature) -> QPushButton:
        button = QPushButton(feature.title)
        button.setFixedWidth(_ACTION_WIDTH)
        button.setMinimumHeight(32)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button.clicked.connect(lambda _checked=False, f=feature: f.create_dialog(self).exec())
        return button


def _grouped(features: list[TestFeature]) -> "OrderedDict[str, list[TestFeature]]":
    groups: OrderedDict[str, list[TestFeature]] = OrderedDict()
    for feature in features:
        groups.setdefault(feature.group, []).append(feature)
    return groups
