from typing import Callable

from PySide6.QtWidgets import QWidget

from autohub.core.module_base import AutoHubModule
from autohub.core.ports import FormBGenerator
from autohub.core.settings import SettingsStore
from autohub.modules.form_b.ui import FormBWidget


class FormBModule(AutoHubModule):
    display_name = "Form B"
    icon_file = "form_b.svg"

    def __init__(self, service_factory: Callable[[], FormBGenerator], settings: SettingsStore | None = None):
        self._service_factory = service_factory
        self._settings = settings

    def create_widget(self) -> QWidget:
        return FormBWidget(self._service_factory(), settings=self._settings)
