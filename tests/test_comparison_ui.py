"""Batch Comparison UI, background exports, filters and existing cross-module wiring."""
from threading import Event
from unittest.mock import Mock, call

import pytest
from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QItemSelectionModel, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QStyle, QStyleOptionComboBox, QStyleOptionViewItem, QTableWidgetSelectionRange

from autohub.modules.comparison import ui
from autohub.modules.comparison.comparison import Status
from autohub.modules.comparison.service import ComparisonService
from autohub.modules.creation.ui import CreationWidget
from autohub.modules.home.ui import HomeWidget
from autohub.modules.home.row_filter import ColumnFilter
from autohub.modules.home import table_filter
from autohub.ui.main_window import MainWindow
from autohub.ui import webflow_link_delegate
from tests.fakes import FakeDialogs, MemorySettings
from tests.test_comparison import export_xml, target_parameters, variant


@pytest.fixture(autouse=True)
def cleanup_comparison_widgets(qapp):
    previous = set(qapp.topLevelWidgets())
    yield
    for widget in set(qapp.topLevelWidgets()) - previous:
        if isinstance(widget, ui.ComparisonWidget):
            widget.shutdown()
    qapp.processEvents()
    for widget in set(qapp.topLevelWidgets()) - previous:
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def build_page(variants=None, exports=None, settings=None):
    session = Mock()
    session.open_dashboard_page.return_value = True
    session.export_job_xml.side_effect = exports or [export_xml(target_parameters())]
    factory = Mock(return_value=session)
    dialogs = FakeDialogs()
    page = ui.ComparisonWidget(dialogs, ComparisonService(factory), settings)
    page.set_variants(variants or [variant()])
    return page, dialogs, session, factory


def wait_done(page, qapp):
    timer = QElapsedTimer()
    timer.start()
    while page._running and timer.elapsed() < 5000:
        qapp.processEvents()
        QTest.qWait(5)
    assert not page._running


def visible_rows(page):
    return [index for index in range(page._table.rowCount()) if not page._table.isRowHidden(index)]


def test_comparison_lists_only_valid_links_and_allows_multiple_selection(qapp):
    page, _, _, _ = build_page([
        variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13"),
        variant("no_link", link=""), variant("invalid", link="bad"), variant("wrong_scheme", link="file:///12"),
    ])
    assert page._variants_table.rowCount() == 2
    assert [page._variants_table.horizontalHeaderItem(i).text() for i in range(6)] == list(ui._VARIANT_HEADERS)
    assert page._variants_table.item(0, 1).text() == "P1"
    assert page._variants_table.item(1, 1).text() == "P2"
    assert page._variants_table.item(0, 2).text() == "WF12"
    assert page._variants_table.item(0, 2).data(Qt.UserRole) == "https://webflow/app/ShowJob/12"
    for column in range(1, 6):
        assert bool(page._variants_table.item(0, column).flags() & Qt.ItemIsEditable) == (column == 3)
    assert page._variants_table.item(0, 2).toolTip() == "Double-click to open. Right-click for options"
    assert page._variants_table.columnWidth(4) < 150
    assert not page._variants_table.horizontalHeader().stretchLastSection()
    assert not page._compare_btn.isEnabled()
    page._select_all_btn.click()
    assert page._selected_rows() == [0, 1]
    assert page._compare_btn.isEnabled()
    page._clear_selection_btn.click()
    assert not page._selected_rows() and not page._compare_btn.isEnabled()
    page.set_variants([])
    assert page._variants_table.rowCount() == 0


def test_automatic_batch_combines_results_and_supports_all_filters(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    page, dialogs, session, _ = build_page(variants, [
        export_xml({**target_parameters(), "General/Power": "94", "General/Model": "extra"}),
        export_xml(target_parameters("P2", "0011"), job_id="13"),
    ])
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert dialogs.errors == []
    assert session.export_job_xml.call_count == 2
    assert [page._table.horizontalHeaderItem(i).text() for i in range(7)] == list(ui._TARGET_HEADERS)
    assert page._table.rowCount() == 6
    assert all(page._variants_table.item(row, 4).text() == "Completed" for row in range(2))
    assert "2 completed; 0 failed" in page._summary.text()
    page._deviations.setChecked(True)
    assert len(visible_rows(page)) == 1
    page._search.setText("power")
    assert len(visible_rows(page)) == 1
    index = visible_rows(page)[0]
    assert page._table.item(index, 2).text() == "93"
    assert page._table.item(index, 4).text() == "94"
    assert page._table.item(index, 5).text() == Status.VALUE_MISMATCH
    page._search.clear()
    page._status_filter.setCurrentText(Status.VALUE_MISMATCH.value)
    assert len(visible_rows(page)) == 1
    page._variant_filter.setCurrentIndex(2)
    assert len(visible_rows(page)) == 0


def test_failed_variant_displays_error_and_does_not_hide_successful_results(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    page, dialogs, _, _ = build_page(variants, [
        b"<broken", export_xml(target_parameters("P2", "0011"), job_id="13"),
    ])
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert page._variants_table.item(0, 4).text() == "Failed"
    assert "Invalid WebFlow XML" in page._variants_table.item(0, 5).text()
    assert page._variants_table.item(1, 4).text() == "Completed"
    assert page._table.rowCount() == 3
    assert "1 completed; 1 failed" in page._summary.text()
    assert not dialogs.errors


def test_mixed_base_and_no_base_results_keep_correct_values_and_filters(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    page, _, session, _ = build_page(variants, [
        export_xml(target_parameters()), export_xml(target_parameters(), job_id="99"),
        export_xml(target_parameters("P2", "0011"), job_id="13"),
    ])
    page._variants_table.item(0, 3).setText("https://webflow/app/ShowJob/99")
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert session.export_job_xml.call_count == 3
    assert [page._table.horizontalHeaderItem(i).text() for i in range(7)] == list(ui._TARGET_HEADERS)
    assert any(row.status == Status.MATCHES_BOTH for _, _, row in page._rows)
    assert any(part == "P2" and row.status == Status.MATCH for part, _, row in page._rows)
    assert len({part for part, _, _ in page._rows}) == 2
    for index, (part, _, _) in enumerate(page._rows):
        if part == "P2":
            assert page._table.item(index, 3).text() == ""
    page._status_filter.setCurrentText(Status.MATCH.value)
    assert visible_rows(page) and all(page._table.item(i, 0).text() == "P2" for i in visible_rows(page))
    page._status_filter.setCurrentText(Status.MATCHES_BOTH.value)
    assert visible_rows(page) and all(page._table.item(i, 0).text() == "P1" for i in visible_rows(page))
    page._variants_table.item(0, 3).setText("")
    assert page._rows and page._table.columnCount() == 7


def test_invalid_base_link_only_fails_its_variant(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    page, _, session, _ = build_page(variants, [
        export_xml(target_parameters()), export_xml(target_parameters("P2", "0011"), job_id="13"),
    ])
    page._variants_table.item(0, 3).setText("invalid")
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert session.export_job_xml.call_count == 2
    assert page._variants_table.item(0, 4).text() == "Failed"
    assert "Base XML:" in page._variants_table.item(0, 5).text()
    assert page._variants_table.item(1, 4).text() == "Completed"
    assert page._table.rowCount() == 3


def test_distinct_edited_base_links_are_passed_to_their_own_targets(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    links = ["https://webflow/app/ShowJob/99", "https://webflow/app/ShowJob/100"]
    page, _, session, _ = build_page(variants, [
        export_xml(target_parameters()), export_xml(target_parameters(), job_id="99"),
        export_xml(target_parameters("P2", "0011"), job_id="13"),
        export_xml({**target_parameters(), "General/Power": "94"}, job_id="100"),
    ])
    for row, link in enumerate(links):
        page._variants_table.item(row, 3).setText(link)
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert session.export_job_xml.call_args_list == [
        call(variants[0]["webflow_link"]), call(links[0]),
        call(variants[1]["webflow_link"]), call(links[1]),
    ]
    assert [
        (part, row.base, row.status) for part, _, row in page._rows if row.parameter == "General/Power"
    ] == [("P1", "93", Status.MATCHES_BOTH), ("P2", "94", Status.MATCHES_MASTER)]


def test_only_checked_variants_are_exported_and_saved_connection_is_used(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    settings = MemorySettings({"webflow_environment": "Acceptance"})
    page, _, session, factory = build_page(
        variants, [export_xml(target_parameters("P2", "0011"), job_id="13")], settings,
    )
    page._variants_table.item(0, 3).setText("https://webflow/app/ShowJob/99")
    page._variants_table.item(1, 0).setCheckState(Qt.Checked)
    page._compare_btn.click()
    wait_done(page, qapp)
    session.export_job_xml.assert_called_once_with(variants[1]["webflow_link"])
    factory.assert_called_once_with(
        driver_path="", base_url="https://rb-pde-int.bosch.com:8881/app/dashboard"
    )
    assert page._table.columnCount() == 7


def test_base_links_follow_variant_identity_on_reorder_without_mutating_master(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    page, _, _, _ = build_page(variants)
    page._variants_table.item(0, 3).setText("https://webflow/app/ShowJob/99")
    page._variants_table.item(0, 0).setCheckState(Qt.Checked)
    page.set_variants(list(reversed(variants)))
    assert page._variants_table.item(0, 3).text() == ""
    assert page._variants_table.item(1, 3).text() == "WF99"
    assert page._variants_table.item(1, 3).data(Qt.UserRole) == "https://webflow/app/ShowJob/99"
    assert page._selected_rows() == [1]
    assert all("base_webflow_link" not in item for item in variants + page._variants)


def test_exporting_base_progress_is_shown_on_its_variant_row(qapp):
    started, release = Event(), Event()
    page, _, session, _ = build_page()
    base_link = "https://webflow/app/ShowJob/99"

    def export(link):
        if link == base_link:
            started.set()
            if not release.wait(5):
                raise RuntimeError("test release timed out")
            return export_xml(target_parameters(), job_id="99")
        return export_xml(target_parameters())

    session.export_job_xml.side_effect = export
    page._variants_table.item(0, 3).setText(base_link)
    page._select_all_btn.click()
    page._compare_btn.click()
    try:
        assert started.wait(2)
        qapp.processEvents()
        assert page._variants_table.item(0, 4).text() == "Exporting Base XML"
        assert page._progress_dialog._operation.text() == "Exporting Base XML"
        assert not page._variants_table.isEnabled()
    finally:
        release.set()
        wait_done(page, qapp)
    assert page._variants_table.item(0, 4).text() == "Completed"


def test_busy_run_disables_source_changes_and_leave_until_finished(qapp):
    started, release = Event(), Event()
    page, dialogs, session, _ = build_page()

    def export(_link):
        started.set()
        if not release.wait(5):
            raise RuntimeError("test release timed out")
        return export_xml(target_parameters())
    session.export_job_xml.side_effect = export
    page._select_all_btn.click()
    page._compare_btn.click()
    try:
        assert started.wait(2)
        qapp.processEvents()
        assert page._variants_table.item(0, 4).text() == "Exporting Target XML"
        assert not page._compare_btn.isEnabled() and not page._variants_table.isEnabled()
        assert not page.confirm_leave()
        assert dialogs.infos
    finally:
        release.set()
        wait_done(page, qapp)
    assert page.confirm_leave() and page._compare_btn.isEnabled()


def test_master_reload_during_run_discards_stale_results(qapp):
    started, release = Event(), Event()
    page, _, session, _ = build_page()

    def export(_link):
        started.set()
        release.wait(5)
        return export_xml(target_parameters())
    session.export_job_xml.side_effect = export
    page._select_all_btn.click()
    page._compare_btn.click()
    try:
        assert started.wait(2)
        page.set_variants([variant("other", link="")])
    finally:
        release.set()
        wait_done(page, qapp)
    assert not page._rows and page._table.rowCount() == 0
    assert "Master data changed" in page._summary.text()


def test_existing_home_creation_signals_feed_comparison_without_shared_mutation(qapp):
    settings = MemorySettings()
    home = HomeWidget(Mock(), settings)
    creation = CreationWidget(Mock(), settings)
    page = ui.ComparisonWidget(FakeDialogs())
    MainWindow._wire_cross_module_signals([home, creation, page])
    source = variant(link="")
    home.variantsLoaded.emit([source])
    assert page._variants_table.rowCount() == 0
    creation.webflowLinksUpdated.emit({"P1": "https://webflow/app/ShowJob/12"})
    creation.webflowNumbersUpdated.emit({"P1": {"AX": "0099", "AW": "ECR"}}, True)
    assert page._variants_table.rowCount() == 1
    assert page._variants_table.item(0, 1).text() == "P1"
    assert page._variants[0]["hardware"]["software_part_number"] == "0099"
    assert page._variants[0]["hardware"]["ecr_number"] == "ECR"
    assert source["hardware"]["software_part_number"] == "0010"
    home.variantsLoaded.emit([variant("other", link="")])
    assert page._variants_table.rowCount() == 0 and not page._rows


def test_comparison_supports_theme_changes_with_results(qapp):
    from autohub.ui.theme import apply_theme

    page, _, _, _ = build_page()
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    apply_theme(qapp, "light")
    apply_theme(qapp, "dark")
    assert page._table.rowCount() == 3


def test_unconfigured_service_reports_error_instead_of_manual_fallback(qapp):
    dialogs = FakeDialogs()
    page = ui.ComparisonWidget(dialogs)
    page.set_variants([variant()])
    page._select_all_btn.click()
    page._compare_btn.click()
    assert "not configured" in dialogs.errors[-1][1]


def test_progress_dialog_is_immediate_modal_responsive_and_cannot_close_during_run(qapp):
    started, release = Event(), Event()
    page, _, session, _ = build_page()

    def export(_link):
        started.set()
        if not release.wait(5):
            raise RuntimeError("test release timed out")
        return export_xml(target_parameters())

    session.export_job_xml.side_effect = export
    page._select_all_btn.click()
    page._compare_btn.click()
    dialog = page._progress_dialog
    try:
        assert dialog.isVisible() and dialog.isModal()
        assert dialog._overall.text() == "Overall: 0 / 1 (0%)"
        assert started.wait(2)
        qapp.processEvents()
        assert dialog._current.text() == "Current: P1"
        assert dialog._operation.text() == "Exporting Target XML"
        dialog.reject()
        dialog.accept()
        dialog.done(0)
        dialog.close()
        QTest.keyClick(dialog, Qt.Key_Escape)
        assert dialog.isVisible()
        assert page._running
    finally:
        release.set()
        wait_done(page, qapp)
    assert dialog._bar.value() == 1
    assert dialog._overall.text() == "Overall: 1 / 1 (100%)"
    assert dialog._summary.text() == "Completed: 1\nFailed: 0\nTotal: 1"
    assert dialog._button.text() == "Close"
    dialog._button.click()
    assert not dialog.isVisible()


def test_progress_failure_counts_towards_overall_and_next_job_continues(qapp):
    started, release = Event(), Event()
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    page, _, session, _ = build_page(variants)

    def export(link):
        if link.endswith("/12"):
            return b"<broken"
        started.set()
        if not release.wait(5):
            raise RuntimeError("test release timed out")
        return export_xml(target_parameters("P2", "0011"), job_id="13")

    session.export_job_xml.side_effect = export
    page._select_all_btn.click()
    page._compare_btn.click()
    dialog = page._progress_dialog
    try:
        assert started.wait(2)
        qapp.processEvents()
        assert dialog._overall.text() == "Overall: 1 / 2 (50%)"
        assert dialog._items.item(0, 1).text() == "Failed"
        assert "Invalid WebFlow XML" in dialog._items.item(0, 2).text()
        assert dialog._current.text() == "Current: P2"
    finally:
        release.set()
        wait_done(page, qapp)
    assert dialog._overall.text() == "Overall: 2 / 2 (100%)"
    assert dialog._summary.text() == "Completed: 1\nFailed: 1\nTotal: 2"


def test_cancel_dialog_finishes_active_variant_skips_remaining_and_keeps_results(qapp):
    started, release = Event(), Event()
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    page, _, session, _ = build_page(variants)

    def export(_link):
        started.set()
        if not release.wait(5):
            raise RuntimeError("test release timed out")
        return export_xml(target_parameters())

    session.export_job_xml.side_effect = export
    page._select_all_btn.click()
    page._compare_btn.click()
    dialog = page._progress_dialog
    try:
        assert started.wait(2)
        qapp.processEvents()
        dialog._button.click()
        assert page._cancel.is_set()
        assert dialog.isVisible() and not dialog._button.isEnabled()
        assert page._running
    finally:
        release.set()
        wait_done(page, qapp)
    session.export_job_xml.assert_called_once_with(variants[0]["webflow_link"])
    assert dialog._summary.text() == "Completed: 1\nFailed: 0\nTotal: 2\nCancelled: 1"
    assert dialog._items.item(1, 1).text() == "Cancelled"
    assert dialog._overall.text() == "Overall: 1 / 2 (50%)"
    assert page._variants_table.item(1, 4).text() == "Cancelled"
    assert page._table.rowCount() == 3
    assert "1 completed; 0 failed. 1 cancelled." in page._summary.text()
    assert page._compare_btn.isEnabled()
    dialog._button.click()
    session.export_job_xml.side_effect = [
        export_xml(target_parameters()), export_xml(target_parameters("P2", "0011"), job_id="13"),
    ]
    page._compare_btn.click()
    wait_done(page, qapp)
    assert not page._cancel.is_set()
    assert page._progress_dialog._summary.text() == "Completed: 2\nFailed: 0\nTotal: 2"


def test_progress_dialog_finishes_even_when_master_reload_discards_results(qapp):
    started, release = Event(), Event()
    page, _, session, _ = build_page()

    def export(_link):
        started.set()
        release.wait(5)
        return export_xml(target_parameters())

    session.export_job_xml.side_effect = export
    page._select_all_btn.click()
    page._compare_btn.click()
    try:
        assert started.wait(2)
        page.set_variants([])
    finally:
        release.set()
        wait_done(page, qapp)
    assert page._progress_dialog._summary.text() == "Completed: 1\nFailed: 0\nTotal: 1"
    assert page._progress_dialog._button.text() == "Close"
    assert not page._rows


def test_unexpected_worker_failure_finishes_dialog_and_releases_controls(qapp):
    page, dialogs, _, _ = build_page()
    page._service.run = Mock(side_effect=RuntimeError("worker failed"))
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert page._progress_dialog._summary.text() == "Completed: 0\nFailed: 1\nTotal: 1"
    assert page._progress_dialog._items.item(0, 2).text() == "worker failed"
    assert page._progress_dialog._button.text() == "Close"
    assert page._compare_btn.isEnabled()
    assert dialogs.errors[-1][1] == "worker failed"


def test_variant_only_labels_filters_and_internal_software_matching(qapp):
    variants = [variant(software="0010"), variant(software="0011", link="https://webflow/app/ShowJob/13")]
    page, _, _, _ = build_page(variants, [
        export_xml(target_parameters(software="0010")),
        export_xml(target_parameters(software="0011"), job_id="13"),
    ])
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert [page._variant_filter.itemText(i) for i in range(page._variant_filter.count())] == [
        "All part numbers", "P1",
    ]
    assert {software for _, software, _ in page._rows} == {"0010", "0011"}
    assert page._progress_dialog._items.horizontalHeaderItem(0).text() == "Variant"
    assert all(page._progress_dialog._items.item(row, 0).text() == "P1" for row in range(2))
    assert all(page._variants_table.item(row, 4).text() == "Completed" for row in range(2))
    page._variant_filter.setCurrentIndex(1)
    assert len(visible_rows(page)) == 6
    assert all(page._table.item(row, 3).text() == "" for row in range(6))


def test_software_mismatch_still_fails_without_exposing_identity_in_error(qapp):
    page, _, _, _ = build_page(exports=[export_xml(target_parameters(software="9999"))])
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert page._variants_table.item(0, 4).text() == "Failed"
    error = page._variants_table.item(0, 5).text()
    assert "No Master Sheet" in error
    assert "9999" not in error and "SW Part Number" not in error
    assert page._table.rowCount() == 0


def test_filter_width_fits_longest_variant_and_search_absorbs_resize(qapp):
    part = "37820-6SA-T310-M6"
    page, _, _, _ = build_page(
        [variant(part)], [export_xml(target_parameters(part))],
    )
    page.resize(1100, 650)
    page.show()
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    page._progress_dialog._button.click()
    page._variant_filter.setCurrentIndex(1)
    qapp.processEvents()
    combo = page._variant_filter
    option = QStyleOptionComboBox()
    combo.initStyleOption(option)
    text_rect = combo.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField, combo)
    assert combo.currentText() == part
    assert text_rect.width() >= combo.fontMetrics().horizontalAdvance(part)
    assert 200 <= combo.width() <= 420
    assert combo.view().textElideMode() == Qt.ElideNone
    assert combo.view().minimumWidth() >= combo.fontMetrics().horizontalAdvance(part)
    variant_width, status_width = combo.width(), page._status_filter.width()
    search_width = page._search.width()
    assert status_width < 200
    page.resize(1400, 650)
    qapp.processEvents()
    assert combo.width() == variant_width
    assert page._status_filter.width() == status_width
    assert page._search.width() > search_width
    assert page._search.geometry().center().y() == page._deviations.geometry().center().y()
    page.resize(900, 650)
    qapp.processEvents()
    assert combo.width() == variant_width
    assert page._search.width() < search_width
    assert combo.currentText() == part


def test_variant_filter_sizes_from_longest_item_and_keeps_popup_uncapped(qapp):
    page, _, _, _ = build_page()
    combo = page._variant_filter
    combo.addItems(["Short", "37820-6SA-T310-M6-extended-configuration"])
    page._size_variant_filter()
    assert combo.minimumWidth() >= combo.fontMetrics().horizontalAdvance(combo.itemText(2))
    combo.addItem("Very long variant " * 20)
    page._size_variant_filter()
    assert combo.minimumWidth() == combo.maximumWidth() == 420
    assert combo.view().minimumWidth() > 420
    combo.clear()
    combo.addItem("All variants")
    page._size_variant_filter()
    assert combo.minimumWidth() == 200


@pytest.mark.parametrize("column", range(6))
def test_result_headers_use_home_filter_dialog_with_current_values(qapp, monkeypatch, column):
    page, _, _, _ = build_page()
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    page._progress_dialog._button.click()
    expected = sorted({
        page._table.item(row, column).text() for row in range(page._table.rowCount())
    }, key=str.casefold)
    selected = expected[0]
    dialog = Mock()
    dialog.exec.return_value = True
    dialog.result_filter.return_value = ColumnFilter(allowed=frozenset({selected}))
    constructor = Mock(return_value=dialog)
    monkeypatch.setattr(table_filter, "ColumnFilterDialog", constructor)
    header = page._table.horizontalHeader()
    assert header.contextMenuPolicy() == Qt.CustomContextMenu
    position = header.rect().topLeft()
    position.setX(header.sectionViewportPosition(column) + 2)
    header.customContextMenuRequested.emit(position)
    assert constructor.call_args.args[:3] == (
        ui._TARGET_HEADERS[column], expected, ColumnFilter(),
    )
    assert page._table.horizontalHeaderItem(column).text().endswith(" ▼")
    assert visible_rows(page) == [
        row for row in range(page._table.rowCount()) if page._table.item(row, column).text() == selected
    ]


def test_header_filters_combine_with_each_other_and_all_global_controls(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    page, _, _, _ = build_page(variants, [
        export_xml({**target_parameters(), "General/Power": "94", "General/XMLOnly": "ignored"}),
        export_xml(target_parameters("P2", "0011"), job_id="13"),
    ])
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    filters = page._header_filter
    assert "General/XMLOnly" not in filters.column_values(1)
    filters.set_column_filter(1, ColumnFilter(text="power"))
    assert len(visible_rows(page)) == 2
    filters.set_column_filter(4, ColumnFilter(allowed=frozenset({"94"})))
    assert len(visible_rows(page)) == 1
    page._search.setText("not present")
    assert not visible_rows(page)
    page._search.clear()
    page._variant_filter.setCurrentIndex(2)
    assert not visible_rows(page)
    page._variant_filter.setCurrentIndex(1)
    page._status_filter.setCurrentText(Status.MATCH.value)
    assert not visible_rows(page)
    page._status_filter.setCurrentText(Status.VALUE_MISMATCH.value)
    page._deviations.setChecked(True)
    assert len(visible_rows(page)) == 1
    assert "1 / 6 parameters shown" in page._summary.text()
    filters.set_column_filter(4, ColumnFilter(allowed=frozenset()))
    assert not visible_rows(page)
    filters.set_column_filter(4, ColumnFilter())
    assert len(visible_rows(page)) == 1
    page._status_filter.setCurrentText("All statuses")
    page._variant_filter.setCurrentIndex(0)
    page._deviations.setChecked(False)
    filters.reset()
    assert len(visible_rows(page)) == 6
    assert all(not page._table.horizontalHeaderItem(i).text().endswith(" ▼") for i in range(6))


def test_header_filters_reset_and_values_refresh_on_new_comparison(qapp):
    page, _, session, _ = build_page(exports=[
        export_xml({**target_parameters(), "General/Power": "94"}),
    ])
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    page._progress_dialog._button.click()
    page._header_filter.set_column_filter(4, ColumnFilter(allowed=frozenset({"94"})))
    assert len(visible_rows(page)) == 1
    session.export_job_xml.side_effect = [export_xml(target_parameters())]
    page._compare_btn.click()
    wait_done(page, qapp)
    assert not page._header_filter.is_active()
    assert len(visible_rows(page)) == 3
    assert "94" not in page._header_filter.column_values(4)
    assert "93" in page._header_filter.column_values(4)
    assert all(not page._table.horizontalHeaderItem(i).text().endswith(" ▼") for i in range(6))


@pytest.mark.parametrize("column", [2, 3])
def test_link_context_menu_copies_full_url_without_changing_selection(qapp, monkeypatch, column):
    page, _, _, _ = build_page()
    link = "https://webflow/app/ShowJob/123456"
    if column == 2:
        page.set_variants([variant(link=link)])
    else:
        page._variants_table.item(0, 3).setText(link)
    page.show()
    qapp.processEvents()
    table = page._variants_table
    table.setCurrentCell(0, 1)
    table.item(0, 0).setCheckState(Qt.Checked)
    selection = table.selectedIndexes()
    revision = page._revision
    rectangle = table.visualItemRect(table.item(0, column))
    menu = Mock()
    action = menu.addAction.return_value
    menu.exec.return_value = action
    monkeypatch.setattr(webflow_link_delegate, "QMenu", Mock(return_value=menu))
    QApplication.clipboard().setText("before")
    QTest.mouseClick(table.viewport(), Qt.RightButton, pos=rectangle.center())
    event = QContextMenuEvent(
        QContextMenuEvent.Mouse, rectangle.center(), table.viewport().mapToGlobal(rectangle.center()),
    )
    QApplication.sendEvent(table.viewport(), event)
    assert [entry.args[0] for entry in menu.addAction.call_args_list] == (
        ["Copy WebFlow Link"] if column == 2 else
        ["Copy WebFlow Link", "Edit WebFlow Link", "Clear WebFlow Link"]
    )
    assert QApplication.clipboard().text() == link
    assert table.selectedIndexes() == selection
    assert table.currentColumn() == 1
    assert page._selected_rows() == [0]
    assert page._revision == revision
    assert table.item(0, column).text() == "WF123456"
    assert table.item(0, column).toolTip() == "Double-click to open. Right-click for options"


def test_base_editor_uses_full_url_then_formats_and_exports_original_url(qapp):
    page, _, session, _ = build_page(exports=[
        export_xml(target_parameters()), export_xml(target_parameters(), job_id="99"),
    ])
    item = page._variants_table.item(0, 3)
    link = "https://webflow/app/ShowJob/99"
    item.setText(link)
    assert item.text() == "WF99"
    editor = QLineEdit()
    index = page._variants_table.model().index(0, 3)
    page._link_delegate.setEditorData(editor, index)
    assert editor.text() == link
    page._link_delegate.setModelData(editor, page._variants_table.model(), index)
    assert item.text() == "WF99" and item.data(Qt.UserRole) == link
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert session.export_job_xml.call_args_list == [
        call("https://webflow/app/ShowJob/12"), call(link),
    ]
    assert page._variants[0]["webflow_link"] == "https://webflow/app/ShowJob/12"


def test_invalid_base_remains_editable_and_clear_removes_internal_url(qapp):
    page, _, _, _ = build_page()
    item = page._variants_table.item(0, 3)
    item.setText("invalid")
    assert item.text() == item.data(Qt.UserRole) == "invalid"
    item.setText("https://webflow/app/ShowJob/99")
    assert item.text() == "WF99"
    item.setText("")
    assert item.data(Qt.UserRole) == "" and item.toolTip() == ""


@pytest.mark.parametrize("initial", ["", "https://webflow/app/ShowJob/99", "invalid"])
@pytest.mark.parametrize("action_name", ["Edit WebFlow Link", "Clear WebFlow Link"])
def test_base_menu_edit_and_clear_depend_on_editable_source(qapp, monkeypatch, initial, action_name):
    page, _, _, _ = build_page()
    table = page._variants_table
    item = table.item(0, 3)
    item.setText(initial)
    page.show()
    qapp.processEvents()
    actions = {}
    menu = Mock()

    def add_action(name):
        actions[name] = Mock()
        return actions[name]

    menu.addAction.side_effect = add_action
    menu.exec.side_effect = lambda _: actions[action_name]
    monkeypatch.setattr(webflow_link_delegate, "QMenu", Mock(return_value=menu))
    rectangle = table.visualItemRect(item)
    event = QContextMenuEvent(
        QContextMenuEvent.Mouse, rectangle.center(), table.viewport().mapToGlobal(rectangle.center()),
    )
    QApplication.sendEvent(table.viewport(), event)
    assert list(actions) == ["Copy WebFlow Link", "Edit WebFlow Link", "Clear WebFlow Link"]
    actions["Copy WebFlow Link"].setEnabled.assert_called_once_with(initial.startswith("https://"))
    assert page._variants[0]["webflow_link"] == "https://webflow/app/ShowJob/12"
    if action_name == "Clear WebFlow Link":
        assert item.text() == "" and item.data(Qt.UserRole) == ""
    else:
        editor = table.findChild(QLineEdit)
        assert editor is not None and editor.text() == initial
        editor.setText("https://webflow/app/ShowJob/100")
        QTest.keyClick(editor, Qt.Key_Return)
        qapp.processEvents()
        assert item.text() == "WF100"
        assert item.data(Qt.UserRole) == "https://webflow/app/ShowJob/100"


@pytest.mark.parametrize("column", [2, 3])
def test_link_single_click_selects_and_double_click_opens_without_editing(qapp, monkeypatch, column):
    page, _, _, _ = build_page()
    table = page._variants_table
    if column == 3:
        table.item(0, 3).setText("https://webflow/app/ShowJob/99")
    page.show()
    qapp.processEvents()
    item = table.item(0, column)
    link = item.data(Qt.UserRole)
    opened = Mock()
    monkeypatch.setattr(webflow_link_delegate.QDesktopServices, "openUrl", opened)
    position = table.visualItemRect(item).center()
    QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=position)
    opened.assert_not_called()
    assert table.currentColumn() == column
    QTest.mouseDClick(table.viewport(), Qt.LeftButton, pos=position)
    opened.assert_called_once()
    assert opened.call_args.args[0].toString() == link
    assert table.findChild(QLineEdit) is None
    assert item.data(Qt.UserRole) == link
    assert item.foreground().color() == QApplication.palette().link().color()


def test_empty_base_double_click_still_allows_full_url_input(qapp):
    page, _, _, _ = build_page()
    table = page._variants_table
    page.show()
    qapp.processEvents()
    item = table.item(0, 3)
    position = table.visualItemRect(item).center()
    QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=position)
    QTest.mouseDClick(table.viewport(), Qt.LeftButton, pos=position)
    editor = table.findChild(QLineEdit)
    assert editor is not None
    editor.setText("https://webflow/app/ShowJob/101")
    QTest.keyClick(editor, Qt.Key_Return)
    qapp.processEvents()
    assert item.text() == "WF101"
    assert item.data(Qt.UserRole) == "https://webflow/app/ShowJob/101"


def test_selection_table_fills_viewport_and_resizes_content_columns(qapp):
    page, _, _, _ = build_page([variant("37820-6SA-T310-M6")])
    page.resize(1100, 650)
    page.show()
    qapp.processEvents()
    table = page._variants_table
    header = table.horizontalHeader()
    assert header.defaultAlignment() == Qt.AlignCenter
    for width in (1100, 1400, 900):
        page.resize(width, 650)
        qapp.processEvents()
        assert header.length() == table.viewport().width()

        assert not table.horizontalScrollBar().isVisible()
        assert abs(table.columnWidth(3) - table.columnWidth(5)) <= 1
        for column in (0, 1, 2, 4):
            assert table.columnWidth(column) >= table.sizeHintForColumn(column)
    table.item(0, 4).setText("Exporting Target XML")
    qapp.processEvents()
    assert table.columnWidth(4) >= table.sizeHintForColumn(4)
    assert header.length() == table.viewport().width()
    page.set_variants([variant("Long variant " * 40)])
    QTest.qWait(20)
    assert header.length() > table.viewport().width()
    assert table.horizontalScrollBar().isVisible()
    page.set_variants([variant()])
    QTest.qWait(20)
    assert header.length() == table.viewport().width()
    assert not table.horizontalScrollBar().isVisible()


def test_selection_checkbox_is_centered_and_clickable(qapp):
    page, _, _, _ = build_page()
    page.show()
    qapp.processEvents()
    table = page._variants_table
    item = table.item(0, 0)
    index = table.model().index(0, 0)
    option = QStyleOptionViewItem()
    option.widget = table
    option.rect = table.visualItemRect(item)
    centered = page._check_delegate._centered_option(option, index)
    rect = table.style().subElementRect(QStyle.SE_ItemViewItemCheckIndicator, centered, table)
    assert abs(rect.center().x() - option.rect.center().x()) <= 1
    QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=rect.center())
    assert item.checkState() == Qt.Checked
    QTest.keyClick(table, Qt.Key_Space)
    assert item.checkState() == Qt.Unchecked


@pytest.mark.parametrize("column", [2, 3])
def test_comparison_links_reuse_home_pointer_cursor(qapp, column):
    page, _, _, _ = build_page()
    page._variants_table.item(0, 3).setText("https://webflow/app/ShowJob/99")
    page.show()
    qapp.processEvents()
    table = page._variants_table
    QTest.mouseMove(table.viewport(), table.visualItemRect(table.item(0, column)).center())
    qapp.processEvents()
    assert table.viewport().cursor().shape() == Qt.PointingHandCursor
    QTest.mouseMove(table.viewport(), table.visualItemRect(table.item(0, 1)).center())
    qapp.processEvents()
    assert table.viewport().cursor().shape() == Qt.ArrowCursor


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_progress_footer_buttons_stay_compact_and_bottom_right(qapp, theme):
    from autohub.modules.comparison.progress import ComparisonProgressDialog
    from autohub.ui.theme import apply_theme

    apply_theme(qapp, theme)
    dialog = ComparisonProgressDialog(["P1"])
    dialog.show()
    try:
        for finished in (False, True):
            if finished:
                dialog.update_status(0, "Completed", "")
                dialog.finish()
            for width in (640, 900):
                dialog.resize(width, 450)
                qapp.processEvents()
                button = dialog._button
                assert button.text() == ("Close" if finished else "Cancel")
                assert button.width() == button.sizeHint().width()
                assert button.width() < dialog.width() // 3
                assert dialog.width() - button.geometry().right() - 1 == 20
                assert dialog.height() - button.geometry().bottom() - 1 == 16
                assert dialog._summary.geometry().bottom() < button.geometry().top()
                assert not button.autoDefault()
                assert button.styleSheet() == ""
    finally:
        dialog.finish()
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_results_are_retained_and_exported_in_full(qapp, tmp_path):
    page, dialogs, session, _ = build_page()
    try:
        assert not page._export_btn.isEnabled()
        page._select_all()
        page._compare()
        wait_done(page, qapp)
        page._progress_dialog.close()
        total = page._table.rowCount()
        assert total and page._export_btn.isEnabled()

        page._select_all(); page._clear_selection(); page._select_all()
        page._search.setText("no-such-text")
        assert page._table.rowCount() == total and not visible_rows(page)
        assert page._export_btn.isEnabled()

        calls = session.export_job_xml.call_count
        dialogs.save_path = str(tmp_path / "out.html")
        page._export()
        assert session.export_job_xml.call_count == calls
        assert dialogs.saved[1].startswith("Comparison_Result_")
        html = open(dialogs.save_path, encoding="utf-8").read()
        assert "<title>Comparison Result</title>" in html and "Date:" in html and "Reviewed by:" in html
        assert html.count("<tr class=") == total
        assert "http://" not in html and "https://" not in html
        assert dialogs.saved[1].endswith(".html")

        page.set_variants([])
        assert not page._export_btn.isEnabled()
    finally:
        page.shutdown()
        page.close()
        page.deleteLater()


def test_update_master_impl_writes_only_completed_target_values_and_keeps_results(qapp):
    from autohub.core.impl_update import ImplOutcome

    class Updater:
        def __init__(self):
            self.calls = []

        def update(self, path, updates):
            from autohub.modules.comparison.impl_update import ImplRefresh
            self.calls.append((path, updates))
            refreshed = {**variant(), "comparison_result": "OK", "hardware": {
                **variant()["hardware"], "power": "95",
            }}
            return ImplRefresh({part: ImplOutcome(len(update.values)) for part, update in updates.items()}, [refreshed])

    updater = Updater()
    settings = Mock()
    settings.load.return_value = {"master_sheet_path": "master.xlsx"}
    session = Mock()
    session.open_dashboard_page.return_value = True
    session.export_job_xml.side_effect = [export_xml(target_parameters()), RuntimeError("boom")]
    dialogs = FakeDialogs()
    page = ui.ComparisonWidget(dialogs, ComparisonService(Mock(return_value=session)), settings, updater)
    reloads = []
    page.masterReloadRequested.connect(lambda: reloads.append(1))
    try:
        page.set_variants([variant(), variant("P2", link="https://webflow/app/ShowJob/2")])
        assert not page._impl_btn.isEnabled()
        page._select_all()
        page._compare()
        wait_done(page, qapp)
        page._progress_dialog.close()
        assert list(page._impl_updates) == ["P1"] and page._impl_btn.isEnabled()
        rows = len(page._rows)
        page._search.setText("power")
        page._set_status(0, Status.VALUE_MISMATCH)
        page._store_review(0, comment="keep review")
        reviews = dict(page._reviews)
        selected = page._selected_rows()
        page._update_impl()
        assert dialogs.confirmed and "P1" in dialogs.confirmed[0][1] and "P2" not in dialogs.confirmed[0][1]
        timer = QElapsedTimer(); timer.start()
        while page._running and timer.elapsed() < 5000:
            qapp.processEvents(); QTest.qWait(5)
        assert updater.calls[0][0] == "master.xlsx" and list(updater.calls[0][1]) == ["P1"]
        assert reloads == [] and dialogs.infos
        assert dialogs.infos[-1][1] == "Master Sheet updated successfully for 1 of 1 variant(s)."
        assert page._variants_table.item(0, 4).text() == "Completed"
        assert page._search.text() == "power" and page._reviews == reviews
        assert page._selected_rows() == selected
        assert next(row.master for _, _, row in page._rows if row.parameter == "General/Power") == "95"
        assert len(page._rows) == rows and page._impl_btn.isEnabled()
        page.set_variants([variant()])
        assert not page._rows and not page._impl_btn.isEnabled()
    finally:
        page.shutdown(); page.close(); page.deleteLater()


def _first_mismatch(page):
    return 0


@pytest.mark.parametrize("value, expected", [("OK", "Completed"), ("NG", "Pending"), ("", "Pending"), ("other", "Pending")])
def test_silent_impl_refresh_preserves_table_state(qapp, value, expected):
    from autohub.core.impl_update import ImplOutcome
    from autohub.modules.comparison.impl_update import ImplRefresh

    page, dialogs, session, _ = build_page()
    page._select_all()
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    page._variants_table.item(0, 3).setText("https://webflow/app/ShowJob/99")
    page._search.setText("power")
    page._variant_filter.setCurrentIndex(1)
    page._set_status(0, Status.VALUE_MISMATCH)
    page._store_review(0, comment="retained")
    page._table.selectRow(0)
    old_items = [page._table.item(0, col) for col in range(7)]
    reviews = dict(page._reviews)
    selected = page._selected_rows()
    page._finish_impl(ImplRefresh({"P1": ImplOutcome(1)}, [{**variant(), "comparison_result": value}]))
    assert page._variants_table.item(0, 4).text() == expected
    assert page._variants_table.item(0, 3).data(Qt.UserRole) == "https://webflow/app/ShowJob/99"
    assert page._selected_rows() == selected and page._reviews == reviews
    assert page._search.text() == "power" and page._variant_filter.currentIndex() == 1
    assert [page._table.item(0, col) for col in range(7)] == old_items
    assert session.export_job_xml.call_count == 1
    assert len(dialogs.infos) == 1 and not dialogs.errors


def test_silent_refresh_failure_shows_only_update_error_and_keeps_results(qapp):
    from autohub.core.impl_update import ImplOutcome
    from autohub.modules.comparison.impl_update import ImplRefresh

    page, dialogs, _, _ = build_page()
    page._select_all()
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    rows = list(page._rows)
    page._finish_impl(ImplRefresh({"P1": ImplOutcome(1)}, []))
    assert page._rows == rows
    assert not dialogs.infos and len(dialogs.errors) == 1
    assert dialogs.errors[0][0] == "Update Master Sheet"
    assert "refresh failed" in dialogs.errors[0][1]


def test_manual_status_and_comment_are_retained_exported_and_do_not_touch_master(qapp, tmp_path):
    page, dialogs, session, _ = build_page()
    try:
        page._select_all()
        page._compare()
        wait_done(page, qapp)
        page._progress_dialog.close()
        assert [page._table.horizontalHeaderItem(i).text() for i in range(7)][-2:] == ["Status", "Comment"]
        index = _first_mismatch(page)
        calculated = page._rows[index][2].status
        updates = dict(page._impl_updates)
        other = Status.VALUE_MISMATCH if calculated != Status.VALUE_MISMATCH else Status.MATCH

        menu = page._result_menu(index, 5)
        assert [a.text() for a in menu.actions()] == ["Change Status", "Reset Status", "", "Copy", "Copy Row"]
        assert not menu.actions()[1].isEnabled()
        page._set_status(index, other)
        item = page._table.item(index, 5)
        assert item.text() == other.value and item.toolTip() == f"Calculated: {calculated.value} | Manually changed"
        assert page._rows[index][2].status == calculated and page._impl_updates == updates
        assert page._result_menu(index, 5).actions()[1].isEnabled()

        page._table.item(index, 6).setText("checked with owner")
        assert page._comment(index) == "checked with owner"
        assert [a.text() for a in page._result_menu(index, 6).actions()] == [
            "Edit Comment", "Clear Comment", "", "Copy", "Copy Row",
        ]
        assert [a.text() for a in page._result_menu(index, 2).actions()] == ["Copy", "Copy Row"]

        page._search.setText("zzz"); page._search.setText("")
        page._status_filter.setCurrentText(other.value)
        assert index in visible_rows(page)
        page._status_filter.setCurrentIndex(0)
        page._render_results()
        assert page._table.item(index, 5).text() == other.value and page._table.item(index, 6).text() == "checked with owner"

        dialogs.save_path = str(tmp_path / "r.html")
        page._export()
        html = open(dialogs.save_path, encoding="utf-8").read()
        assert "<th>Comment</th>" in html and "checked with owner" in html
        assert f"Calculated: {calculated.value} | Manually changed" in html

        page._reset_status(index)
        page._set_comment(index, "")
        assert page._table.item(index, 5).text() == calculated.value and not page._reviews
        calls = session.export_job_xml.call_count
        assert calls == 1
    finally:
        page.shutdown(); page.close(); page.deleteLater()


def test_initial_status_comes_from_master_comparison_result(qapp):
    variants = [
        {**variant("P1"), "comparison_result": "OK"},
        {**variant("P2", "0011", "https://webflow/app/ShowJob/13"), "comparison_result": " ok "},
        {**variant("P3", "0012", "https://webflow/app/ShowJob/14"), "comparison_result": "NG"},
        {**variant("P4", "0013", "https://webflow/app/ShowJob/15"), "comparison_result": "other"},
        variant("P5", "0014", "https://webflow/app/ShowJob/16"),
    ]
    page, *_ = build_page(variants)
    assert [page._variants_table.item(row, 4).text() for row in range(5)] == [
        "Completed", "Completed", "Pending", "Pending", "Pending"]
    assert not page._rows and not page._impl_btn.isEnabled()


@pytest.fixture
def reviewed_page(qapp):
    page, dialogs, session, _ = build_page()
    page._select_all()
    page._compare()
    wait_done(page, qapp)
    page._progress_dialog.close()
    page.show()
    qapp.processEvents()
    yield page, dialogs, session
    page.shutdown()
    page.close()
    page.deleteLater()


def test_result_copy_cell_rectangle_and_row(reviewed_page):
    page, _, session = reviewed_page
    table = page._table
    table.item(0, 3).setText("(missing)")
    table.setCurrentCell(0, 3)
    QTest.keyClick(table, Qt.Key_C, Qt.ControlModifier)
    assert QApplication.clipboard().text() == "(missing)"
    table.clearSelection()
    table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 2), True)
    QTest.keyClick(table, Qt.Key_C, Qt.ControlModifier)
    assert QApplication.clipboard().text() == "\n".join(
        "\t".join(table.item(row, column).text() for column in range(3)) for row in range(2)
    )
    menu = page._result_menu(0, 2)
    next(action for action in menu.actions() if action.text() == "Copy Row").trigger()
    assert QApplication.clipboard().text() == "\t".join(table.item(0, column).text() for column in range(7))
    assert session.export_job_xml.call_count == 1


def test_result_comment_paste_cut_delete_persist_in_export(reviewed_page, tmp_path):
    page, dialogs, session = reviewed_page
    table = page._table
    original = list(page._rows)
    updates = dict(page._impl_updates)
    table.setCurrentCell(0, 6)
    QApplication.clipboard().setText("review first\nreview second")
    QTest.keyClick(table, Qt.Key_V, Qt.ControlModifier)
    assert [page._comment(i) for i in range(2)] == ["review first", "review second"]
    assert table.item(0, 6).toolTip() == "review first"
    page._search.setText("review")
    page._search.clear()
    page._render_results()
    assert table.item(1, 6).text() == "review second"
    dialogs.save_path = str(tmp_path / "edited.html")
    page._export()
    assert "review first" in (tmp_path / "edited.html").read_text()
    table.setCurrentCell(0, 6)
    QTest.keyClick(table, Qt.Key_X, Qt.ControlModifier)
    assert QApplication.clipboard().text() == "review first" and page._comment(0) == ""
    table.setCurrentCell(1, 6)
    QTest.keyClick(table, Qt.Key_Delete)
    assert page._comment(1) == ""
    assert page._rows == original and page._impl_updates == updates
    assert session.export_job_xml.call_count == 1


@pytest.mark.parametrize("column", range(5))
def test_paste_cut_delete_cannot_modify_readonly_values(reviewed_page, column):
    page, _, _ = reviewed_page
    table = page._table
    original = list(page._rows)
    value = table.item(0, column).text()
    table.setCurrentCell(0, column)
    QApplication.clipboard().setText("do not write")
    for key in (Qt.Key_V, Qt.Key_X, Qt.Key_Delete):
        QTest.keyClick(table, key, Qt.ControlModifier if key != Qt.Key_Delete else Qt.NoModifier)
    assert table.item(0, column).text() == value and page._rows == original


def test_paste_status_validates_entire_batch_before_editing(reviewed_page):
    page, dialogs, _ = reviewed_page
    table = page._table
    calculated = page._rows[0][2].status
    table.setCurrentCell(0, 5)
    QApplication.clipboard().setText("VALUE_MISMATCH\taccepted")
    QTest.keyClick(table, Qt.Key_V, Qt.ControlModifier)
    assert page._effective_status(0) == Status.VALUE_MISMATCH and page._comment(0) == "accepted"
    assert page._rows[0][2].status == calculated
    reviews = dict(page._reviews)
    for text in ("INVALID", "MATCHES_BASE", "MATCH\tchanged\nINVALID\talso changed"):
        QApplication.clipboard().setText(text)
        QTest.keyClick(table, Qt.Key_V, Qt.ControlModifier)
        assert page._reviews == reviews
    assert len(dialogs.errors) == 3


def test_comment_editor_uses_native_shortcuts_commit_and_escape(reviewed_page, qapp):
    page, _, _ = reviewed_page
    table = page._table
    table.setCurrentCell(0, 6)
    table.editItem(table.item(0, 6))
    editor = table.findChild(QLineEdit)
    assert editor is not None
    QApplication.clipboard().setText("normal editor paste")
    QTest.keyClick(editor, Qt.Key_V, Qt.ControlModifier)
    QTest.keyClick(editor, Qt.Key_Return)
    qapp.processEvents()
    assert page._comment(0) == "normal editor paste"
    table.editItem(table.item(0, 6))
    editor = next(editor for editor in table.findChildren(QLineEdit) if editor.isVisible())
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "save on focus loss")
    page._search.setFocus()
    qapp.processEvents()
    assert page._comment(0) == "save on focus loss"
    table.editItem(table.item(0, 6))
    editor = next(editor for editor in table.findChildren(QLineEdit) if editor.isVisible())
    editor.selectAll()
    QTest.keyClicks(editor, "cancel this")
    QTest.keyClick(editor, Qt.Key_Escape)
    qapp.processEvents()
    assert page._comment(0) == "save on focus loss"


def test_result_comment_width_and_single_line_display(reviewed_page, qapp):
    page, _, _ = reviewed_page
    page.resize(1500, 800)
    qapp.processEvents()
    table = page._table
    page._set_comment(0, "Long comment " * 100)
    assert table.columnWidth(6) >= 260
    assert table.columnWidth(6) >= table.columnWidth(2)
    assert not table.wordWrap()
    assert table.rowHeight(0) < 60
    assert table.item(0, 6).toolTip() == "Long comment " * 99 + "Long comment"
    page.resize(1800, 800)
    qapp.processEvents()
    assert table.horizontalHeader().length() <= table.viewport().width() + 1


def test_paste_skips_filtered_rows_and_stays_in_comment_column(reviewed_page):
    page, _, _ = reviewed_page
    table = page._table
    table.setRowHidden(1, True)
    table.setCurrentCell(0, 6)
    QApplication.clipboard().setText("first\nlast")
    QTest.keyClick(table, Qt.Key_V, Qt.ControlModifier)
    assert page._comment(0) == "first"
    assert page._comment(1) == ""
    assert page._comment(2) == "last"


def test_comment_edit_follows_model_index_after_row_sort(reviewed_page):
    page, _, _ = reviewed_page
    table = page._table
    table.sortItems(1, Qt.DescendingOrder)
    index = page._model_index(0)
    table.setCurrentCell(0, 6)
    QApplication.clipboard().setText("sorted review")
    QTest.keyClick(table, Qt.Key_V, Qt.ControlModifier)
    assert page._comment(index) == "sorted review"
    assert table.item(0, 6).text() == "sorted review"


def test_part_number_overlay_stays_fixed_and_shares_selection_filters(reviewed_page, qapp):
    page, _, _ = reviewed_page
    table = page._table
    view = table.frozen.view
    assert page._variants_table.horizontalHeaderItem(1).text() == "Part Number"
    assert table.horizontalHeaderItem(0).text() == "Part Number"
    assert view.model() is table.model() and view.selectionModel() is table.selectionModel()
    table.setColumnWidth(1, 1500)
    qapp.processEvents()
    x = view.geometry().x()
    table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
    qapp.processEvents()
    assert view.geometry().x() == x
    assert view.columnWidth(0) == table.columnWidth(0)
    view.selectionModel().setCurrentIndex(view.model().index(0, 0), QItemSelectionModel.ClearAndSelect)
    QTest.keyClick(view, Qt.Key_C, Qt.ControlModifier)
    assert QApplication.clipboard().text() == table.item(0, 0).text()
    page._search.setText("not-a-real-parameter")
    assert all(view.isRowHidden(row) and table.isRowHidden(row) for row in range(table.rowCount()))
    page._search.clear()
    assert not view.isRowHidden(0)
    table.setRowHeight(0, 40)
    assert view.rowHeight(0) == 40
