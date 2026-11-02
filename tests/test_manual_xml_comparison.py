"""Local XML comparison reuses the retained Comparison workspace without Master/browser access."""
from threading import Event
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
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


@pytest.mark.parametrize("target_count", [1, 2])
def test_exclusions_precede_manual_comparison_and_never_reach_results_or_export(
    qapp, tmp_path, monkeypatch, target_count,
):
    paths = [tmp_path / f"source{index}.xml" for index in range(target_count + 1)]
    for index, path in enumerate(paths):
        path.write_bytes(export_xml({
            "General/Power": "93", "Files/Attachment": str(index), "Notes/Review": str(index),
        }, job_id=None))
    compare = Mock(wraps=service.compare_xml_datasets)
    monkeypatch.setattr(service, "compare_xml_datasets", compare)
    page, dialogs, _, _ = manual_page(paths[:2])
    if target_count > 1:
        dialogs.files = [[str(paths[2])]]
        page._xml_buttons["Target"].click()
    page._compare()
    wait_done(page, qapp)
    assert not dialogs.errors
    assert compare.call_args.args[0] == {"General/Power": "93"}
    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "General/Power"
    assert all(not row.deviation for _, _, row in page._rows)
    assert "Total: 1 | Match: 1 | Deviation: 0" in page._summary.text()
    dialogs.save_path = str(tmp_path / "report.html")
    page._export()
    html = (tmp_path / "report.html").read_text()
    assert "General/Power" in html and "Files/Attachment" not in html and "Notes/Review" not in html


@pytest.mark.parametrize("target_count", [1, 2])
def test_new_manual_comparisons_read_latest_saved_exclusions(qapp, tmp_path, target_count):
    paths = [tmp_path / f"source{index}.xml" for index in range(target_count + 1)]
    for path in paths:
        path.write_bytes(export_xml({"General/Power": "93", "Files/Attachment": "file", "Notes/Review": "note"}, job_id=None))
    page, dialogs, _, _ = manual_page(paths[:2])
    if target_count == 2:
        dialogs.files = [[str(paths[2])]]
        page._xml_buttons["Target"].click()
    for prefixes, expected in (
        (["General/"], ["Files/Attachment", "Notes/Review"]),
        ([], ["Files/Attachment", "General/Power", "Notes/Review"]),
        (["Files/", "Notes/"], ["General/Power"]),
    ):
        previous = page._rows
        page._settings.update(xml_comparison_exclusions=prefixes)
        assert page._rows is previous
        page._compare()
        wait_done(page, qapp)
        page._progress_dialog.close()
        assert not dialogs.errors
        assert [row.parameter for _, _, row in page._rows] == expected


@pytest.mark.parametrize("target_count", [1, 2])
def test_master_scope_option_does_not_disable_manual_exclusions(qapp, tmp_path, target_count):
    paths = [tmp_path / f"source{index}.xml" for index in range(target_count + 1)]
    for path in paths:
        path.write_bytes(export_xml({"General/Power": "93", "Files/Attachment": "file"}, job_id=None))
    page, dialogs, _, _ = manual_page(paths[:2])
    if target_count == 2:
        dialogs.files = [[str(paths[2])]]
        page._xml_buttons["Target"].click()
    for master_only, expected in (
        (True, ["General/Power"]),
        (False, ["General/Power"]),
    ):
        page._settings.update(
            xml_comparison_exclusions=["Files/"],
            xml_comparison_exclusions_master_only=master_only,
        )
        page._compare_btn.click()
        wait_done(page, qapp)
        page._progress_dialog.close()
        assert not dialogs.errors
        assert [row.parameter for _, _, row in page._rows] == expected


def test_manual_mode_needs_no_master_or_browser_and_reuses_result_table(qapp, xml_files):
    page, dialogs, browser, updater = manual_page(xml_files)
    original = [path.read_bytes() for path in xml_files]
    assert page._variants == [] and page._compare_btn.isEnabled()
    assert page._variants_table.isHidden() and page._impl_btn.isHidden()
    assert page._select_all_btn.isHidden() and page._clear_selection_btn.isHidden()
    assert page._base_chips.chips[0].label.text() == xml_files[0].name
    assert page._base_chips.chips[0].label.toolTip() == str(xml_files[0])
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
    assert page._base_chips.chips[0].label.text() == xml_files[0].name
    assert len(page._target_chips.chips) == 1
    assert "Total: 4 | Match: 1 | Deviation: 3" in page._summary.text()
    assert page._summary.isHidden()
    actions = page._layout.itemAt(page._layout.indexOf(page._table) - 1).layout()
    assert actions.indexOf(page._compare_btn) >= 0
    assert page._progress_dialog._summary.text() == "Completed: 1\nFailed: 0\nTotal: 1"
    for column in range(5):
        assert not page._table.horizontalHeaderItem(column).icon().isNull()
        assert page._table.frozen.view.isColumnHidden(column) == (column != 0)


def test_base_chip_removal_and_reselection_preserve_completed_results(qapp, xml_files):
    page, dialogs, _, _ = manual_page(xml_files)
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    rows = page._rows
    page._base_chips.chips[0].remove_button.click()
    assert page._xml_paths["Base"] == ""
    assert page._base_chips.isHidden() and not page._xml_labels["Base"].isHidden()
    assert not page._compare_btn.isEnabled()
    assert page._rows is rows and page._export_btn.isEnabled()
    dialogs.files = [str(xml_files[0])]
    page._xml_buttons["Base"].click()
    assert page._xml_paths["Base"] == str(xml_files[0])
    assert len(page._base_chips.chips) == 1 and page._compare_btn.isEnabled()
    assert page._xml_labels["Base"].isHidden() and page._rows is rows


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_manual_source_chips_wrap_on_workspace_resize_without_empty_list_space(qapp, xml_files, theme):
    from autohub.ui.theme import apply_theme

    apply_theme(qapp, theme)
    page, dialogs, _, _ = manual_page(xml_files)
    dialogs.files = [[f"/exports/WF21821{index}_export.xml" for index in range(5)]]
    page._xml_buttons["Target"].click()
    page.resize(1400, 900)
    page.show()
    qapp.processEvents()
    assert page._xml_buttons["Base"].geometry().center().y() == page._xml_buttons["Target"].geometry().center().y()
    assert page._clear_targets_btn.geometry().center().y() == page._xml_buttons["Target"].geometry().center().y()
    wide_height = page._target_chips.height()
    assert wide_height == page._target_chips.chips[0].height()
    page.resize(800, 900)
    qapp.processEvents()
    assert page._target_chips.height() > wide_height
    assert len({chip.y() for chip in page._target_chips.chips}) > 1
    assert page._table.geometry().top() - page._compare_btn.geometry().bottom() - 1 == page._layout.spacing()
    page._clear_targets_btn.click()
    qapp.processEvents()
    assert page._target_chips.isHidden()
    assert page._xml_labels["Target"].text() == "0 files selected"


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
    page._header_filter.set_column_filter(4, ColumnFilter(text="reviewed"))
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
    page._header_filter.set_column_filter(0, ColumnFilter(text="nothing-visible"))
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
    page._target_paths = [str(xml_files[0])]
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
    assert not page._summary.isHidden()
    page._manual_mode_btn.click()
    assert page._summary.isHidden()
    assert page._rows is manual_rows and page._compared_files == tuple(map(str, xml_files))
    session.export_job_xml.assert_called_once()


def test_manual_reader_enforces_parser_size_limit(xml_files, tmp_path):
    oversized = tmp_path / "oversized.xml"
    oversized.write_bytes(b" " * (service.MAX_XML_BYTES + 1))
    with pytest.raises(ValueError, match="Target XML: WebFlow XML exceeds the 10 MiB limit"):
        service.compare_xml_files(str(xml_files[0]), str(oversized))


@pytest.fixture
def multiple_xml_files(xml_files, tmp_path):
    additional = tmp_path / "second.xml"
    additional.write_bytes(export_xml({
        "General/Power": "93", "General/Same": "0010", "Extra/SecondOnly": "second",
    }, job_id=None))
    return (*xml_files, additional)


def test_target_picker_adds_removes_and_deduplicates_without_losing_results(qapp, multiple_xml_files, tmp_path):
    base, first, second = multiple_xml_files
    page, dialogs, _, _ = manual_page((base, first))
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    rows = page._rows
    alias = tmp_path / "alias.xml"
    alias.symlink_to(first)
    dialogs.files = [[str(first), str(alias), str(second)]]
    page._xml_buttons["Target"].click()
    assert page._target_paths == [str(first), str(second)]
    assert len(page._target_chips.chips) == 2
    assert page._xml_labels["Target"].text() == "2 files selected"
    assert not page._clear_targets_btn.isHidden()
    assert page._rows is rows and page._compared_files == (str(base), str(first))
    chip = page._target_chips.chips[0]
    assert chip.label.text() == first.name and chip.label.toolTip() == str(first)
    chip.remove_button.click()
    assert page._target_paths == [str(second)] and len(page._target_chips.chips) == 1
    assert page._xml_labels["Target"].text() == "1 file selected"
    assert page._clear_targets_btn.isHidden() and page._rows is rows
    dialogs.files = [[str(first)]]
    page._xml_buttons["Target"].click()
    page._clear_targets_btn.click()
    assert not page._target_paths and not page._compare_btn.isEnabled()
    assert page._rows is rows and page._export_btn.isEnabled()
    assert page._target_chips.isHidden()


def test_multi_target_engine_parses_base_once_and_keeps_union_statuses(multiple_xml_files, monkeypatch):
    parsed = Mock(wraps=service.parse_xml)
    monkeypatch.setattr(service, "parse_xml", parsed)
    progress = Mock()
    base, first, second = multiple_xml_files
    result = service.compare_xml_files(str(base), [str(first), str(second)], progress=progress)
    assert parsed.call_count == 3
    assert sum(call.args[0] == base.read_bytes() for call in parsed.call_args_list) == 1
    rows = {row.parameter: row for row in result}
    assert list(rows) == sorted({
        "General/Power", "General/Same", "Extra/BaseOnly", "Extra/TargetOnly", "Extra/SecondOnly",
    })
    assert rows["General/Power"].targets == ("94", "93")
    assert rows["General/Power"].target_statuses == (Status.VALUE_MISMATCH, Status.MATCH)
    assert rows["General/Power"].status == Status.VALUE_MISMATCH
    assert rows["General/Same"].status == Status.MATCH
    assert rows["Extra/BaseOnly"].target_statuses == (Status.MISSING_IN_TARGET,) * 2
    assert rows["Extra/TargetOnly"].target_statuses == (Status.MISSING_IN_BASE, Status.MISSING_IN_TARGET)
    assert rows["Extra/SecondOnly"].target_statuses == (Status.MISSING_IN_TARGET, Status.MISSING_IN_BASE)
    assert (0, "Completed", "") in [call.args for call in progress.call_args_list]
    assert (1, "Completed", "") in [call.args for call in progress.call_args_list]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_multi_target_results_reviews_filters_summary_and_export(qapp, multiple_xml_files, tmp_path, theme):
    from autohub.ui.theme import apply_theme

    apply_theme(qapp, theme)
    base, first, second = multiple_xml_files
    page, dialogs, _, _ = manual_page((base, first))
    dialogs.files = [[str(second)]]
    page._xml_buttons["Target"].click()
    page._compare()
    assert not page._target_chips.isEnabled() and not page._clear_targets_btn.isEnabled()
    assert not page._base_chips.isEnabled()
    wait_done(page, qapp)
    assert not dialogs.errors
    assert page._target_chips.isEnabled() and page._base_chips.isEnabled()
    assert page._table.columnCount() == 6 and page._status_column == 4 and page._comment_column == 5
    headers = [page._table.horizontalHeaderItem(i).text() for i in range(6)]
    assert headers == ["Parameter", "Base", f"Target 1: {first.name}", f"Target 2: {second.name}", "Status", "Comment"]
    assert page._progress_dialog._summary.text() == "Completed: 2\nFailed: 0\nTotal: 2"
    assert page._progress_dialog._items.item(1, 0).text() == second.name
    assert "Overall: Total: 5 | Match: 1 | Deviation: 4" in page._summary.text()
    assert f"Target 1 ({first.name}): Match: 1 | Deviation: 4" in page._summary.text()
    assert f"Target 2 ({second.name}): Match: 2 | Deviation: 3" in page._summary.text()
    assert page._summary.isHidden()
    assert page._base_chips.chips[0].label.text() == base.name
    assert len(page._target_chips.chips) == 2
    actions = page._layout.itemAt(page._layout.indexOf(page._table) - 1).layout()
    assert actions.indexOf(page._compare_btn) >= 0
    index = next(i for i, (_, _, row) in enumerate(page._rows) if row.parameter == "General/Power")
    assert page._result_item(index, 2).background().color().name() == "#fde2e1"
    assert page._result_item(index, 3).background().style() == Qt.NoBrush
    assert "Target 1" in page._comment(index) and Status.VALUE_MISMATCH.value in page._comment(index)
    page._header_filter.set_column_filter(3, ColumnFilter(allowed=frozenset({"93"})))
    assert len(visible_rows(page)) == 1
    page._table.sortItems(0, Qt.DescendingOrder)
    page._set_status(index, Status.MATCH)
    calculated_comment = page._comment(index)
    assert "Target 1" in calculated_comment
    page._set_comment(index, "")
    assert page._comment(index) == ""
    page._set_comment(index, "accepted deviation")
    assert "Overall: Total: 5 | Match: 2 | Deviation: 3" in page._summary.text()
    assert f"Target 1 ({first.name}): Match: 1 | Deviation: 4" in page._summary.text()
    item = page._result_item(index, 5)
    page._table.selectionModel().setCurrentIndex(
        page._table.model().index(item.row(), 5), QItemSelectionModel.ClearAndSelect,
    )
    assert not page._table.isRowHidden(page._result_item(index, 5).row())
    assert not page._table.isColumnHidden(5)
    assert page._result_clipboard.selected_cells() == [(page._result_item(index, 5).row(), 5)]
    QApplication.clipboard().setText("reviewed all targets")
    page._paste_result()
    assert page._comment(index) == "reviewed all targets"
    dialogs.save_path = str(tmp_path / "multi.html")
    page._export()
    html = (tmp_path / "multi.html").read_text()
    assert html.count("<th>") == 6 and html.count("<tr class=") == 5
    assert first.name in html and second.name in html
    assert 'id="target-xml-1"' in html and 'id="target-xml-2"' in html
    assert 'data-status="MISSING_IN_BASE"' in html
    assert 'data-status="MISSING_IN_TARGET"' in html
    assert 'class="target-deviation"' in html and 'data-calculated="VALUE_MISMATCH"' in html
    assert "reviewed all targets" in html and "fill(status,4)" in html
    assert str(tmp_path) not in html
    page._progress_dialog.close()
    page._master_mode_btn.click()
    page._manual_mode_btn.click()
    assert page._table.columnCount() == 6 and page._comment(index) == "reviewed all targets"
    apply_theme(qapp, "dark")


def test_failed_additional_target_preserves_previous_result(qapp, multiple_xml_files, tmp_path):
    base, first, second = multiple_xml_files
    page, dialogs, _, _ = manual_page((base, first))
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    rows, files = page._rows, page._compared_files
    invalid = tmp_path / "broken.xml"
    invalid.write_bytes(b"<broken")
    dialogs.files = [[str(second), str(invalid)]]
    page._xml_buttons["Target"].click()
    page._compare()
    wait_done(page, qapp)
    assert "Invalid WebFlow XML" in dialogs.errors[-1][1] and "broken.xml" in dialogs.errors[-1][1]
    assert page._rows is rows and page._compared_files == files and page._table.columnCount() == 5


def test_compare_requires_base_and_at_least_one_target(qapp, xml_files):
    page = ui.ComparisonWidget(FakeDialogs(files=[[str(xml_files[1])]]))
    page._manual_mode_btn.click()
    assert not page._compare_btn.isEnabled()
    page._xml_buttons["Target"].click()
    assert not page._compare_btn.isEnabled()
    with pytest.raises(ValueError, match="at least one"):
        service.compare_xml_files(str(xml_files[0]), [])


def test_three_targets_with_duplicate_filenames_and_return_to_single_layout(qapp, multiple_xml_files, tmp_path):
    base, first, second = multiple_xml_files
    folder = tmp_path / "another"
    folder.mkdir()
    third = folder / first.name
    third.write_bytes(base.read_bytes())
    page, dialogs, _, _ = manual_page((base, first))
    dialogs.files = [[str(second), str(third)]]
    page._xml_buttons["Target"].click()
    assert len(page._target_paths) == 3
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    assert page._status_column == 5 and page._comment_column == 6 and page._table.columnCount() == 7
    headers = page._result_headers()
    assert headers[2] == f"Target 1: {first.name}" and headers[4] == f"Target 3: {third.name}"
    assert all(len(row.targets) == len(row.target_statuses) == 3 for _, _, row in page._rows)
    page._clear_targets()
    assert page._table.columnCount() == 7 and page._export_btn.isEnabled()
    dialogs.files = [[str(third)]]
    page._xml_buttons["Target"].click()
    assert page._table.columnCount() == 7
    page._compare()
    wait_done(page, qapp)
    assert page._table.columnCount() == 5 and page._status_column == 3 and page._comment_column == 4
    assert all(row.status == Status.MATCH for _, _, row in page._rows)
    assert not page._header_filter.is_active()


def test_multi_target_cancellation_stops_before_reading_remaining_targets(multiple_xml_files, monkeypatch):
    base, first, second = multiple_xml_files
    cancelled = Event()
    parsed = Mock(wraps=service.parse_xml)
    monkeypatch.setattr(service, "parse_xml", parsed)
    events = []

    def progress(index, status, error):
        events.append((index, status, error))
        if index == 0 and status == "Completed":
            cancelled.set()

    result = service.compare_xml_files(
        str(base), [str(first), str(second)], progress=progress, cancelled=cancelled.is_set,
    )
    assert result is None and parsed.call_count == 2
    assert (1, "Cancelled", "") in events


def test_multi_target_samefile_export_guard_protects_additional_targets(qapp, multiple_xml_files, tmp_path):
    base, first, second = multiple_xml_files
    page, dialogs, _, _ = manual_page((base, first))
    dialogs.files = [[str(second)]]
    page._xml_buttons["Target"].click()
    page._compare()
    wait_done(page, qapp)
    alias = tmp_path / "report.html"
    alias.hardlink_to(second)
    original = second.read_bytes()
    dialogs.save_path = str(alias)
    page._export()
    assert dialogs.errors and second.read_bytes() == original
