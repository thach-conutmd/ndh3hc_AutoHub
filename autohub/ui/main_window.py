"""Main application window: sidebar navigation + stacked module pages."""
from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from autohub.config import APP_NAME, APP_VERSION, LOGO_PATH
from autohub.core.capabilities import (
    Closable, LeaveGuard, StartupPreload, StartupTask, VariantSink, VariantSource, WebFlowLinkSink, WebFlowLinkSource,
    WebFlowNumberSink, WebFlowNumberSource,
    WebFlowOptionsSink, WebFlowOptionsSource,
    SettingsSink, SettingsSource,
)
from autohub.core.module_base import AutoHubModule
from autohub.ui.sidebar import Sidebar

_logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, modules: list[AutoHubModule]):
        super().__init__()
        self._base_title = f"{APP_NAME} v{APP_VERSION}"
        self._module_names = [module.display_name for module in modules]
        self.setWindowTitle(self._base_title)
        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_PATH)))
        self.setFixedSize(1024, 700)

        self._sidebar = Sidebar(
            [(module.icon_file, module.display_name) for module in modules],
            [index for index, module in enumerate(modules) if module.pinned_bottom],
        )
        self._pages = QStackedWidget()
        self._current = -1

        widgets = [module.create_widget() for module in modules]
        for widget in widgets:
            self._pages.addWidget(widget)
        self._wire_cross_module_signals(widgets)

        self._sidebar.moduleSelected.connect(self._on_module_selected)
        if modules:
            self._on_module_selected(0)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar)
        layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(central)

    @staticmethod
    def _wire_cross_module_signals(widgets: list[QWidget]) -> None:
        # Pages talk through capability protocols, so MainWindow never knows concrete
        # types, e.g. Home's loaded variants feed Creation's checklist.
        sources = [w for w in widgets if isinstance(w, VariantSource)]
        sinks = [w for w in widgets if isinstance(w, VariantSink)]
        for source in sources:
            for sink in sinks:
                source.variantsLoaded.connect(sink.set_variants)
        link_sources = [w for w in widgets if isinstance(w, WebFlowLinkSource)]
        link_sinks = [w for w in widgets if isinstance(w, WebFlowLinkSink)]
        for source in link_sources:
            for sink in link_sinks:
                source.webflowLinksUpdated.connect(sink.set_webflow_links)
        for source in (w for w in widgets if isinstance(w, WebFlowNumberSource)):
            for sink in (w for w in widgets if isinstance(w, WebFlowNumberSink)):
                source.webflowNumbersUpdated.connect(sink.set_webflow_numbers)
        for source in (w for w in widgets if isinstance(w, WebFlowOptionsSource)):
            for sink in (w for w in widgets if isinstance(w, WebFlowOptionsSink)):
                source.webflowOptionsUpdated.connect(sink.set_webflow_options)
        for source in (w for w in widgets if isinstance(w, SettingsSource)):
            for sink in (w for w in widgets if isinstance(w, SettingsSink)):
                source.settingsChanged.connect(sink.apply_settings)

    def preload(self, progress) -> None:
        """Runs each page's startup loading while the startup dialog is still shown."""
        for i in range(self._pages.count()):
            page = self._pages.widget(i)
            if isinstance(page, StartupPreload):
                page.preload(progress)

    def run_startup_tasks(self) -> None:
        for i in range(self._pages.count()):
            page = self._pages.widget(i)
            if isinstance(page, StartupTask):
                page.on_startup()

    def closeEvent(self, event) -> None:
        if not self._may_leave_current_page():
            event.ignore()
            return
        for i in range(self._pages.count()):
            page = self._pages.widget(i)
            if isinstance(page, Closable):
                page.shutdown()
        super().closeEvent(event)

    def _may_leave_current_page(self) -> bool:
        page = self._pages.currentWidget()
        return not isinstance(page, LeaveGuard) or page.confirm_leave()

    def _on_module_selected(self, index: int) -> None:
        if index != self._current and self._current >= 0 and not self._may_leave_current_page():
            self._sidebar.select_module(self._current)  # the user chose to stay
            return
        self._current = index
        _logger.info("Module selected: %s", self._module_names[index])
        self._pages.setCurrentIndex(index)
        self.setWindowTitle(f"{APP_NAME} - {self._module_names[index]}")
