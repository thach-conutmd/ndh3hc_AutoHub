"""Comparison page upload, filtering and existing cross-module capability wiring."""
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from autohub.modules.comparison import ui
from autohub.modules.comparison.comparison import Status
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
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def page_with_target(qapp, tmp_path, parameters=None):
    target = tmp_path / "target.xml"
    target.write_bytes(export_xml(parameters if parameters is not None else target_parameters()))
    dialogs = FakeDialogs(files=[str(target)])
    page = ui.ComparisonWidget(dialogs)
    page.set_variants([variant()])
    page._upload_target_btn.click()
    return page, dialogs


def visible_rows(page):
    return [index for index in range(page._table.rowCount()) if not page._table.isRowHidden(index)]


def test_comparison_lists_only_linked_variants_with_software_and_resets_on_reload(qapp):
    page = ui.ComparisonWidget(FakeDialogs())
    page.set_variants([variant(), variant("P2", "0011", ""), variant("P3", "", "invalid")])
    assert page._variant_selector.count() == 2
    assert page._variant_selector.itemText(0) == "P1 | 0010"
    assert "missing SW" in page._variant_selector.itemText(1)
    page.set_variants([])
    assert page._variant_selector.count() == 0
    assert not page._upload_target_btn.isEnabled()
    assert not page._compare_btn.isEnabled()
    assert page._table.rowCount() == 0


def test_target_upload_compare_search_status_and_deviations(qapp, tmp_path):
    parameters = {**target_parameters(), "General/Power": "94", "General/Model": "extra"}
    page, dialogs = page_with_target(qapp, tmp_path, parameters)
    assert dialogs.errors == []
    assert page._compare_btn.isEnabled()
    page._compare_btn.click()
    assert [page._table.horizontalHeaderItem(i).text() for i in range(6)] == list(ui._TARGET_HEADERS)
    assert page._table.rowCount() == 5
    page._deviations.setChecked(True)
    assert len(visible_rows(page)) == 3
    page._search.setText("power")
    assert len(visible_rows(page)) == 1
    index = visible_rows(page)[0]
    assert page._table.item(index, 3).text() == "93"
    assert page._table.item(index, 4).text() == "94"
    assert page._table.item(index, 5).text() == Status.VALUE_MISMATCH
    page._search.clear()
    page._status_filter.setCurrentText(Status.MISSING_IN_MASTER.value)
    assert len(visible_rows(page)) == 2
    assert "2 / 5" in page._summary.text()


@pytest.mark.parametrize("failure", ["syntax", "other_variant", "other_sw", "other_job", "invalid_link", "missing_sw"])
def test_bad_target_upload_reports_error_and_clears_previous_results(qapp, tmp_path, failure):
    page, dialogs = page_with_target(qapp, tmp_path)
    page._compare_btn.click()
    assert page._table.rowCount()
    parameters = target_parameters()
    job = "12"
    if failure == "other_variant":
        parameters = target_parameters("P2")
    elif failure == "other_sw":
        parameters = target_parameters(software="0011")
    elif failure == "other_job":
        job = "99"
    elif failure == "invalid_link":
        page.set_webflow_links({"P1": "invalid"})
    elif failure == "missing_sw":
        page.set_webflow_numbers({"P1": {"AX": ""}})
    path = tmp_path / "invalid.xml"
    path.write_bytes(b"<broken" if failure == "syntax" else export_xml(parameters, job_id=job))
    dialogs.files.append(str(path))
    page._upload_target_btn.click()
    assert dialogs.errors
    assert page._target is None
    assert page._table.rowCount() == 0
    assert not page._compare_btn.isEnabled()


def test_upload_requires_selected_pair_not_another_valid_master_variant(qapp, tmp_path):
    path = tmp_path / "other.xml"
    path.write_bytes(export_xml(target_parameters("P2")))
    dialogs = FakeDialogs(files=[str(path)])
    page = ui.ComparisonWidget(dialogs)
    page.set_variants([variant(), variant("P2")])
    page._upload_target_btn.click()
    assert "selected Variant + SW Part Number" in dialogs.errors[-1][1]
    assert page._target is None


def test_three_way_comparison_requires_base_export_and_clears_when_link_changes(qapp, tmp_path):
    page, dialogs = page_with_target(qapp, tmp_path)
    page._base_link.setText("https://webflow/app/ShowJob/13")
    assert not page._compare_btn.isEnabled()
    path = tmp_path / "base.xml"
    path.write_bytes(export_xml({**target_parameters(), "General/Power": "94"}, job_id="13"))
    dialogs.files.append(str(path))
    page._upload_base_btn.click()
    assert page._compare_btn.isEnabled()
    page._compare_btn.click()
    assert dialogs.errors == []
    assert [page._table.horizontalHeaderItem(i).text() for i in range(5)] == list(ui._BASE_HEADERS)
    power = next(row for row in page._rows if row.parameter == "General/Power")
    assert power.status == Status.MATCHES_MASTER
    assert any(row.status == Status.MATCHES_BOTH for row in page._rows)
    page._base_link.setText("https://webflow/app/ShowJob/14")
    assert page._base is None and not page._compare_btn.isEnabled()
    assert page._table.rowCount() == 0
    page._base_link.clear()
    assert page._compare_btn.isEnabled()
    page._compare_btn.click()
    assert page._table.columnCount() == 6


@pytest.mark.parametrize("link,job", [("invalid", "13"), ("https://webflow/app/ShowJob/13", "99")])
def test_base_link_and_xml_must_be_valid_and_correspond(qapp, tmp_path, link, job):
    page, dialogs = page_with_target(qapp, tmp_path)
    page._base_link.setText(link)
    path = tmp_path / "base.xml"
    path.write_bytes(export_xml(target_parameters(), job_id=job))
    dialogs.files.append(str(path))
    page._upload_base_btn.click()
    assert dialogs.errors and page._base is None
    assert not page._compare_btn.isEnabled()


def test_variant_change_clears_target_and_results(qapp, tmp_path):
    page, _ = page_with_target(qapp, tmp_path)
    page.set_variants([variant(), variant("P2")])
    page._target = target_parameters()
    page._compare()
    page._variant_selector.setCurrentIndex(1)
    assert page._target is None and not page._rows
    assert not page._compare_btn.isEnabled()


def test_cancel_upload_preserves_valid_source_and_missing_file_reports_error(qapp, tmp_path):
    page, dialogs = page_with_target(qapp, tmp_path)
    old_target = page._target
    page._upload_target_btn.click()
    assert page._target is old_target
    dialogs.files.append(str(tmp_path / "missing.xml"))
    page._upload_target_btn.click()
    assert page._target is None and dialogs.errors


def test_open_webflow_uses_validated_job_links_and_surfaces_browser_failures(qapp, monkeypatch):
    dialogs = FakeDialogs()
    page = ui.ComparisonWidget(dialogs)
    page.set_variants([variant()])
    opened = Mock(return_value=True)
    monkeypatch.setattr(ui.QDesktopServices, "openUrl", opened)
    page._open_target_btn.click()
    assert opened.call_args.args[0].toString() == variant()["webflow_link"]
    opened.return_value = False
    page._open_target_btn.click()
    assert "Could not open" in dialogs.errors[-1][1]
    opened.reset_mock()
    page._base_link.setText("not a link")
    page._open_base_btn.click()
    opened.assert_not_called()
    assert "valid WebFlow" in dialogs.errors[-1][1]


def test_existing_home_and_creation_signals_feed_comparison_without_shared_mutation(qapp):
    settings = MemorySettings()
    home = HomeWidget(Mock(), settings)
    creation = CreationWidget(Mock(), settings)
    page = ui.ComparisonWidget(FakeDialogs())
    MainWindow._wire_cross_module_signals([home, creation, page])
    source = variant(link="")
    home.variantsLoaded.emit([source])
    assert page._variant_selector.count() == 0
    creation.webflowLinksUpdated.emit({"P1": "https://webflow/app/ShowJob/12"})
    creation.webflowNumbersUpdated.emit({"P1": {"AX": "0099", "AW": "ECR"}}, True)
    assert page._variant_selector.count() == 1
    assert page._variant_selector.currentText() == "P1 | 0099"
    assert page._selected()["hardware"]["ecr_number"] == "ECR"
    assert source["hardware"]["software_part_number"] == "0010"
    home.variantsLoaded.emit([variant("other", link="")])
    assert page._variant_selector.count() == 0 and not page._rows


def test_comparison_supports_theme_changes_with_results(qapp, tmp_path):
    from autohub.ui.theme import apply_theme

    page, _ = page_with_target(qapp, tmp_path)
    page._compare_btn.click()
    apply_theme(qapp, "light")
    apply_theme(qapp, "dark")
    assert page._table.rowCount() == 4
