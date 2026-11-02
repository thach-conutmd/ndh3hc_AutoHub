"""Home page layout: Master Sheet picker and the variant table. All behaviour lives in HomePresenter."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.settings import SettingsStore
from autohub.core.settings_keys import (
    CALIBRATION_FOLDER_PATH_KEY,
    LATEST_COUNT_KEY,
    SHOW_WEBFLOW_LINK_KEY,
    WEBFLOW_GENERAL_OPTIONS_KEY,
)
from autohub.core.workers import TaskRunner
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
        self._dialogs = dialogs or QtDialogs(self)
        self._file_name_labels: dict[str, QLabel] = {}
        self._variant_table = VariantTable()
        self._variant_table.set_webflow_option_choices(settings.load().get(WEBFLOW_GENERAL_OPTIONS_KEY, {}))

        title = QLabel("Variant workspace")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel("Load a Master Sheet, review variants, and prepare your WebFlow jobs.")
        subtitle.setWordWrap(True)
        set_muted(subtitle, True)

        browse_btn = QPushButton(f"Load {MASTER_SHEET}")
        self._browse_btn = browse_btn
        browse_btn.setMinimumWidth(140)
        self._open_master_btn = QPushButton(f"Open {MASTER_SHEET}")
        self._open_master_btn.setEnabled(False)
        self._open_master_btn.setToolTip("Open the selected Master Sheet in its default application.")
        name_label = QLabel()
        name_label.setMinimumWidth(_FILE_NAME_LABEL_WIDTH)
        name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name_label.setWordWrap(True)
        set_muted(name_label, True)
        self._file_name_labels[MASTER_SHEET] = name_label
        files_row = QHBoxLayout()
        files_row.setSpacing(16)
        files_row.addWidget(name_label, 1)
        files_row.addWidget(browse_btn)
        files_row.addWidget(self._open_master_btn)

        self._create_btn = QPushButton(NEW_VARIANT_TEXT)
        self._create_btn.setEnabled(False)
        self._create_btn.setMinimumWidth(120)
        self._create_btn.setToolTip(NEW_VARIANT_TIP)
        self._load_btn = QPushButton(LOAD_TEXT)
        self._load_btn.setEnabled(False)
        self._load_btn.setMinimumWidth(120)
        files_row.addWidget(self._load_btn)

        sheet_group = QGroupBox("Master Sheet")
        sheet_group.setStyleSheet(
            "QGroupBox { border: 1px solid palette(mid); border-radius: 8px; "
            "margin-top: 12px; font-weight: 600; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }"
        )
        sheet_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        sheet_layout = QVBoxLayout(sheet_group)
        sheet_layout.setContentsMargins(16, 14, 16, 8)
        sheet_layout.addLayout(files_row)

        self._row_summary = QLabel("No variants loaded")
        set_muted(self._row_summary, True)
        table_title = QLabel("Variants")
        table_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        table_header = QHBoxLayout()
        table_header.addWidget(table_title)
        table_header.addWidget(self._row_summary)
        table_header.addStretch(1)
        table_header.addWidget(self._create_btn)
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
        for button in (browse_btn, self._load_btn, self._create_btn, self._update_btn, self._clear_btn, self._delete_btn):
            button.setMinimumHeight(32)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(sheet_group)
        layout.addSpacing(4)
        layout.addLayout(table_header)
        layout.addWidget(self._variant_table, 1)
        layout.addLayout(write_row)

        model = self._variant_table.model()
        model.rowsInserted.connect(self._refresh_row_summary)
        model.rowsRemoved.connect(self._refresh_row_summary)
        model.modelReset.connect(self._refresh_row_summary)
        self._variant_table.selectionModel().selectionChanged.connect(self._refresh_row_summary)
        self._tasks = TaskRunner()
        self._master_watcher = QFileSystemWatcher(self)
        self._master_check_timer = QTimer(self)
        self._master_check_timer.setSingleShot(True)
        self._master_check_timer.setInterval(250)
        self._master_check_timer.timeout.connect(self._revalidate_master)
        self._master_watcher.fileChanged.connect(lambda _: self._master_check_timer.start())
        self._master_watcher.directoryChanged.connect(lambda _: self._master_check_timer.start())
        self._presenter = HomePresenter(self, service, settings, self._dialogs, self._tasks.start)
        browse_btn.clicked.connect(lambda _checked: self._presenter.browse_master_sheet())
        self._open_master_btn.clicked.connect(self._on_open_master_sheet)
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

    def preload(self, progress) -> None:
        self._presenter.auto_load_variants(progress)

    # -- HomeView ----------------------------------------------------------------------

    def _refresh_row_summary(self, *_args) -> None:
        count = self.row_count()
        selected = len(self.selected_rows())
        summary = f"{count} variant{'s' if count != 1 else ''}" if count else "No variants loaded"
        if selected:
            summary += f" | {selected} selected"
        self._row_summary.setText(summary)

    def show_file_name(self, field_name: str, path: str) -> None:
        label = self._file_name_labels.get(field_name)
        if label is None:
            return
        valid = bool(path) and Path(path).is_file()
        label.setText(Path(path).name if valid else "")
        label.setToolTip(path if valid else "")
        set_muted(label, not valid)
        if field_name == MASTER_SHEET:
            self._open_master_btn.setEnabled(valid)
            watched = self._master_watcher.files() + self._master_watcher.directories()
            if watched:
                self._master_watcher.removePaths(watched)
            if valid:
                self._master_watcher.addPaths([str(Path(path).resolve()), str(Path(path).resolve().parent)])

    def _revalidate_master(self) -> None:
        if self._presenter._busy:
            self._master_check_timer.start()
            return
        if self._presenter.revalidate_master_sheet():
            path = self._settings.load().get("master_sheet_path", "")
            self.show_file_name(MASTER_SHEET, path)

    def _on_open_master_sheet(self) -> None:
        if not self._presenter.revalidate_master_sheet("Open Master Sheet"):
            return
        path = str(self._settings.load().get("master_sheet_path", "")).strip()
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve()))):
            self._dialogs.error("Open Master Sheet", f"Could not open the Master Sheet:\n{path}")

    def show_rows(self, rows: list[dict]) -> None:
        self._variant_table.populate(rows)

    def reload_master(self) -> None:
        self._presenter.reload_variants()

    def set_webflow_links(self, links: dict[str, str]) -> None:
        if not self._presenter.revalidate_master_sheet():
            return
        self._variant_table.set_webflow_links(links)
        self._presenter.set_webflow_links(links)

    def set_webflow_numbers(self, numbers: dict[str, dict[str, str]], persisted: bool = True) -> None:
        if not self._presenter.revalidate_master_sheet():
            return
        self._variant_table.set_webflow_numbers(numbers)
        self._presenter.set_webflow_numbers(numbers, persisted)

    def set_webflow_options(self, options: dict[str, list[str]]) -> None:
        self._variant_table.set_webflow_option_choices(options)

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

    def set_workspace_enabled(self, enabled: bool, busy: bool = False) -> None:
        self._variant_table.setEnabled(enabled)
        self._browse_btn.setEnabled(not busy)

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
        folder_path = str(self._settings.load().get(CALIBRATION_FOLDER_PATH_KEY, "")).strip()
        if folder_path:
            folder = Path(folder_path)
            for variant in variants:
                filename = str(variant.get("hardware", {}).get("data_version") or "").strip()
                if Path(filename).suffix.casefold() == ".hex":
                    variant["_calibration_hex_path"] = str(folder / Path(filename).name)
        self.variantsLoaded.emit(variants)
