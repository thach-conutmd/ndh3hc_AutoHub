"""Per-column filters of the Home variant table."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from autohub.modules.home.row_filter import ColumnFilter, RowFilter
from autohub.modules.home.filter_dialog import ColumnFilterDialog


@pytest.fixture(autouse=True)
def cleanup_filter_widgets(qapp):
    previous = set(qapp.topLevelWidgets())
    yield
    for widget in set(qapp.topLevelWidgets()) - previous:
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_text_filter_is_case_insensitive_contains():
    assert ColumnFilter(text="mp1").matches("DAN/MP1")
    assert not ColumnFilter(text="mp2").matches("DAN/MP1")


def test_allowed_values_filter_is_exact():
    assert ColumnFilter(allowed=frozenset({"A"})).matches("A")
    assert not ColumnFilter(allowed=frozenset({"A"})).matches("AB")


def test_row_filter_combines_columns_with_and():
    rows = RowFilter()
    rows.set(0, ColumnFilter(text="a"))
    rows.set(1, ColumnFilter(allowed=frozenset({"x"})))
    assert rows.matches(["abc", "x"]) and not rows.matches(["abc", "y"]) and not rows.matches(["zzz", "x"])
    rows.set(0, ColumnFilter())  # an empty filter removes the column's condition
    assert rows.matches(["zzz", "x"]) and not rows.is_active(0)


def test_dialog_returns_no_value_condition_when_all_checked(qapp):
    dialog = ColumnFilterDialog("J", ["A", "B"], ColumnFilter())
    assert dialog.result_filter() == ColumnFilter()


def test_dialog_reflects_current_filter(qapp):
    dialog = ColumnFilterDialog("J", ["A", "B", ""], ColumnFilter(text="", allowed=frozenset({"B"})))
    assert dialog.result_filter().allowed == frozenset({"B"})


@pytest.fixture
def table(qapp):
    from autohub.modules.home.variant_table import VariantTable

    widget = VariantTable()
    widget.populate([{"J": "P1", "H": "DAN"}, {"J": "P2", "H": "SOP"}, {"J": "P3", "H": "DAN"}])
    return widget


def _column(table, field):
    from autohub.core.variant_schema import VARIANT_FIELD_ORDER

    return 1 + VARIANT_FIELD_ORDER.index(field)


def test_table_hides_rows_and_marks_the_header(table):
    column = _column(table, "H")
    table.set_column_filter(column, ColumnFilter(allowed=frozenset({"DAN"})))
    assert [table.isRowHidden(r) for r in range(3)] == [False, True, False]
    assert table.horizontalHeaderItem(column).toolTip() == "Filter active - click to modify"
    assert not table.horizontalHeaderItem(column).icon().isNull()
    assert len(table.read()) == 3  # hidden rows are still part of the data written back


def test_table_filter_resets_when_repopulated(table):
    table.set_column_filter(_column(table, "H"), ColumnFilter(text="zzz"))
    table.populate([{"J": "P9", "H": "DAN"}])
    assert not table.isRowHidden(0)
    item = table.horizontalHeaderItem(_column(table, "H"))
    assert item.toolTip() == f"Filter {item.text()}"


def test_native_filter_icons_preserve_titles_and_reset_immediately(table):
    from PySide6.QtCore import Qt
    column = _column(table, "J")
    item = table.horizontalHeaderItem(column)
    title = item.text()
    inactive = item.icon().pixmap(14, 14).toImage()
    assert not item.icon().isNull()
    assert item.toolTip() == f"Filter {title}"
    assert table.horizontalHeaderItem(0).icon().isNull()
    table.set_column_filter(column, ColumnFilter(text="P1"))
    assert item.text() == title
    assert inactive != item.icon().pixmap(14, 14).toImage()
    overlay = table._frozen.view
    assert overlay.model().headerData(column, Qt.Horizontal, Qt.ToolTipRole) == "Filter active - click to modify"
    assert not overlay.model().headerData(column, Qt.Horizontal, Qt.DecorationRole).isNull()
    table.set_column_filter(column, ColumnFilter())
    assert item.icon().pixmap(14, 14).toImage() == inactive
    assert item.toolTip() == f"Filter {title}"
    assert not any(table.isRowHidden(row) for row in range(table.rowCount()))


@pytest.mark.parametrize("frozen", [False, True])
def test_click_header_or_icon_opens_existing_dialog(table, monkeypatch, frozen):
    from unittest.mock import Mock
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from autohub.modules.home import table_filter

    column = _column(table, "J")
    dialog = Mock()
    dialog.exec.return_value = True
    dialog.result_filter.return_value = ColumnFilter(text="P2")
    constructor = Mock(return_value=dialog)
    monkeypatch.setattr(table_filter, "ColumnFilterDialog", constructor)
    table.resize(1000, 400)
    table.show()
    header = table._frozen.view.horizontalHeader() if frozen else table.horizontalHeader()
    for offset in (10, header.sectionSize(column) // 2):
        pos = QPoint(header.sectionViewportPosition(column) + offset, header.height() // 2)
        QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier, pos)
        assert constructor.call_args.args[0] == "Part Number"
        assert constructor.call_args.args[1] == ["P1", "P2", "P3"]
        assert [table.isRowHidden(row) for row in range(3)] == [True, False, True]
    assert constructor.call_count == 2
    table.setColumnWidth(column, 180)
    assert table._frozen.view.columnWidth(column) == 180
    assert header.model().headerData(column, Qt.Horizontal, Qt.DecorationRole) is not None


def test_icons_follow_theme_palette_without_changing_filters_or_data(table):
    from PySide6.QtGui import QColor, QPalette

    column = _column(table, "H")
    table.set_column_filter(column, ColumnFilter(text="DAN"))
    item = table.horizontalHeaderItem(column)
    original = table.read()
    before = item.icon().pixmap(14, 14).toImage()
    palette = table.palette()
    palette.setColor(QPalette.Highlight, QColor("#1234ab"))
    table.setPalette(palette)
    assert before != item.icon().pixmap(14, 14).toImage()
    assert table.read() == original
    assert [table.isRowHidden(row) for row in range(3)] == [False, True, False]
    assert item.toolTip() == "Filter active - click to modify"


def test_non_filterable_header_does_not_open_dialog(table, monkeypatch):
    from unittest.mock import Mock
    from autohub.modules.home import table_filter

    constructor = Mock()
    monkeypatch.setattr(table_filter, "ColumnFilterDialog", constructor)
    table.horizontalHeader().sectionClicked.emit(0)
    table._frozen.view.horizontalHeader().sectionClicked.emit(0)
    assert not constructor.called
