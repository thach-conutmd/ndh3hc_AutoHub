"""Test module: standalone checks for individual WebFlow features, independent of the full workflow."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget

from autohub.core.module_base import AutoHubModule
from autohub.modules.testing.features import TestFeature
from autohub.modules.testing.ui import TestingWidget


class TestingModule(AutoHubModule):
    display_name = "Test"
    icon_file = "test.svg"

    def __init__(self, features: list[TestFeature]):
        self._features = features

    def create_widget(self) -> QWidget:
        return TestingWidget(self._features)
