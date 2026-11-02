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
    assert table.horizontalHeaderItem(column).text().endswith("▼")
    assert len(table.read()) == 3  # hidden rows are still part of the data written back


def test_table_filter_resets_when_repopulated(table):
    table.set_column_filter(_column(table, "H"), ColumnFilter(text="zzz"))
    table.populate([{"J": "P9", "H": "DAN"}])
    assert not table.isRowHidden(0)
    assert not table.horizontalHeaderItem(_column(table, "H")).text().endswith("▼")
