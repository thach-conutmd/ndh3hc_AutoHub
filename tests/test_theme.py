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


def test_retry_checkbox_saves_and_preserves_attempt_limit(qapp):
    from autohub.modules.creation.config_form import load_config

    settings = MemorySettings({"webflow_max_attempts": 7})
    page = SettingsWidget(settings)
    assert page._retry.isChecked() and page._attempts.isEnabled()
    page._retry.setChecked(False)
    assert not page._attempts.isEnabled()
    assert page._attempts.value() == 7 and page._apply.isEnabled()
    page._apply.click()
    assert load_config(settings).retry_enabled is False
    restored = SettingsWidget(settings)
    assert not restored._retry.isChecked() and not restored._attempts.isEnabled()
    restored._retry.setChecked(True)
    restored._apply.click()
    assert load_config(settings).retry_enabled is True
    assert restored._attempts.isEnabled() and restored._attempts.value() == 7


def test_retry_checkbox_changes_can_be_discarded(qapp):
    from tests.fakes import FakeDialogs

    page = SettingsWidget(MemorySettings(), FakeDialogs(table_answer=False))
    page._retry.setChecked(False)
    assert page.confirm_leave()
    assert page._retry.isChecked() and page._attempts.isEnabled()
    assert not page._apply.isEnabled()


def test_settings_controls_are_organized_in_groups(qapp):
    from PySide6.QtWidgets import QGroupBox

    page = SettingsWidget(MemorySettings())
    groups = {group.title(): group for group in page.findChildren(QGroupBox)}
    assert set(groups) == {"Theme", "Logging", "Analysis", "Home", "Creation", "WebFlow Retry"}
    assert page._theme.parentWidget() is groups["Theme"]
    assert page._logging.parentWidget() is groups["Logging"]
    assert page._record.parentWidget() is groups["Analysis"]
    assert page._retry.parentWidget() is groups["WebFlow Retry"]
    assert page._attempts.parentWidget() is groups["WebFlow Retry"]
    assert page._latest.parentWidget() is groups["Home"]
    assert page._show_link.parentWidget() is groups["Home"]


def test_home_settings_apply_to_existing_home_page(qapp):
    from unittest.mock import Mock
    from autohub.modules.home.ui import HomeWidget
    from autohub.ui.main_window import MainWindow
    from tests.fakes import build_service

    settings = MemorySettings({"latest_variant_count": 5})
    home = HomeWidget(build_service(), settings)
    page = SettingsWidget(settings)
    MainWindow._wire_cross_module_signals([home, page])
    home._presenter.refresh_latest_rows = Mock()
    assert not hasattr(home, "_settings_btn")
    page._latest.setCurrentIndex(page._latest.findData(20))
    page._show_link.setChecked(True)
    page._apply.click()
    assert settings.load()["latest_variant_count"] == 20
    assert settings.load()["show_webflow_link"] is True
    home._presenter.refresh_latest_rows.assert_called_once()
    assert not home._variant_table.isColumnHidden(2)


def test_home_settings_discard_restores_both_controls(qapp):
    from tests.fakes import FakeDialogs

    settings = MemorySettings({"latest_variant_count": 20, "show_webflow_link": True})
    page = SettingsWidget(settings, FakeDialogs(table_answer=False))
    page._latest.setCurrentIndex(page._latest.findData(5))
    page._show_link.setChecked(False)
    assert page.confirm_leave()
    assert page._latest.currentData() == 20 and page._show_link.isChecked()
    assert not page._apply.isEnabled()


def test_unrelated_settings_do_not_refresh_home(qapp):
    from unittest.mock import Mock

    page = SettingsWidget(MemorySettings())
    changed = Mock()
    page.settingsChanged.connect(changed)
    page._record.setChecked(False)
    page._apply.click()
    assert changed.call_args.args[0] == {"record_webflow_pages": False}


def test_creation_settings_are_saved_and_discarded_from_settings_page(qapp):
    from PySide6.QtCore import Qt
    from autohub.modules.creation.ui import CreationWidget
    from autohub.modules.settings.creation_form import load_config
    from autohub.modules.creation.service import WebFlowJobService
    from tests.fakes import FakeDialogs, FakeWebFlow

    settings = MemorySettings({"tool_version": "Old"})
    page = SettingsWidget(settings, FakeDialogs(table_answer=False))
    page._creation._tool_version.setText("New")
    page._creation._routing.setText("Route")
    page._creation._change_reason.item(0).setCheckState(Qt.Checked)
    assert page._apply.isEnabled()
    page._apply.click()
    config = load_config(settings)
    assert config.tool_version == "New" and config.routing == "Route"
    assert config.change_reason == page._creation._change_reason.item(0).text()
    page._creation._tool_version.setText("Discard")
    page._creation._change_reason.item(0).setCheckState(Qt.Unchecked)
    assert page.confirm_leave()
    assert page._creation._tool_version.text() == "New"
    assert page._creation._change_reason.item(0).checkState() == Qt.Checked
    assert not page._apply.isEnabled()
    creation = CreationWidget(WebFlowJobService(FakeWebFlow), settings)
    assert not hasattr(creation, "_settings_btn")


def test_settings_tabs_keep_pending_changes_and_shared_footer(qapp):
    page = SettingsWidget(MemorySettings())
    assert [page._tabs.tabText(index) for index in range(page._tabs.count())] == [
        "General", "Home", "Creation", "Diagnostics",
    ]
    assert page._save_status.text() == "All changes saved"
    page._creation._routing.setText("New routing")
    page._tabs.setCurrentIndex(3)
    assert page._save_status.text() == "Unsaved changes"
    assert page._apply.isEnabled()
    page._apply.click()
    assert page._save_status.text() == "All changes saved"
    assert page._settings.load()["routing"] == "New routing"
