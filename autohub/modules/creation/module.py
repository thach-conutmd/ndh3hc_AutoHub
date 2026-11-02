from typing import Callable

from PySide6.QtWidgets import QWidget

from autohub.core.module_base import AutoHubModule
from autohub.core.settings import SettingsStore
from autohub.modules.creation.service import WebFlowJobService
from autohub.modules.creation.ui import CreationWidget


class CreationModule(AutoHubModule):
    display_name = "Creation"
    icon_file = "creation.svg"

    def __init__(self, service_factory: Callable[[], WebFlowJobService], settings: SettingsStore):
        self._service_factory = service_factory
        self._settings = settings

    def create_widget(self) -> QWidget:
        return CreationWidget(self._service_factory(), self._settings)
