from typing import Callable

from PySide6.QtWidgets import QWidget

from autohub.core.module_base import AutoHubModule
from autohub.core.ports import HexdumpAnalysis
from autohub.modules.hexdump.ui import HexdumpWidget


class HexdumpModule(AutoHubModule):
    display_name = "Hexdump"
    icon_file = "hexdump.svg"

    def __init__(self, service_factory: Callable[[], HexdumpAnalysis]):
        self._service_factory = service_factory

    def create_widget(self) -> QWidget:
        return HexdumpWidget(self._service_factory())
