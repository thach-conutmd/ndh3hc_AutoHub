from PySide6.QtWidgets import QWidget

from autohub.core.module_base import AutoHubModule
from autohub.modules.comparison.ui import ComparisonWidget


class ComparisonModule(AutoHubModule):
    display_name = "Comparison"
    icon_file = "comparison.svg"

    def create_widget(self) -> QWidget:
        return ComparisonWidget()
