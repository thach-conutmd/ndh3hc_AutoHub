import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QTabBar, QWidget

from autohub.modules.settings.ui import SettingsWidget
from autohub.ui.theme import DARK, LIGHT, apply_theme, is_dark, normalize_theme_mode
from tests.fakes import MemorySettings


@pytest.mark.parametrize("mode,colors", [("dark", DARK), ("light", LIGHT)])
def test_selectable_buttons_have_distinct_states_without_resizing(qapp, mode, colors):
    apply_theme(qapp, mode)
    window = QWidget()
    layout = QHBoxLayout(window)
    action = QPushButton("Mode")
    selectable = QPushButton("Mode")
    selectable.setCheckable(True)
    layout.addWidget(action)
    layout.addWidget(selectable)
    window.show()
    try:
        qapp.processEvents()
        QTest.mouseMove(window, QPoint(1, 1))
        qapp.processEvents()
        original_size = selectable.sizeHint()
        assert original_size == action.sizeHint()

        def background(button):
            return button.grab().toImage().pixelColor(8, 8).name()

        assert background(action) == colors.button_bg
        assert background(selectable) == colors.sidebar_bg
        QTest.mouseMove(selectable, QPoint(8, 8))
        qapp.processEvents()
        assert background(selectable) == colors.sidebar_hover
        selectable.click()
        assert selectable.isChecked()
        assert background(selectable) == colors.accent
        image = selectable.grab().toImage()
        assert image.pixelColor(selectable.width() // 2, selectable.height() - 1).name() == colors.link
        assert any(
            image.pixelColor(x, y).lightness() > 250
            for x in range(14, image.width() - 14) for y in range(8, image.height() - 8)
        )
        assert selectable.sizeHint() == original_size
        selectable.setEnabled(False)
        assert background(selectable) == colors.disabled_button
        selectable.setEnabled(True)
        selectable.click()
        assert not selectable.isChecked()
        assert background(selectable) == colors.sidebar_hover
    finally:
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        apply_theme(qapp, "dark")


@pytest.mark.parametrize("mode,colors", [("dark", DARK), ("light", LIGHT)])
def test_native_tabs_keep_geometry_and_show_active_hover_and_disabled_states(qapp, mode, colors):
    qapp.setStyleSheet("")
    tabs = QTabBar()
    tabs.setDocumentMode(True)
    tabs.setExpanding(False)
    for label in ("General", "Home", "Creation", "Diagnostics"):
        tabs.addTab(label)
    native_sizes = [tabs.tabRect(i).size() for i in range(tabs.count())]
    apply_theme(qapp, mode)
    tabs.show()
    try:
        qapp.processEvents()
        QTest.mouseMove(tabs, tabs.tabRect(0).center())
        qapp.processEvents()
        assert [tabs.tabRect(i).size() for i in range(tabs.count())] == native_sizes

        def background(index):
            rect = tabs.tabRect(index)
            return tabs.grab().toImage().pixelColor(rect.left() + 6, rect.top() + 6).name()

        assert background(0) == colors.accent
        assert background(1) == colors.sidebar_bg
        QTest.mouseMove(tabs, tabs.tabRect(1).center())
        qapp.processEvents()
        assert background(1) == colors.sidebar_hover
        QTest.mouseClick(tabs, Qt.LeftButton, pos=tabs.tabRect(1).center())
        assert tabs.currentIndex() == 1 and background(1) == colors.accent
        rect = tabs.tabRect(1)
        assert tabs.grab().toImage().pixelColor(rect.center().x(), rect.bottom()).name() == colors.link
        tabs.setTabEnabled(2, False)
        assert background(2) == colors.disabled_button
        assert [tabs.tabRect(i).size() for i in range(tabs.count())] == native_sizes
    finally:
        tabs.close()
        tabs.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        apply_theme(qapp, "dark")


def test_navigation_groups_share_styling_and_follow_live_theme_changes(qapp):
    from autohub.modules.comparison.ui import ComparisonWidget
    from autohub.ui.sidebar import Sidebar
    from tests.fakes import FakeDialogs

    comparison = ComparisonWidget(FakeDialogs())
    settings = SettingsWidget(MemorySettings())
    sidebar = Sidebar([(None, "Home"), (None, "Settings")], pinned_bottom=[1])
    buttons = [
        (comparison._master_mode_btn, comparison._manual_mode_btn),
        tuple(settings._creation._environment_buttons.buttons()),
    ]
    try:
        for mode, colors in (("dark", DARK), ("light", LIGHT), ("dark", DARK)):
            apply_theme(qapp, mode)
            for first, second in buttons:
                first.setChecked(True)
                for button, expected in ((first, colors.accent), (second, colors.sidebar_bg)):
                    button.ensurePolished()
                    assert button.grab().toImage().pixelColor(8, 8).name() == expected
                second.click()
                assert second.isChecked() and not first.isChecked()
                assert second.grab().toImage().pixelColor(8, 8).name() == colors.accent
            sidebar.show()
            qapp.processEvents()
            sidebar.select_module(0)
            rect = sidebar._list.visualItemRect(sidebar._list.item(0))
            image = sidebar._list.viewport().grab().toImage()
            assert image.pixelColor(rect.left() + 14, rect.top() + 8).name() == colors.accent
            assert rect.height() == 40
            sidebar.select_module(1)
            image = sidebar._list.viewport().grab().toImage()
            assert image.pixelColor(rect.left() + 14, rect.top() + 8).name() == colors.sidebar_bg
    finally:
        comparison.shutdown()
        for widget in (comparison, settings, sidebar):
            widget.close()
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        apply_theme(qapp, "dark")


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


def test_checklist_selects_latest_variant_event_and_preserves_user_filter():
    from datetime import datetime

    from autohub.modules.creation.variant_checklist import VariantChecklist

    QApplication.instance() or QApplication([])
    box = VariantChecklist()
    rows = [
        {"part_number": "2", "ecu_type": "x", "event": "62XS - HIN", "created_at": datetime(2025, 6, 1)},
        {"part_number": "1", "ecu_type": "x", "event": "6WZX - MP0", "created_at": datetime(2025, 1, 1)},
    ]
    box.set_variants(rows)
    assert box._event_filter.currentText() == "62XS - HIN"
    assert list(box._checkboxes) == ["2"]
    newer = {"part_number": "3", "ecu_type": "x", "event": "62XS - MP2", "created_at": datetime(2025, 7, 1)}
    box.set_variants([*rows, newer])
    assert box._event_filter.currentText() == "62XS - MP2"
    assert list(box._checkboxes) == ["3"]
    box._event_filter.setCurrentText("6WZX - MP0")
    box._on_event_chosen(0)
    box.set_variants(rows)
    assert box._event_filter.currentText() == "6WZX - MP0"
    assert list(box._checkboxes) == ["1"]
    box._event_filter.setCurrentText("All events")
    box._on_event_chosen(0)
    box.set_variants(rows)
    assert box._event_filter.currentText() == "All events"
    assert list(box._checkboxes) == ["2", "1"]


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


def test_settings_page_saves_and_discards_the_a2l_component_id_symbol(qapp):
    from tests.fakes import FakeDialogs

    settings = MemorySettings()
    page = SettingsWidget(settings, dialogs=FakeDialogs(table_answer=False))
    assert page._a2l_comp_id_symbol.text() == "I14229_numCompID_CA"
    page._a2l_comp_id_symbol.setText("CustomCompId")
    assert page._apply.isEnabled()
    page._apply.click()
    assert settings.load()["a2l_comp_id_symbol"] == "CustomCompId"

    page._a2l_comp_id_symbol.setText("Discarded")
    assert page.confirm_leave() is True
    assert page._a2l_comp_id_symbol.text() == "CustomCompId"

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
    assert set(groups) == {
        "Theme", "Logging", "Analysis", "Home", "Creation", "New variants", "WebFlow Retry", "Exclude Compare Data",
    }
    assert page._theme.parentWidget() is groups["Theme"]
    assert page._logging.parentWidget() is groups["Logging"]
    assert page._record.parentWidget() is groups["Analysis"]
    assert page._retry.parentWidget() is groups["WebFlow Retry"]
    assert page._attempts.parentWidget() is groups["WebFlow Retry"]
    assert page._latest.parentWidget() is groups["Home"]
    assert page._show_link.parentWidget() is groups["Home"]


def test_xml_exclusion_settings_add_edit_delete_restore_and_save(qapp):
    from tests.fakes import FakeDialogs

    settings = MemorySettings()
    dialogs = FakeDialogs()
    page = SettingsWidget(settings, dialogs)
    assert page._exclusion_values() == ("Files/", "Notes/")
    page._add_exclusion_btn.click()
    assert page._exclusions.rowCount() == 3 and page._apply.isEnabled()
    page._on_apply()
    assert dialogs.errors and "xml_comparison_exclusions" not in settings.load()
    page._exclusions.item(2, 0).setText(" Custom / ")
    page._on_apply()
    assert settings.load()["xml_comparison_exclusions"] == ["Files/", "Notes/", "Custom/"]
    assert not page._apply.isEnabled()
    restored = SettingsWidget(settings)
    assert restored._exclusion_values() == ("Files/", "Notes/", "Custom/")
    restored._exclusions.cellWidget(0, 2).click()
    restored._exclusions.cellWidget(0, 2).click()
    restored._exclusions.cellWidget(0, 2).click()
    restored._on_apply()
    assert settings.load()["xml_comparison_exclusions"] == []
    restored._restore_exclusions_btn.click()
    assert restored._exclusion_values() == ("Files/", "Notes/")
    restored._on_apply()
    assert settings.load()["xml_comparison_exclusions"] == ["Files/", "Notes/"]


def test_exclusion_checkboxes_persist_edit_delete_and_restore(qapp):
    from autohub.modules.comparison.xml_parser import comparison_exclusions

    settings = MemorySettings()
    page = SettingsWidget(settings)
    assert page._exclusions.item(0, 0).checkState() == Qt.Checked
    page._exclusions.item(0, 0).setCheckState(Qt.Unchecked)
    page._exclusions.item(0, 0).setText(" Custom / ")
    assert page._apply.isEnabled()
    page._apply.click()
    assert settings.load()["xml_comparison_exclusions"] == ["Custom/", "Notes/"]
    assert settings.load()["xml_comparison_disabled_exclusions"] == ["Custom/"]
    assert comparison_exclusions(settings.load()) == ("Notes/",)
    restored = SettingsWidget(settings)
    assert restored._exclusions.item(0, 0).checkState() == Qt.Unchecked
    assert not restored._apply.isEnabled()
    restored._exclusions.item(0, 0).setCheckState(Qt.Checked)
    restored._apply.click()
    assert comparison_exclusions(settings.load()) == ("Custom/", "Notes/")
    restored._exclusions.item(0, 0).setCheckState(Qt.Unchecked)
    restored._exclusions.cellWidget(0, 2).click()
    restored._apply.click()
    assert settings.load()["xml_comparison_disabled_exclusions"] == []
    restored._add_exclusion_btn.click()
    assert restored._exclusions.item(1, 0).checkState() == Qt.Checked
    restored._restore_exclusions_btn.click()
    assert restored._exclusion_values() == ("Files/", "Notes/")
    assert restored._disabled_exclusion_values() == ()


@pytest.mark.parametrize("answer", [True, False, None])
def test_exclusion_checkboxes_follow_apply_discard_cancel(qapp, answer):
    from tests.fakes import FakeDialogs

    settings = MemorySettings()
    page = SettingsWidget(settings, FakeDialogs(table_answer=answer))
    page._exclusions.item(0, 0).setCheckState(Qt.Unchecked)
    assert page.confirm_leave() is (answer is not None)
    assert settings.load().get("xml_comparison_disabled_exclusions") == (["Files/"] if answer else None)
    assert page._disabled_exclusion_values() == (() if answer is False else ("Files/",))


def test_exclusion_scope_is_saved_loaded_and_emitted(qapp):
    settings = MemorySettings()
    page = SettingsWidget(settings)
    changes = []
    page.settingsChanged.connect(changes.append)
    assert not page._exclusions_master_only.isChecked()
    page._exclusions_master_only.setChecked(True)
    assert page._apply.isEnabled()
    page._apply.click()
    assert settings.load()["xml_comparison_exclusions_master_only"] is True
    assert changes == [{"xml_comparison_exclusions_master_only": True}]
    restored = SettingsWidget(settings)
    assert restored._exclusions_master_only.isChecked()
    assert not restored._apply.isEnabled()
    restored._exclusions_master_only.setChecked(False)
    restored._apply.click()
    assert settings.load()["xml_comparison_exclusions_master_only"] is False


@pytest.mark.parametrize("answer", [True, False, None])
def test_xml_exclusion_settings_follow_apply_discard_cancel(qapp, answer):
    from tests.fakes import FakeDialogs

    settings = MemorySettings()
    page = SettingsWidget(settings, FakeDialogs(table_answer=answer))
    page._exclusions.item(0, 0).setText("Custom/")
    page._exclusions_master_only.setChecked(True)
    assert page.confirm_leave() is (answer is not None)
    assert settings.load().get("xml_comparison_exclusions") == (["Custom/", "Notes/"] if answer else None)
    assert page._exclusion_values()[0] == ("Files/" if answer is False else "Custom/")
    assert settings.load().get("xml_comparison_exclusions_master_only") is (True if answer else None)
    assert page._exclusions_master_only.isChecked() is (answer is not False)


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


def test_master_sheet_card_height_fits_its_content(qapp):
    from PySide6.QtWidgets import QGroupBox, QSizePolicy
    from autohub.modules.home.ui import HomeWidget
    from tests.fakes import build_service

    home = HomeWidget(build_service(), MemorySettings())
    group = next(group for group in home.findChildren(QGroupBox) if group.title() == "Master Sheet")
    margins = group.layout().contentsMargins()
    assert group.sizePolicy().verticalPolicy() == QSizePolicy.Maximum
    assert (margins.top(), margins.bottom()) == (14, 8)


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
        "General", "Home", "Creation", "Diagnostics", "Comparison",
    ]
    assert page._save_status.text() == "All changes saved"
    page._creation._routing.setText("New routing")
    page._tabs.setCurrentIndex(3)
    assert page._save_status.text() == "Unsaved changes"
    assert page._apply.isEnabled()
    page._apply.click()
    assert page._save_status.text() == "All changes saved"
    assert page._settings.load()["routing"] == "New routing"


def test_home_workspace_summary_tracks_rows_selection_and_clear(qapp):
    from autohub.modules.home.ui import HomeWidget
    from tests.fakes import build_service

    home = HomeWidget(build_service(), MemorySettings())
    assert home._row_summary.text() == "No variants loaded"
    home.show_rows([{"J": "P1"}, {"J": "P2"}])
    assert home._row_summary.text() == "2 variants"
    home._variant_table.selectRow(0)
    assert home._row_summary.text() == "2 variants | 1 selected"
    home.remove_rows([0])
    assert home._row_summary.text().startswith("1 variant")
    home.clear_rows()
    assert home._row_summary.text() == "No variants loaded"
