from PySide6.QtWidgets import QWidget

from autohub.core.module_base import AutoHubModule
from autohub.core.settings import SettingsStore
from autohub.core.templates import TemplateManager
from autohub.modules.settings.ui import SettingsWidget


class SettingsModule(AutoHubModule):
    display_name = "Settings"
    icon_file = "settings.svg"
    pinned_bottom = True

    def __init__(self, settings: SettingsStore, templates: TemplateManager | None = None):
        self._settings = settings
        self._templates = templates

    def create_widget(self) -> QWidget:
        return SettingsWidget(self._settings, templates=self._templates)
