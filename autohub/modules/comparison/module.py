from typing import Callable

from PySide6.QtWidgets import QWidget

from autohub.core.module_base import AutoHubModule
from autohub.core.settings import SettingsStore
from autohub.modules.comparison.impl_update import MasterImplUpdater
from autohub.modules.comparison.service import ComparisonService
from autohub.modules.comparison.ui import ComparisonWidget


class ComparisonModule(AutoHubModule):
    display_name = "Comparison"
    icon_file = "comparison.svg"

    def __init__(self, service_factory: Callable[[], ComparisonService], settings: SettingsStore,
                 impl_updater_factory: Callable[[], MasterImplUpdater] | None = None):
        self._service_factory = service_factory
        self._impl_updater_factory = impl_updater_factory
        self._settings = settings

    def create_widget(self) -> QWidget:
        return ComparisonWidget(
            service=self._service_factory(), settings=self._settings,
            impl_updater=self._impl_updater_factory() if self._impl_updater_factory else None,
        )
