"""Home page layout: Master Sheet picker and the variant table. All behaviour lives in HomePresenter."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from autohub.config import HOME_BANNER_PATH
from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.settings import SettingsStore
from autohub.core.settings_keys import LATEST_COUNT_KEY, SHOW_WEBFLOW_LINK_KEY
from autohub.core.workers import TaskRunner
from autohub.modules.home.banner import BannerLabel
from autohub.modules.home.presenter import (
    LOAD_TEXT,
    MASTER_SHEET,
    NEW_VARIANT_TEXT,
    NEW_VARIANT_TIP,
    UPDATE_TEXT,
    HomePresenter,
)
from autohub.modules.home.service import VariantService
from autohub.modules.home.variant_table import VariantTable
from autohub.ui.theme import set_muted

_FILE_NAME_LABEL_WIDTH = 150


class HomeWidget(QWidget):
    #: emitted with the list of WebFlow-ready variant dicts once created/loaded.
    variantsLoaded = Signal(list)

    def __init__(self, service: VariantService, settings: SettingsStore, dialogs: Dialogs | None = None):
        super().__init__()

        self._settings = settings
        self._banner = BannerLabel(HOME_BANNER_PATH)
        self._file_name_labels: dict[str, QLabel] = {}
        self._variant_table = VariantTable()

        browse_btn = QPushButton(f"Load {MASTER_SHEET}")
        browse_btn.setMinimumWidth(140)
        name_label = QLabel("Not selected")
        name_label.setMinimumWidth(_FILE_NAME_LABEL_WIDTH)
        set_muted(name_label, True)
        self._file_name_labels[MASTER_SHEET] = name_label
        files_row = QHBoxLayout()
        files_row.setSpacing(16)
        files_row.addWidget(browse_btn)
        files_row.addWidget(name_label)
        files_row.addStretch(1)

        self._create_btn = QPushButton(NEW_VARIANT_TEXT)
        self._create_btn.setMinimumWidth(120)
        self._create_btn.setToolTip(NEW_VARIANT_TIP)
        self._load_btn = QPushButton(LOAD_TEXT)
        self._load_btn.setMinimumWidth(120)
        files_row.addWidget(self._create_btn)
        files_row.addWidget(self._load_btn)


        self._update_btn = QPushButton(UPDATE_TEXT)
        self._update_btn.setEnabled(False)
        self._clear_btn = QPushButton("Clear table")
        self._clear_btn.setEnabled(False)
        self._delete_btn = QPushButton("Delete selected")
        self._delete_btn.setToolTip("Delete the variants of the selected rows (also from the Master Sheet after Update).")
        self._delete_btn.setEnabled(False)
        write_row = QHBoxLayout()
        write_row.addWidget(self._clear_btn)
        write_row.addWidget(self._delete_btn)
        write_row.addStretch(1)
        write_row.addWidget(self._update_btn)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(14)
        layout.addWidget(self._banner)
        layout.addLayout(files_row)
        layout.addWidget(self._variant_table, 1)
        layout.addLayout(write_row)

        self._tasks = TaskRunner()
        self._presenter = HomePresenter(self, service, settings, dialogs or QtDialogs(self), self._tasks.start)
        browse_btn.clicked.connect(lambda _checked: self._presenter.browse_master_sheet())
        self._create_btn.clicked.connect(self._presenter.new_variant)
        self._load_btn.clicked.connect(self._presenter.load_variants)
        self._update_btn.clicked.connect(self._presenter.update_master_sheet)
        self._clear_btn.clicked.connect(self._presenter.clear_table)
        self._delete_btn.clicked.connect(self._presenter.delete_selected)
        self._variant_table.userEdited.connect(self._presenter.on_table_edited)
        self._variant_table.selectionModel().selectionChanged.connect(
            lambda *_: self._presenter.on_selection_changed()
        )
        self._presenter.restore_saved_paths()
        self._variant_table.set_webflow_link_visible(self._show_webflow_link())

    # -- HomeView ----------------------------------------------------------------------

    def show_file_name(self, field_name: str, path: str) -> None:
        label = self._file_name_labels.get(field_name)
        if label is None:
            return
        label.setText(Path(path).name)
        label.setToolTip(path)
        set_muted(label, False)

    def show_rows(self, rows: list[dict]) -> None:
        self._variant_table.populate(rows)

    def set_webflow_links(self, links: dict[str, str]) -> None:
        self._variant_table.set_webflow_links(links)
        self._presenter.set_webflow_links(links)

    def set_webflow_numbers(self, numbers: dict[str, dict[str, str]], persisted: bool = True) -> None:
        self._variant_table.set_webflow_numbers(numbers)
        self._presenter.set_webflow_numbers(numbers, persisted)

    def apply_settings(self, changes: dict) -> None:
        if SHOW_WEBFLOW_LINK_KEY in changes:
            self._variant_table.set_webflow_link_visible(self._show_webflow_link())
        if LATEST_COUNT_KEY in changes:
            self._presenter.refresh_latest_rows()

    def _show_webflow_link(self) -> bool:
        return bool(self._settings.load().get(SHOW_WEBFLOW_LINK_KEY, False))

    def read_rows(self) -> list[dict]:
        return self._variant_table.read()

    def row_count(self) -> int:
        return self._variant_table.rowCount()

    def clear_rows(self) -> None:
        self._variant_table.clear_rows()

    def set_new_variant_state(self, enabled: bool, text: str) -> None:
        self._create_btn.setEnabled(enabled)
        self._create_btn.setText(text)

    def set_load_state(self, enabled: bool, text: str) -> None:
        self._load_btn.setEnabled(enabled)
        self._load_btn.setText(text)

    def set_update_state(self, enabled: bool, text: str) -> None:
        self._update_btn.setEnabled(enabled)
        self._update_btn.setText(text)

    def set_clear_enabled(self, enabled: bool) -> None:
        self._clear_btn.setEnabled(enabled)

    def set_delete_enabled(self, enabled: bool) -> None:
        self._delete_btn.setEnabled(enabled)

    def selected_rows(self) -> list[int]:
        return self._variant_table.selected_rows()

    def remove_rows(self, rows: list[int]) -> None:
        self._variant_table.remove_rows(rows)

    def publish_variants(self, variants: list[dict]) -> None:
        self.variantsLoaded.emit(variants)
