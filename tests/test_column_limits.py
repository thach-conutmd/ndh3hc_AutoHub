from autohub.modules.home.column_limits import MAX_COLUMN_WIDTH, MIN_COLUMN_WIDTH, clamp_width
from autohub.modules.home.variant_table import VariantTable


def test_clamp_width():
    assert clamp_width(10) == MIN_COLUMN_WIDTH
    assert clamp_width(10_000) == MAX_COLUMN_WIDTH
    assert clamp_width(100) == 100


def test_columns_stay_within_limits(qtbot=None):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    table = VariantTable()
    table.populate([{"J": "x" * 500}])
    for column in range(table.columnCount()):
        if table.isColumnHidden(column):
            continue
        assert MIN_COLUMN_WIDTH <= table.columnWidth(column) <= MAX_COLUMN_WIDTH
    table.setColumnWidth(3, 5)
    assert table.columnWidth(3) == MIN_COLUMN_WIDTH
    table.setColumnWidth(3, 5000)
    assert table.columnWidth(3) == MAX_COLUMN_WIDTH


def test_settings_page_returns_the_chosen_latest_count():
    from PySide6.QtWidgets import QApplication
    from autohub.modules.settings.ui import SettingsWidget
    from tests.fakes import MemorySettings
    QApplication.instance() or QApplication([])
    assert SettingsWidget(MemorySettings({"latest_variant_count": 20}))._latest.currentData() == 20
    assert SettingsWidget(MemorySettings({"latest_variant_count": 7}))._latest.currentData() == 0


def test_webflow_link_column_is_hidden_until_enabled_and_read_only():
    from PySide6.QtCore import Qt

    from autohub.modules.home.variant_table import VariantTable

    table = VariantTable()
    table.populate([{"_row": 1, "J": "P1", "_webflow_link": "https://h:8881/app/ShowJob/16406"}])
    column = table.columnCount() - 1
    assert table.isColumnHidden(column)
    table.set_webflow_link_visible(True)
    item = table.item(0, column)
    assert not table.isColumnHidden(column) and item.text() == "WF16406"
    assert not item.flags() & Qt.ItemIsEditable
    assert "_webflow_link" not in table.read()[0]


def test_webflow_link_column_is_frozen_right_after_the_part_number():
    from PySide6.QtWidgets import QApplication

    from autohub.modules.home.variant_table import VariantTable

    QApplication.instance() or QApplication([])
    table = VariantTable()
    table.populate([{"_row": 1, "J": "P1", "_webflow_link": "https://h/app/ShowJob/1"}])
    link = table.columnCount() - 1
    frozen = table._frozen
    before = frozen.width
    table.set_webflow_link_visible(True)
    assert table.horizontalHeader().visualIndex(link) == 2
    assert frozen.is_frozen(link) and not frozen.view.isColumnHidden(link)
    assert frozen.width == before + table.columnWidth(link) and table.columnWidth(link) >= 60
    table.set_webflow_link_visible(False)
    assert frozen.view.isColumnHidden(link) and frozen.width == before


def test_hidden_webflow_link_column_leaves_no_gap():
    from PySide6.QtWidgets import QApplication

    from autohub.modules.home.variant_table import VariantTable

    QApplication.instance() or QApplication([])
    table = VariantTable()
    table.populate([{"_row": 1, "J": "P1"}])
    link = table.columnCount() - 1
    header = table.horizontalHeader()
    assert header.visualIndex(link) == link
    table.set_webflow_link_visible(True)
    assert header.visualIndex(link) == 2
    table.set_webflow_link_visible(False)
    assert header.visualIndex(link) == link and table.columnWidth(link) == 0


def test_hand_cursor_over_a_webflow_link_cell_only():
    from PySide6.QtWidgets import QApplication

    from autohub.modules.home.variant_table import VariantTable

    QApplication.instance() or QApplication([])
    table = VariantTable()
    table.populate([{"_row": 1, "J": "P1", "_webflow_link": "https://h/app/ShowJob/1"}, {"_row": 2, "J": "P2"}])
    link = table.columnCount() - 1
    assert table._is_link_cell(table.model().index(0, link))
    assert not table._is_link_cell(table.model().index(1, link))
    assert not table._is_link_cell(table.model().index(0, 1))
