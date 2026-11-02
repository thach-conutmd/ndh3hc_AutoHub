import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox

from autohub.core.variant_choices import VARIANT_CHOICES
from autohub.core.webflow_fields import GENERAL_OPTION_COLUMNS
from autohub.core.variant_schema import VARIANT_FIELD_ORDER
from autohub.modules.home.choice_delegate import ChoiceDelegate, MultiChoiceDelegate
from autohub.modules.home.variant_table import VariantTable


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_choice_columns_exist_in_the_table_schema():
    assert set(VARIANT_CHOICES) <= set(VARIANT_FIELD_ORDER)


def test_delegate_offers_the_list_and_keeps_unknown_values(app):
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    table = QTableWidget(1, 1)
    table.setItem(0, 0, QTableWidgetItem("Legacy"))
    delegate = ChoiceDelegate(("Yes", "No"), table)
    index = table.model().index(0, 0)
    editor = delegate.createEditor(table, None, index)
    assert isinstance(editor, QComboBox)
    delegate.setEditorData(editor, index)
    assert [editor.itemText(i) for i in range(editor.count())] == ["", "Yes", "No", "Legacy"]
    editor.setCurrentText("No")
    delegate.setModelData(editor, table.model(), index)
    assert table.item(0, 0).text() == "No"


def test_general_columns_use_cached_multi_select_options_and_preserve_unknown_values(app):
    table = VariantTable()
    options = {key: [f"{key} option"] for key in GENERAL_OPTION_COLUMNS.values()}

    table.set_webflow_option_choices(options)

    model_year_col = VARIANT_FIELD_ORDER.index("AF") + 1
    for column in GENERAL_OPTION_COLUMNS:
        index = VARIANT_FIELD_ORDER.index(column) + 1
        assert isinstance(table.itemDelegateForColumn(index), MultiChoiceDelegate)

    table.populate([{"AF": "2027|Legacy Year"}])
    index = table.model().index(0, model_year_col)
    delegate = table.itemDelegateForColumn(model_year_col)
    editor = delegate.createEditor(table, None, index)
    delegate.setEditorData(editor, index)
    assert editor.selected_values() == ["2027", "Legacy Year"]
    editor.set_selected_values(["2028", "Legacy Year"])
    delegate.setModelData(editor, table.model(), index)
    assert table.item(0, model_year_col).text() == "2028|Legacy Year"
    assert editor.selected_values() == ["2028", "Legacy Year"]


def test_multichoice_combo_toggles_multiple_items(app):
    table = VariantTable()
    delegate = MultiChoiceDelegate(("2027", "2028"), table)
    index = table.model().index(0, 0)
    editor = delegate.createEditor(table, None, index)
    editor.show()
    editor.showPopup()
    app.processEvents()

    for row in (0, 1):
        option_index = editor.model().index(row, 0)
        position = editor.view().visualRect(option_index).center()
        QTest.mouseClick(editor.view().viewport(), Qt.LeftButton, pos=position)
        app.processEvents()

    assert editor.selected_values() == ["2027", "2028"]
