"""Local XML comparison reuses the retained Comparison workspace without Master/browser access."""
from threading import Event
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from autohub.modules.comparison import service, ui
from autohub.modules.comparison.comparison import Status
from autohub.modules.home.row_filter import ColumnFilter
from tests.fakes import FakeDialogs, MemorySettings
from tests.test_comparison import export_xml, variant
from tests.test_comparison_ui import build_page, cleanup_comparison_widgets, wait_done, visible_rows


@pytest.fixture
def xml_files(tmp_path):
    base, target = tmp_path / "base.xml", tmp_path / "target.XML"
    base.write_bytes(export_xml({
        "General/Power": "93", "Extra/BaseOnly": "base", "General/Same": "0010",
    }, job_id=None))
    target.write_bytes(export_xml({
        "General/Power": "94", "Extra/TargetOnly": "target", "General/Same": "0010",
    }, job_id=None))
    return base, target


def manual_page(xml_files):
    dialogs = FakeDialogs(files=[str(path) for path in xml_files])
    browser = Mock()
    updater = Mock()
    page = ui.ComparisonWidget(
        dialogs, service.ComparisonService(browser), MemorySettings({"change_engineer": "Reviewer"}), updater,
    )
    page._manual_mode_btn.click()
    for source in ("Base", "Target"):
        page._xml_buttons[source].click()
    return page, dialogs, browser, updater


def test_manual_mode_needs_no_master_or_browser_and_reuses_result_table(qapp, xml_files):
    page, dialogs, browser, updater = manual_page(xml_files)
    original = [path.read_bytes() for path in xml_files]
    assert page._variants == [] and page._compare_btn.isEnabled()
    assert page._variants_table.isHidden() and page._impl_btn.isHidden()
    assert page._select_all_btn.isHidden() and page._clear_selection_btn.isHidden()
    assert page._xml_labels["Base"].text() == xml_files[0].name
    assert page._xml_labels["Base"].toolTip() == str(xml_files[0])
    page._compare_btn.click()
    assert page._progress_dialog is not None
    assert not page._manual_mode_btn.isEnabled() and not page._master_mode_btn.isEnabled()
    wait_done(page, qapp)
    assert dialogs.errors == []
    browser.assert_not_called()
    page._update_impl()
    updater.update.assert_not_called()
    assert [path.read_bytes() for path in xml_files] == original
    assert page._table.columnCount() == 5
    assert [page._table.horizontalHeaderItem(i).text() for i in range(5)] == list(ui._MANUAL_HEADERS)
    assert page._table.rowCount() == 4 and page._export_btn.isEnabled()
    assert "Base: base.xml" in page._file_info.text() and "Target: target.XML" in page._file_info.text()
    assert str(xml_files[0]) in page._file_info.toolTip()
    assert "Total: 4 | Match: 1 | Deviation: 3" in page._summary.text()
    assert page._layout.indexOf(page._file_info) < page._layout.indexOf(page._summary)
    assert page._layout.indexOf(page._summary) < page._layout.indexOf(page._table)
    assert page._progress_dialog._summary.text() == "Completed: 1\nFailed: 0\nTotal: 1"
    for column in range(5):
        assert not page._table.horizontalHeaderItem(column).icon().isNull()
        assert page._table.frozen.view.isColumnHidden(column) == (column != 0)


def test_manual_reviews_survive_sort_filter_resize_new_files_and_master_reload(qapp, xml_files):
    page, dialogs, _, _ = manual_page(xml_files)
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    rows = page._rows
    index = next(i for i, (_, _, row) in enumerate(rows) if row.parameter == "General/Power")
    page._table.sortItems(0, Qt.DescendingOrder)
    item = page._result_item(index, 4)
    page._table.setCurrentItem(item)
    QApplication.clipboard().setText("reviewed")
    page._paste_result()
    page._set_status(index, Status.MATCH)
    assert page._comment(index) == "reviewed" and page._effective_status(index) == Status.MATCH
    assert page._result_item(index, 3).font().italic()
    assert page._result_item(index, 3).background().color().name() == "#e3f6e8"
    assert "Total: 4 | Match: 2 | Deviation: 2" in page._summary.text()
    page._header_filter.set_column_filter(3, ColumnFilter(allowed=frozenset({"MATCH"})))
    assert len(visible_rows(page)) == 2
    assert page._table.horizontalHeaderItem(3).toolTip() == "Filter active - click to modify"
    page._table.sortItems(3, Qt.AscendingOrder)
    assert len(visible_rows(page)) == 2
    assert all(page._table.item(row, 3).text() == "MATCH" for row in visible_rows(page))
    page._search.setText("reviewed")
    assert len(visible_rows(page)) == 1
    page.resize(1400, 800)
    page._table.setColumnWidth(1, 200)
    qapp.processEvents()
    dialogs.files = [str(xml_files[1])]
    page._xml_buttons["Base"].click()
    assert page._rows is rows and page._compared_files == tuple(map(str, xml_files))
    page.set_variants([variant()])
    page.set_webflow_links({"P1": "https://webflow/app/ShowJob/99"})
    assert page._rows is rows and page._comment(index) == "reviewed"
    table = page._table
    page._master_mode_btn.click()
    assert not page._rows and page._table.columnCount() == 7
    page._manual_mode_btn.click()
    assert page._table is table and page._rows is rows
    assert page._comment(index) == "reviewed" and page._effective_status(index) == Status.MATCH
    assert page._allowed_statuses(index) == (
        Status.MATCH, Status.VALUE_MISMATCH, Status.MISSING_IN_BASE, Status.MISSING_IN_TARGET,
    )


@pytest.mark.parametrize("problem", ["malformed", "missing", "wrong_type", "oversized"])
def test_failed_new_comparison_preserves_previous_result(qapp, xml_files, tmp_path, problem, monkeypatch):
    page, dialogs, _, _ = manual_page(xml_files)
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    rows, files = page._rows, page._compared_files
    bad = tmp_path / ("bad.txt" if problem == "wrong_type" else "bad.xml")
    if problem != "missing":
        bad.write_bytes(b"<broken" if problem == "malformed" else xml_files[0].read_bytes())
    if problem == "oversized":
        monkeypatch.setattr(service, "MAX_XML_BYTES", 10)
    dialogs.files = [str(bad)]
    page._xml_buttons["Target"].click()
    page._compare()
    wait_done(page, qapp)
    assert len(dialogs.errors) == 1 and "XML" in dialogs.errors[0][1]
    assert page._rows is rows and page._compared_files == files
    assert page._export_btn.isEnabled()


def test_manual_export_uses_completed_sources_and_all_retained_reviews(qapp, xml_files, tmp_path):
    page, dialogs, browser, _ = manual_page(xml_files)
    page._compare()
    wait_done(page, qapp)
    page._set_comment(0, "review <ok>")
    page._set_status(0, Status.MATCH)
    page._search.setText("nothing-visible")
    dialogs.files = [str(xml_files[1])]
    page._xml_buttons["Base"].click()
    dialogs.save_path = str(tmp_path / "report.html")
    page._export()
    html = (tmp_path / "report.html").read_text()
    assert html.count("<tr class=") == 4
    assert "review &lt;ok&gt;" in html and 'class="status manual"' in html
    assert 'id="base-xml" value="base.xml"' in html
    assert 'id="target-xml" value="target.XML"' in html
    assert 'id="reviewed-by" value="Reviewer"' in html
    assert str(tmp_path) not in html and "<th>Master</th>" not in html
    browser.assert_not_called()
    source = xml_files[0].read_bytes()
    dialogs.save_path = str(xml_files[0])
    page._export()
    assert dialogs.errors and xml_files[0].read_bytes() == source


def test_successful_new_comparison_replaces_old_result_only_on_completion(qapp, xml_files):
    page, _, _, _ = manual_page(xml_files)
    page._compare()
    wait_done(page, qapp)
    page._set_comment(0, "old review")
    page._progress_dialog.close()
    old_rows = page._rows
    page._xml_paths["Target"] = str(xml_files[0])
    page._compare()
    assert page._rows is old_rows
    wait_done(page, qapp)
    assert page._rows is not old_rows and not page._reviews
    assert all(row.status == Status.MATCH for _, _, row in page._rows)
    assert page._compared_files == (str(xml_files[0]), str(xml_files[0]))


def test_manual_cancellation_retains_previous_result(qapp, xml_files, monkeypatch):
    page, dialogs, _, _ = manual_page(xml_files)
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    rows = page._rows
    started, release = Event(), Event()
    compare = ui.compare_xml_files

    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return compare(*args, **kwargs)

    monkeypatch.setattr(ui, "compare_xml_files", blocked)
    page._compare()
    try:
        assert started.wait(5)
        page._progress_dialog._button.click()
    finally:
        release.set()
    wait_done(page, qapp)
    assert page._rows is rows and not dialogs.errors
    assert "Previous results retained" in page._summary.text()
    assert "Cancelled: 1" in page._progress_dialog._summary.text()


def test_manual_comparison_validates_both_sources_and_cancelled_picker_keeps_path(qapp, xml_files):
    page, dialogs, _, _ = manual_page(xml_files)
    before = dict(page._xml_paths)
    page._xml_buttons["Base"].click()
    assert page._xml_paths == before
    page._xml_paths["Base"] = ""
    page._compare()
    wait_done(page, qapp)
    assert dialogs.errors and "Base XML" in dialogs.errors[0][1]
    assert not page._export_btn.isEnabled()


def test_mode_switch_restores_master_results_reviews_and_update_actions(qapp, xml_files):
    page, dialogs, session, _ = build_page()
    page._select_all()
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    page._set_comment(0, "Master review")
    master_rows = page._rows
    updates = page._impl_updates
    page._manual_mode_btn.click()
    assert not page._rows and not page._export_btn.isEnabled() and not page._impl_btn.isEnabled()
    dialogs.files = list(map(str, xml_files))
    for source in ("Base", "Target"):
        page._xml_buttons[source].click()
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    manual_rows = page._rows
    page._master_mode_btn.click()
    assert page._rows is master_rows and page._comment(0) == "Master review"
    assert page._impl_updates is updates and page._impl_btn.isEnabled()
    assert page._table.columnCount() == 7 and page._selected_rows() == [0]
    assert page._table.item(0, 0).text() == "P1"
    assert page._compare_btn.text() == "Compare selected"
    assert page._layout.indexOf(page._summary) > page._layout.indexOf(page._table)
    page._manual_mode_btn.click()
    assert page._rows is manual_rows and page._compared_files == tuple(map(str, xml_files))
    session.export_job_xml.assert_called_once()


def test_manual_reader_enforces_parser_size_limit(xml_files, tmp_path):
    oversized = tmp_path / "oversized.xml"
    oversized.write_bytes(b" " * (service.MAX_XML_BYTES + 1))
    with pytest.raises(ValueError, match="Target XML: WebFlow XML exceeds the 10 MiB limit"):
        service.compare_xml_files(str(xml_files[0]), str(oversized))
