"""AutoHub entry point."""
import logging
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from autohub.config import APP_NAME, LOGO_PATH
from autohub.core.logger import log_location, logging_enabled, set_logging_enabled, setup_logging
from autohub.core.settings import JsonSettingsStore
from autohub.ui.startup_dialog import StartupDialog
from autohub.ui.theme import apply_theme, set_dark_titlebar

_logger = logging.getLogger(__name__)


def startup_steps(app: QApplication, settings: JsonSettingsStore, state: dict, report=None) -> list:
    """(message, action) pairs run behind the startup dialog; heavy imports happen here, after it shows.

    ``report`` shows sub-step text (e.g. Master Sheet progress) in the dialog.
    """
    report = report or (lambda _text: None)

    def apply_settings():
        saved = settings.load()
        set_logging_enabled(logging_enabled(saved))
        setup_logging(location=log_location(saved))

    def prepare_interface():
        from autohub.ui.button_cursor import install_button_cursor
        from autohub.ui.combo_popup import install_combo_popup_style

        install_button_cursor(app)
        install_combo_popup_style(app)

    def load_modules():
        from autohub.bootstrap import build_modules

        state["modules"] = build_modules(settings)

    def build_window():
        from autohub.ui.main_window import MainWindow

        state["window"] = MainWindow(state["modules"])
        set_dark_titlebar(state["window"], state["dark"])

    def load_variants():
        state["window"].preload(report)

    return [
        ("Applying settings and logging...", apply_settings),
        ("Preparing interface...", prepare_interface),
        ("Loading modules and configuration...", load_modules),
        ("Building main window...", build_window),
        ("Loading variants...", load_variants),
    ]


def run_startup(steps: list, dialog: StartupDialog) -> None:
    for message, action in steps:
        dialog.step(message)
        _logger.info("Startup: %s", message.rstrip("."))
        action()
        dialog.advance()


def main() -> int:
    app = QApplication(sys.argv)
    if LOGO_PATH.exists():
        app.setWindowIcon(QIcon(str(LOGO_PATH)))
    settings = JsonSettingsStore()
    state = {"dark": apply_theme(app, settings.load().get("theme"))}

    steps = startup_steps(app, settings, state, lambda text: dialog.step(text))
    dialog = StartupDialog(len(steps))
    dialog.start()
    try:
        run_startup(steps, dialog)
    except Exception as error:
        _logger.exception("Startup failed")
        dialog.close()
        QMessageBox.critical(None, APP_NAME, f"{APP_NAME} could not start:\n\n{error}")
        return 1
    window = state["window"]
    dialog.finish(window)
    QTimer.singleShot(0, window.run_startup_tasks)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
