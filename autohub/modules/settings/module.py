from PySide6.QtWidgets import QWidget

from autohub.core.module_base import AutoHubModule
from autohub.core.settings import SettingsStore
from autohub.modules.settings.ui import SettingsWidget


class SettingsModule(AutoHubModule):
    display_name = "Settings"
    icon_file = "settings.svg"
    pinned_bottom = True

    def __init__(self, settings: SettingsStore):
        self._settings = settings

    def create_widget(self) -> QWidget:
        return SettingsWidget(self._settings)
