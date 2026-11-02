"""Batch Comparison UI, background exports, filters and existing cross-module wiring."""
from threading import Event
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, Qt
from PySide6.QtTest import QTest

from autohub.modules.comparison import ui
from autohub.modules.comparison.comparison import Status
from autohub.modules.comparison.service import ComparisonService
from autohub.modules.creation.ui import CreationWidget
from autohub.modules.home.ui import HomeWidget
from autohub.ui.main_window import MainWindow
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
    assert page._variants_table.item(0, 1).text() == "P1 | 0010"
    assert page._variants_table.item(1, 1).text() == "P2 | 0011"
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
    assert [page._table.horizontalHeaderItem(i).text() for i in range(6)] == list(ui._TARGET_HEADERS)
    assert page._table.rowCount() == 9
    assert all(page._variants_table.item(row, 2).text() == "Completed" for row in range(2))
    assert "2 completed; 0 failed" in page._summary.text()
    page._deviations.setChecked(True)
    assert len(visible_rows(page)) == 4
    page._search.setText("power")
    assert len(visible_rows(page)) == 1
    index = visible_rows(page)[0]
    assert page._table.item(index, 3).text() == "93"
    assert page._table.item(index, 4).text() == "94"
    assert page._table.item(index, 5).text() == Status.VALUE_MISMATCH
    page._search.clear()
    page._status_filter.setCurrentText(Status.MISSING_IN_MASTER.value)
    assert len(visible_rows(page)) == 3
    page._variant_filter.setCurrentIndex(2)
    assert len(visible_rows(page)) == 1
    assert page._table.item(visible_rows(page)[0], 0).text() == "P2"


def test_failed_variant_displays_error_and_does_not_hide_successful_results(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    page, dialogs, _, _ = build_page(variants, [
        b"<broken", export_xml(target_parameters("P2", "0011"), job_id="13"),
    ])
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert page._variants_table.item(0, 2).text() == "Failed"
    assert "Invalid WebFlow XML" in page._variants_table.item(0, 3).text()
    assert page._variants_table.item(1, 2).text() == "Completed"
    assert page._table.rowCount() == 4
    assert "1 completed; 1 failed" in page._summary.text()
    assert not dialogs.errors


def test_base_exports_automatically_once_and_keeps_variant_identity_in_results(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    page, _, session, _ = build_page(variants, [
        export_xml(target_parameters(), job_id="99"),
        export_xml(target_parameters()), export_xml(target_parameters("P2", "0011"), job_id="13"),
    ])
    page._base_link.setText("https://webflow/app/ShowJob/99")
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    assert session.export_job_xml.call_count == 3
    assert page._base_status.text() == "Base: Completed"
    assert [page._table.horizontalHeaderItem(i).text() for i in range(7)] == list(ui._BASE_HEADERS)
    assert any(row.status == Status.MATCHES_BOTH for _, _, row in page._rows)
    assert len({part for part, _, _ in page._rows}) == 2
    page._base_link.clear()
    assert not page._rows and page._table.columnCount() == 6


def test_invalid_base_link_reports_failed_status_for_each_selected_variant(qapp):
    page, _, session, _ = build_page()
    page._base_link.setText("invalid")
    page._select_all_btn.click()
    page._compare_btn.click()
    wait_done(page, qapp)
    session.export_job_xml.assert_not_called()
    assert page._variants_table.item(0, 2).text() == "Failed"
    assert "Base XML:" in page._variants_table.item(0, 3).text()
    assert page._base_status.text().startswith("Base: Failed")


def test_only_checked_variants_are_exported_and_saved_connection_is_used(qapp):
    variants = [variant(), variant("P2", "0011", "https://webflow/app/ShowJob/13")]
    settings = MemorySettings({"webflow_base_url": "https://webflow/app/dashboard"})
    page, _, session, factory = build_page(
        variants, [export_xml(target_parameters("P2", "0011"), job_id="13")], settings,
    )
    page._variants_table.item(1, 0).setCheckState(Qt.Checked)
    page._compare_btn.click()
    wait_done(page, qapp)
    session.export_job_xml.assert_called_once_with(variants[1]["webflow_link"])
    factory.assert_called_once_with(driver_path="", base_url="https://webflow/app/dashboard")


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
        assert page._variants_table.item(0, 2).text() == "Exporting XML"
        assert not page._compare_btn.isEnabled() and not page._base_link.isEnabled()
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
    assert page._variants_table.item(0, 1).text() == "P1 | 0099"
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
    assert page._table.rowCount() == 4


def test_unconfigured_service_reports_error_instead_of_manual_fallback(qapp):
    dialogs = FakeDialogs()
    page = ui.ComparisonWidget(dialogs)
    page.set_variants([variant()])
    page._select_all_btn.click()
    page._compare_btn.click()
    assert "not configured" in dialogs.errors[-1][1]
