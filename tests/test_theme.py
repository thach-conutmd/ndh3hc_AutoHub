from PySide6.QtWidgets import QApplication, QWidget

from autohub.modules.settings.ui import SettingsWidget
from autohub.ui.theme import DARK, LIGHT, apply_theme, is_dark, normalize_theme_mode
from tests.fakes import MemorySettings


def test_mode_resolution():
    assert normalize_theme_mode("nonsense") == "dark" and normalize_theme_mode("light") == "light"
    assert is_dark("dark", False) and not is_dark("light", True)
    assert is_dark("system", True) and not is_dark("system", False)


def test_apply_theme_switches_palette():
    app = QApplication.instance() or QApplication([])
    assert apply_theme(app, "light") is False
    assert app.palette().window().color().name() == LIGHT.window
    assert apply_theme(app, "dark") is True
    assert app.palette().window().color().name() == DARK.window
    assert apply_theme(app, "system") in (True, False)


def test_settings_page_saves_and_applies_the_theme():
    app = QApplication.instance() or QApplication([])
    settings = MemorySettings()
    page = SettingsWidget(settings)
    assert not page._apply.isEnabled()  # nothing changed yet
    page._theme.setCurrentIndex(page._theme.findData("light"))
    assert page._apply.isEnabled()
    assert "theme" not in settings.load()  # nothing happens until Apply
    page._apply.click()
    assert settings.load()["theme"] == "light"
    assert not page._apply.isEnabled()  # applied, so grey again
    page._theme.setCurrentIndex(page._theme.findData("dark"))
    page._theme.setCurrentIndex(page._theme.findData("light"))
    assert not page._apply.isEnabled()  # back to the applied value
    assert app.palette().window().color().name() == LIGHT.window
    apply_theme(app, "dark")


def test_pinned_module_sits_in_the_bottom_list_and_selection_is_exclusive():
    from autohub.ui.sidebar import Sidebar

    QApplication.instance() or QApplication([])
    sidebar = Sidebar([(None, "Home"), (None, "Creation"), (None, "Settings")], pinned_bottom=[2])
    assert sidebar.width() == 170
    sidebar.toggle_collapsed()
    assert sidebar.width() == 56
    sidebar.toggle_collapsed()
    assert sidebar.width() == 170
    chosen = []
    sidebar.moduleSelected.connect(chosen.append)
    assert sidebar._list.count() == 2 and sidebar._bottom_list.count() == 1
    sidebar._bottom_list.setCurrentRow(0)
    assert chosen == [2] and sidebar._list.currentRow() == -1
    sidebar._list.setCurrentRow(1)
    assert chosen == [2, 1] and sidebar._bottom_list.currentRow() == -1


def test_settings_page_turns_logging_off_and_on_with_apply():
    import logging

    from autohub.core.logger import logging_enabled

    QApplication.instance() or QApplication([])
    settings = MemorySettings()
    page = SettingsWidget(settings)
    assert page._logging.isChecked() and logging_enabled(settings.load())
    try:
        page._logging.setChecked(False)
        assert not logging.root.manager.disable  # not yet
        page._apply.click()
        assert settings.load()["logging_enabled"] is False
        assert logging.root.manager.disable == logging.CRITICAL
        page._logging.setChecked(True)
        page._apply.click()
        assert logging.root.manager.disable == logging.NOTSET
    finally:
        logging.disable(logging.NOTSET)


def test_checklist_selects_the_latest_event_until_the_user_chooses():
    from datetime import datetime

    from autohub.modules.creation.variant_checklist import VariantChecklist

    QApplication.instance() or QApplication([])
    box = VariantChecklist()
    rows = [
        {"part_number": "1", "ecu_type": "x", "event": "OLD", "created_at": datetime(2025, 1, 1)},
        {"part_number": "2", "ecu_type": "x", "event": "NEW", "created_at": datetime(2025, 6, 1)},
    ]
    box.set_variants(rows)
    assert box._event_filter.currentText() == "NEW" and list(box._checkboxes) == ["2"]
    box._event_filter.setCurrentText("OLD")
    box._on_event_chosen(0)
    box.set_variants(rows)
    assert box._event_filter.currentText() == "OLD"


def _changed_page(answer):
    from tests.fakes import FakeDialogs

    QApplication.instance() or QApplication([])
    settings = MemorySettings()
    page = SettingsWidget(settings, dialogs=FakeDialogs(table_answer=answer))
    page._theme.setCurrentIndex(page._theme.findData("light"))
    return page, settings


def test_leaving_without_changes_does_not_ask():
    from tests.fakes import FakeDialogs

    QApplication.instance() or QApplication([])
    dialogs = FakeDialogs(table_answer=None)
    assert SettingsWidget(MemorySettings(), dialogs=dialogs).confirm_leave() is True
    assert dialogs.asked == []


def test_leaving_with_changes_apply_discard_or_cancel():
    page, settings = _changed_page(True)
    assert page.confirm_leave() is True and settings.load()["theme"] == "light"
    apply_theme(QApplication.instance(), "dark")

    page, settings = _changed_page(False)
    assert page.confirm_leave() is True and "theme" not in settings.load()
    assert page._theme.currentData() == "dark" and not page._apply.isEnabled()

    page, settings = _changed_page(None)
    assert page.confirm_leave() is False and "theme" not in settings.load()
    assert page._theme.currentData() == "light"


def test_main_window_stays_on_the_page_when_leaving_is_cancelled():
    from autohub.ui.main_window import MainWindow

    QApplication.instance() or QApplication([])

    class Guard(QWidget):
        allow = False

        def confirm_leave(self):
            return self.allow

    class Mod:
        icon_file = None
        pinned_bottom = False

        def __init__(self, name, widget):
            self.display_name, self._widget = name, widget

        def create_widget(self):
            return self._widget

    guard = Guard()
    window = MainWindow([Mod("A", guard), Mod("B", QWidget())])
    window._sidebar._list.setCurrentRow(1)
    assert window._pages.currentIndex() == 0 and window._sidebar._list.currentRow() == 0
    guard.allow = True
    window._sidebar._list.setCurrentRow(1)
    assert window._pages.currentIndex() == 1


def test_settings_page_saves_the_page_recording_option():
    QApplication.instance() or QApplication([])
    settings = MemorySettings()
    page = SettingsWidget(settings)
    assert page._record.isChecked()  # on by default
    page._record.setChecked(False)
    assert page._apply.isEnabled()
    page._apply.click()
    assert settings.load()["record_webflow_pages"] is False


def test_settings_attempt_count_is_saved_and_loaded(qapp):
    from autohub.modules.creation.config_form import load_config

    settings = MemorySettings()
    page = SettingsWidget(settings)
    assert page._attempts.value() == 5
    assert page._attempts.minimum() == 1 and page._attempts.maximum() == 100
    page._attempts.setValue(1)
    assert page._apply.isEnabled()
    assert "webflow_max_attempts" not in settings.load()
    page._apply.click()
    assert not page._apply.isEnabled()
    assert load_config(settings).max_attempts == 1
    assert SettingsWidget(settings)._attempts.value() == 1


def test_attempt_changes_support_apply_discard_and_cancel(qapp):
    from tests.fakes import FakeDialogs

    for answer in (True, False, None):
        settings = MemorySettings({"webflow_max_attempts": 3})
        page = SettingsWidget(settings, FakeDialogs(table_answer=answer))
        page._attempts.setValue(7)
        assert page.confirm_leave() is (answer is not None)
        assert settings.load()["webflow_max_attempts"] == (7 if answer else 3)
        assert page._attempts.value() == (3 if answer is False else 7)
