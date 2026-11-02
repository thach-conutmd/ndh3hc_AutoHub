"""Settings page for theme, logging, WebFlow tracing and retry attempts."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
)

from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.logger import (
    LOG_FILE_PATH, LOGGING_ENABLED_KEY, clear_log_file, logging_enabled, set_logging_enabled,
)
from autohub.core.a2l_hex import DEFAULT_COMP_ID_SYMBOL
from autohub.core.settings import SettingsStore
from autohub.core.settings_keys import NEW_VARIANT_DEFAULTS_KEY
from autohub.core.webflow_defaults import new_variant_defaults
from autohub.core.settings_keys import (
    A2L_COMP_ID_SYMBOL_KEY,
    DEFAULT_WEBFLOW_MAX_ATTEMPTS,
    LATEST_COUNT_CHOICES,
    LATEST_COUNT_KEY,
    RECORD_PAGES_KEY,
    SHOW_WEBFLOW_LINK_KEY,
    WEBFLOW_ATTEMPTS_LIMIT,
    WEBFLOW_MAX_ATTEMPTS_KEY,
    WEBFLOW_RETRY_ENABLED_KEY,
    normalize_latest_count,
    DEFAULT_XML_COMPARISON_EXCLUSIONS,
    XML_COMPARISON_EXCLUSIONS_KEY,
    XML_COMPARISON_EXCLUSIONS_MASTER_ONLY_KEY,
    XML_COMPARISON_DISABLED_EXCLUSIONS_KEY,
)
from autohub.modules.comparison.xml_parser import comparison_exclusions
from autohub.ui.theme import DEFAULT_THEME_MODE, apply_theme, normalize_theme_mode, set_muted
from autohub.modules.settings.creation_form import CreationSettingsForm, load_config
from autohub.modules.settings.new_variant_form import NewVariantSettingsForm

THEME_KEY = "theme"
_LABELS = {"system": "System", "light": "Light", "dark": "Dark"}


class SettingsWidget(QWidget):
    settingsChanged = Signal(dict)

    def __init__(self, settings: SettingsStore, dialogs: Dialogs | None = None):
        super().__init__()
        self._settings = settings
        self._dialogs = dialogs or QtDialogs(self)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")

        self._theme = QComboBox()
        for mode, label in _LABELS.items():
            self._theme.addItem(label, mode)
        saved = normalize_theme_mode(settings.load().get(THEME_KEY, DEFAULT_THEME_MODE))
        self._theme.setCurrentIndex(self._theme.findData(saved))
        self._theme.setToolTip("System follows the Windows light / dark setting.")

        self._logging = QCheckBox("Enable application logging")
        self._logging.setChecked(logging_enabled(settings.load()))

        self._record = QCheckBox("Record WebFlow steps for analysis")
        self._record.setChecked(bool(settings.load().get(RECORD_PAGES_KEY, True)))

        self._retry = QCheckBox("Enable automatic retries")
        self._retry.setChecked(settings.load().get(WEBFLOW_RETRY_ENABLED_KEY, True))
        self._retry.setToolTip("When disabled, WebFlow runs once. Crash recovery still asks before resuming.")

        self._attempts = QSpinBox()
        self._attempts.setRange(1, WEBFLOW_ATTEMPTS_LIMIT)
        self._attempts.setValue(settings.load().get(WEBFLOW_MAX_ATTEMPTS_KEY, DEFAULT_WEBFLOW_MAX_ATTEMPTS))
        self._attempts.setEnabled(self._retry.isChecked())
        self._retry.toggled.connect(self._attempts.setEnabled)
        self._attempts.setToolTip(
            "Includes the first attempt. Set to 1 to disable automatic retries. "
            "Retries resume saved progress, with a 5-second delay. After a crash, "
            "AutoHub asks before resuming with the batch's saved settings."
        )

        self._latest = QComboBox()
        for count in LATEST_COUNT_CHOICES:
            self._latest.addItem(str(count) if count else "All", count)
        self._latest.setCurrentIndex(self._latest.findData(
            normalize_latest_count(settings.load().get(LATEST_COUNT_KEY, 0))
        ))
        self._latest.setToolTip("How many of the latest variants Load variants shows.")
        self._show_link = QCheckBox("Show the WebFlow link column")
        self._show_link.setChecked(bool(settings.load().get(SHOW_WEBFLOW_LINK_KEY, False)))
        self._a2l_comp_id_symbol = QLineEdit(
            str(settings.load().get(A2L_COMP_ID_SYMBOL_KEY, DEFAULT_COMP_ID_SYMBOL))
        )
        self._a2l_comp_id_symbol.setToolTip(
            "A2L CHARACTERISTIC or MEASUREMENT name used to read the component ID from the HEX file."
        )
        home_group = QGroupBox("Home")
        home_form = QFormLayout(home_group)
        home_form.addRow("Latest variants:", self._latest)
        home_form.addRow(self._show_link)
        home_form.addRow("A2L component ID symbol:", self._a2l_comp_id_symbol)

        theme_group = QGroupBox("Theme")
        QFormLayout(theme_group).addRow("Mode:", self._theme)

        logging_group = QGroupBox("Logging")
        logging_layout = QVBoxLayout(logging_group)
        logging_layout.addWidget(self._logging)
        self._open_log = QPushButton("Open log file")
        self._open_log.clicked.connect(self._on_open_log)
        self._clear_log = QPushButton("Clear log content")
        self._clear_log.clicked.connect(self._on_clear_log)
        log_actions = QHBoxLayout()
        log_actions.addWidget(self._open_log)
        log_actions.addWidget(self._clear_log)
        log_actions.addStretch(1)
        logging_layout.addLayout(log_actions)

        analysis_group = QGroupBox("Analysis")
        QVBoxLayout(analysis_group).addWidget(self._record)

        retry_group = QGroupBox("WebFlow Retry")
        retry_form = QFormLayout(retry_group)
        retry_form.addRow(self._retry)
        retry_form.addRow("Maximum WebFlow attempts:", self._attempts)

        creation_group = QGroupBox("Creation")
        self._creation = CreationSettingsForm(load_config(settings))
        QVBoxLayout(creation_group).addWidget(self._creation)

        new_variants_group = QGroupBox("New variants")
        self._new_variant_defaults = NewVariantSettingsForm(new_variant_defaults(settings.load()))
        QVBoxLayout(new_variants_group).addWidget(self._new_variant_defaults)

        exclusions_group = QGroupBox("Exclude Compare Data")
        exclusions_layout = QVBoxLayout(exclusions_group)
        self._exclusions_master_only = QCheckBox("Apply to Master Sheet Compare")
        self._exclusions_master_only.setChecked(
            bool(settings.load().get(XML_COMPARISON_EXCLUSIONS_MASTER_ONLY_KEY, False))
        )
        exclusions_layout.addWidget(self._exclusions_master_only)
        self._exclusions = QTableWidget(0, 3)
        self._exclusions.setHorizontalHeaderLabels(("Path prefix", "", ""))
        self._exclusions.verticalHeader().hide()
        self._exclusions.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2):
            self._exclusions.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        exclusions_layout.addWidget(self._exclusions)
        self._add_exclusion_btn = QPushButton("+ Add exclusion")
        self._restore_exclusions_btn = QPushButton("Restore defaults")
        self._add_exclusion_btn.clicked.connect(lambda: self._add_exclusion(""))
        self._restore_exclusions_btn.clicked.connect(
            lambda: self._restore_exclusions(DEFAULT_XML_COMPARISON_EXCLUSIONS)
        )
        exclusion_actions = QHBoxLayout()
        exclusion_actions.addWidget(self._add_exclusion_btn)
        exclusion_actions.addWidget(self._restore_exclusions_btn)
        exclusion_actions.addStretch(1)
        exclusions_layout.addLayout(exclusion_actions)
        try:
            saved = settings.load()
            self._restore_exclusions(
                comparison_exclusions(saved, enabled_only=False),
                comparison_exclusions({XML_COMPARISON_EXCLUSIONS_KEY: saved.get(XML_COMPARISON_DISABLED_EXCLUSIONS_KEY, [])}),
            )
        except ValueError as error:
            self._dialogs.error("XML Comparison Exclusions", str(error))
            self._restore_exclusions(("",))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        subtitle = QLabel("Personalize AutoHub and configure your WebFlow workflow.")
        set_muted(subtitle, True)
        layout.addWidget(subtitle)
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        descriptions = {
            theme_group: "Choose a comfortable appearance. System follows your Windows theme.",
            logging_group: "Write application activity to logs/autohub.log and the console.",
            analysis_group: "Save HTML, screenshots and element details in logs/webflow_trace. "
                            "Detailed recording uses additional disk space.",
            home_group: "Control Home's variant list and configure the A2L component-ID symbol.",
            creation_group: "Configure the WebFlow connection and ECR details. Leave all four ECR "
                            "fields empty to skip ECR import, or complete all four to enable it.",
            new_variants_group: "Set the default values used when New variants builds Master Sheet rows. "
                                "Configurator Items are not defaults; required values must be filled in the "
                                "Master Sheet before creating WebFlow jobs.",
            retry_group: "Recover from browser failures without recreating completed jobs. "
                         "After an app crash, AutoHub asks before resuming saved progress.",
            exclusions_group: "Exclude parameters/rows whose normalized paths start with these prefixes. "
                              "A trailing / excludes an entire hierarchy. Excluded rows are not compared or shown. "
                              "Always applies to Manual XML Compare. Enable the option below to also apply "
                              "to Master Sheet Compare. "
                              "An empty list excludes nothing. "
                              "Uncheck a row to keep it saved without excluding it. "
                              "Changes apply to new comparisons after Apply changes.",
        }
        for tab_name, groups in (
            ("General", (theme_group,)),
            ("Home", (home_group,)),
            ("Creation", (creation_group, new_variants_group, retry_group)),
            ("Diagnostics", (logging_group, analysis_group)),
            ("Comparison", (exclusions_group,)),
        ):
            content = QWidget()
            groups_layout = QVBoxLayout(content)
            groups_layout.setContentsMargins(16, 16, 16, 16)
            groups_layout.setSpacing(18)
            for group in groups:
                group.layout().setContentsMargins(16, 24, 16, 16)
                group.layout().setSpacing(12)
                group.setStyleSheet(
                    "QGroupBox { border: 1px solid palette(mid); border-radius: 8px; "
                    "margin-top: 12px; font-weight: 600; }"
                    "QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }"
                )
                description = QLabel(descriptions[group])
                description.setWordWrap(True)
                set_muted(description, True)
                group_layout = group.layout()
                if isinstance(group_layout, QFormLayout):
                    group_layout.insertRow(0, description)
                else:
                    group_layout.insertWidget(0, description)
                groups_layout.addWidget(group)
            groups_layout.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setWidget(content)
            self._tabs.addTab(scroll, tab_name)
        layout.addWidget(self._tabs, 1)
        self._save_status = QLabel("All changes saved")
        set_muted(self._save_status, True)
        self._apply = QPushButton("Apply changes")
        self._apply.setMinimumWidth(130)
        self._apply.setMinimumHeight(32)
        self._apply.setToolTip("Save and apply changes across all settings tabs.")
        self._apply.clicked.connect(self._on_apply)
        self._applied = self._current()
        self._theme.currentIndexChanged.connect(self._refresh_apply)
        self._logging.toggled.connect(self._refresh_apply)
        self._record.toggled.connect(self._refresh_apply)
        self._attempts.valueChanged.connect(self._refresh_apply)
        self._retry.toggled.connect(self._refresh_apply)
        self._latest.currentIndexChanged.connect(self._refresh_apply)
        self._show_link.toggled.connect(self._refresh_apply)
        self._a2l_comp_id_symbol.textChanged.connect(self._refresh_apply)
        self._exclusions_master_only.toggled.connect(self._refresh_apply)
        self._exclusions.itemChanged.connect(self._refresh_apply)
        for field in (
            self._creation._tool_version, self._creation._routing,
            self._creation._change_engineer, self._creation._cost_allocation,
        ):
            field.textChanged.connect(self._refresh_apply)
        for field in self._new_variant_defaults._text_fields.values():
            field.textChanged.connect(self._refresh_apply)
        for field in self._new_variant_defaults._boolean_fields.values():
            field.toggled.connect(self._refresh_apply)
        self._new_variant_defaults._project_number.valueChanged.connect(self._refresh_apply)
        self._creation._change_reason.itemChanged.connect(self._refresh_apply)
        self._creation._environment_buttons.buttonToggled.connect(self._refresh_apply)
        self._refresh_apply()
        footer = QHBoxLayout()
        footer.addWidget(self._save_status)
        footer.addStretch(1)
        footer.addWidget(self._apply)
        layout.addLayout(footer)

    def _exclusion_values(self) -> tuple[str, ...]:
        return tuple(self._exclusions.item(row, 0).text().strip() for row in range(self._exclusions.rowCount()))

    def _disabled_exclusion_values(self) -> tuple[str, ...]:
        return tuple(
            self._exclusions.item(row, 0).text().strip()
            for row in range(self._exclusions.rowCount())
            if self._exclusions.item(row, 0).checkState() != Qt.Checked
        )

    def _add_exclusion(self, value: str, enabled: bool = True) -> None:
        blocked = self._exclusions.blockSignals(True)
        row = self._exclusions.rowCount()
        self._exclusions.insertRow(row)
        item = QTableWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
        self._exclusions.setItem(row, 0, item)
        edit = QPushButton("Edit")
        edit.clicked.connect(lambda: self._exclusions.editItem(item))
        delete = QPushButton("Delete")
        delete.clicked.connect(lambda: self._delete_exclusion(item))
        self._exclusions.setCellWidget(row, 1, edit)
        self._exclusions.setCellWidget(row, 2, delete)
        self._exclusions.blockSignals(blocked)
        if hasattr(self, "_applied"):
            self._refresh_apply()
        if not value:
            self._exclusions.setCurrentItem(item)
            self._exclusions.editItem(item)

    def _delete_exclusion(self, item: QTableWidgetItem) -> None:
        self._exclusions.removeRow(item.row())
        self._refresh_apply()

    def _restore_exclusions(self, values, disabled=()) -> None:
        self._exclusions.blockSignals(True)
        self._exclusions.setRowCount(0)
        for value in values:
            self._add_exclusion(value, value not in disabled)
        self._exclusions.blockSignals(False)
        if hasattr(self, "_applied"):
            self._refresh_apply()

    def _on_open_log(self) -> None:
        if not LOG_FILE_PATH.is_file():
            self._dialogs.error("Open log file", f"Log file does not exist:\n{LOG_FILE_PATH}")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_FILE_PATH.resolve()))):
            self._dialogs.error("Open log file", f"Could not open the log file:\n{LOG_FILE_PATH}")

    def _on_clear_log(self) -> None:
        if not self._dialogs.confirm("Clear log content", "Permanently clear all application log content?"):
            return
        try:
            clear_log_file()
        except OSError as error:
            self._dialogs.error("Clear log content", f"Could not clear the log file:\n{error}")
            return
        self._dialogs.info("Clear log content", "Application log content cleared.")

    def _current(self) -> tuple:
        return (
            self._theme.currentData(), self._logging.isChecked(), self._record.isChecked(),
            self._attempts.value(), self._retry.isChecked(),
            self._latest.currentData(), self._show_link.isChecked(),
            *self._creation.values().values(),
            *self._new_variant_defaults.values().values(),
            self._exclusions_master_only.isChecked(),
            self._a2l_comp_id_symbol.text().strip(),
            self._disabled_exclusion_values(),
            self._exclusion_values(),
        )

    def _refresh_apply(self, *_args) -> None:
        """Apply is only available while the page differs from what is applied."""
        self._apply.setEnabled(self._current() != self._applied)
        self._save_status.setText("Unsaved changes" if self._apply.isEnabled() else "All changes saved")

    def confirm_leave(self) -> bool:
        """Asks what to do with pending changes; False (Cancel) keeps the user on this page."""
        if not self._apply.isEnabled():
            return True
        answer = self._dialogs.ask_yes_no_cancel(
            "Unapplied settings", "You changed settings but did not apply them.\nApply them before leaving?",
            yes_text="Apply", no_text="Discard",
        )
        if answer is None:
            return False
        if answer:
            self._on_apply()
            return not self._apply.isEnabled()
        else:
            self._theme.setCurrentIndex(self._theme.findData(self._applied[0]))
            self._logging.setChecked(self._applied[1])
            self._record.setChecked(self._applied[2])
            self._attempts.setValue(self._applied[3])
            self._retry.setChecked(self._applied[4])
            self._latest.setCurrentIndex(self._latest.findData(self._applied[5]))
            self._show_link.setChecked(self._applied[6])
            creation_count = len(self._creation.values())
            defaults_start = 7 + creation_count
            defaults_count = len(self._new_variant_defaults.values())
            exclusions_start = defaults_start + defaults_count
            self._creation.restore(dict(zip(
                self._creation.values(), self._applied[7:defaults_start]
            )))
            self._new_variant_defaults.restore(dict(zip(
                self._new_variant_defaults.values(),
                self._applied[defaults_start:exclusions_start],
            )))
            self._exclusions_master_only.setChecked(self._applied[exclusions_start])
            self._a2l_comp_id_symbol.setText(self._applied[exclusions_start + 1])
            self._restore_exclusions(self._applied[-1], self._applied[-2])
        return True

    def _on_apply(self) -> None:
        try:
            exclusions = comparison_exclusions({XML_COMPARISON_EXCLUSIONS_KEY: self._exclusion_values()})
            disabled = comparison_exclusions({XML_COMPARISON_EXCLUSIONS_KEY: self._disabled_exclusion_values()})
        except ValueError as error:
            self._dialogs.error("XML Comparison Exclusions", str(error))
            return
        self._restore_exclusions(exclusions, disabled)
        mode, enabled, record, attempts, retry, latest, show_link = self._current()[:7]
        values = {
            THEME_KEY: mode, LOGGING_ENABLED_KEY: enabled, RECORD_PAGES_KEY: record,
            WEBFLOW_MAX_ATTEMPTS_KEY: attempts,
            WEBFLOW_RETRY_ENABLED_KEY: retry,
            LATEST_COUNT_KEY: latest, SHOW_WEBFLOW_LINK_KEY: show_link,
            **self._creation.values(),
            NEW_VARIANT_DEFAULTS_KEY: self._new_variant_defaults.values(),
            XML_COMPARISON_EXCLUSIONS_MASTER_ONLY_KEY: self._exclusions_master_only.isChecked(),
            A2L_COMP_ID_SYMBOL_KEY: self._a2l_comp_id_symbol.text().strip(),
            XML_COMPARISON_DISABLED_EXCLUSIONS_KEY: list(disabled),
            XML_COMPARISON_EXCLUSIONS_KEY: list(exclusions),
        }
        changes = {}
        position = 0
        for key, value in values.items():
            if key == NEW_VARIANT_DEFAULTS_KEY:
                previous = self._applied[position : position + len(value)]
                position += len(value)
                if tuple(value.values()) != previous:
                    changes[key] = value
            else:
                previous = self._applied[position]
                position += 1
                current = tuple(value) if key in (
                    XML_COMPARISON_EXCLUSIONS_KEY, XML_COMPARISON_DISABLED_EXCLUSIONS_KEY,
                ) else value
                if current != previous:
                    changes[key] = value
        self._settings.update(**values)
        set_logging_enabled(enabled)
        apply_theme(QApplication.instance(), mode)
        self._applied = self._current()
        self._refresh_apply()
        self.settingsChanged.emit(changes)
