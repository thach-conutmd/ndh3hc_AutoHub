from typing import Callable

from PySide6.QtWidgets import QWidget

from autohub.core.module_base import AutoHubModule
from autohub.core.settings import SettingsStore
from autohub.core.templates import TemplateManager
from autohub.modules.home.service import VariantService
from autohub.modules.home.ui import HomeWidget


class HomeModule(AutoHubModule):
    display_name = "Home"
    icon_file = "home.svg"

    def __init__(
        self,
        service_factory: Callable[[], VariantService],
        settings: SettingsStore,
        templates: TemplateManager | None = None,
    ):
        self._service_factory = service_factory
        self._settings = settings
        self._templates = templates

    def create_widget(self) -> QWidget:
        return HomeWidget(self._service_factory(), self._settings, templates=self._templates)
