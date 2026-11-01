"""Settings page for theme, logging, WebFlow tracing and retry attempts."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from autohub.core.dialogs import Dialogs, QtDialogs
from autohub.core.logger import LOGGING_ENABLED_KEY, logging_enabled, set_logging_enabled
from autohub.core.settings import SettingsStore
from autohub.core.settings_keys import (
    DEFAULT_WEBFLOW_MAX_ATTEMPTS, RECORD_PAGES_KEY, WEBFLOW_ATTEMPTS_LIMIT, WEBFLOW_MAX_ATTEMPTS_KEY,
)
from autohub.ui.theme import DEFAULT_THEME_MODE, apply_theme, normalize_theme_mode

THEME_KEY = "theme"
_LABELS = {"system": "System", "light": "Light", "dark": "Dark"}


class SettingsWidget(QWidget):
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

        self._logging = QCheckBox("Enable logging (logs/autohub.log and console)")
        self._logging.setChecked(logging_enabled(settings.load()))

        self._record = QCheckBox("Record every WebFlow step (HTML, screenshot, elements) in logs/webflow_trace")
        self._record.setChecked(bool(settings.load().get(RECORD_PAGES_KEY, True)))

        self._attempts = QSpinBox()
        self._attempts.setRange(1, WEBFLOW_ATTEMPTS_LIMIT)
        self._attempts.setValue(settings.load().get(WEBFLOW_MAX_ATTEMPTS_KEY, DEFAULT_WEBFLOW_MAX_ATTEMPTS))
        self._attempts.setToolTip(
            "Includes the first attempt. Set to 1 to disable automatic retries. "
            "Retries resume saved progress, with a 5-second delay. After a crash, "
            "AutoHub asks before resuming with the batch's saved settings."
        )

        form = QFormLayout()
        form.addRow("Theme:", self._theme)
        form.addRow("Logging:", self._logging)
        form.addRow("Analysis:", self._record)
        form.addRow("Maximum WebFlow attempts:", self._attempts)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addLayout(form)
        self._apply = QPushButton("Apply")
        self._apply.setToolTip("Save and apply the settings above.")
        self._apply.clicked.connect(self._on_apply)
        self._applied = self._current()
        self._theme.currentIndexChanged.connect(self._refresh_apply)
        self._logging.toggled.connect(self._refresh_apply)
        self._record.toggled.connect(self._refresh_apply)
        self._attempts.valueChanged.connect(self._refresh_apply)
        self._refresh_apply()
        layout.addWidget(self._apply, alignment=Qt.AlignRight)

    def _current(self) -> tuple[str, bool, bool, int]:
        return self._theme.currentData(), self._logging.isChecked(), self._record.isChecked(), self._attempts.value()

    def _refresh_apply(self, *_args) -> None:
        """Apply is only available while the page differs from what is applied."""
        self._apply.setEnabled(self._current() != self._applied)

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
        else:
            self._theme.setCurrentIndex(self._theme.findData(self._applied[0]))
            self._logging.setChecked(self._applied[1])
            self._record.setChecked(self._applied[2])
            self._attempts.setValue(self._applied[3])
        return True

    def _on_apply(self) -> None:
        mode, enabled, record, attempts = self._current()
        self._settings.update(**{
            THEME_KEY: mode, LOGGING_ENABLED_KEY: enabled, RECORD_PAGES_KEY: record,
            WEBFLOW_MAX_ATTEMPTS_KEY: attempts,
        })
        set_logging_enabled(enabled)
        apply_theme(QApplication.instance(), mode)
        self._applied = (mode, enabled, record, attempts)
        self._refresh_apply()
