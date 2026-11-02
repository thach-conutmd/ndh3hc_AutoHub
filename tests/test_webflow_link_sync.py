from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from autohub.core.variant_schema import VARIANT_FIELD_ORDER
from autohub.core.settings_keys import WEBFLOW_GENERAL_OPTIONS_KEY
from autohub.modules.home import variant_table as table_module
from autohub.modules.creation.ui import CreationWidget
from autohub.modules.home.ui import HomeWidget
from autohub.ui.main_window import MainWindow
from tests.fakes import MemorySettings


@pytest.mark.parametrize("fresh_link", ["", None, "https://webflow/app/ShowJob/221486"])
def test_home_reload_replaces_creation_data_including_blank_links(qapp, fresh_link):
    settings = MemorySettings()
    home = HomeWidget(Mock(), settings)
    creation = CreationWidget(Mock(), settings)
    MainWindow._wire_cross_module_signals([home, creation])
    creation.set_variants([{
        "part_number": "P", "ecu_type": "MG1", "webflow_link": "https://webflow/app/ShowJob/16472",
        "ecu": {"family_name": "old"}, "hardware": {"software_part_number": "old SW"},
    }])
    creation._checklist.set_links({"P": "https://webflow/app/ShowJob/16473"})
    creation._checklist._checkboxes["P"].setChecked(True)
    row = {"_row": 11, "J": "P", "_webflow_link": fresh_link or ""}
    variant = {
        "part_number": "P", "ecu_type": "MG1", "ecu": {"family_name": "new"},
        "hardware": {"software_part_number": "", "ecr_number": "new ECR"},
    }
    if fresh_link is not None:
        variant["webflow_link"] = fresh_link

    home._presenter._apply_load(([row], [variant]), keep_rows=False)

    checklist = creation._checklist
    table = checklist._table
    assert checklist.has_link("P") is bool(fresh_link)
    assert checklist.selected_variants() == []
    assert table.item(0, 2).text() == "new"
    assert table.item(0, 6).text() == ""
    assert table.item(0, 7).text() == "new ECR"
    if fresh_link:
        assert table.cellWidget(0, 5).text() == "WF221486"
    else:
        assert table.cellWidget(0, 5) is None
    assert home.read_rows()[0].get("_webflow_link", "") == (fresh_link or "")


def test_clearing_creation_variants_removes_links_from_the_previous_sheet(qapp):
    creation = CreationWidget(Mock(), MemorySettings())
    creation.set_variants([{
        "part_number": "P", "ecu_type": "MG1", "webflow_link": "https://webflow/app/ShowJob/16472",
    }])

    creation.set_variants([])

    assert not creation._checklist.has_link("P")
    creation.set_variants([{"part_number": "P", "ecu_type": "MG1"}])
    assert creation._checklist._table.cellWidget(0, 5) is None
    creation._checklist._checkboxes["P"].setChecked(True)
    assert creation._without_declined_duplicates(creation._checklist.selected_variants())


def test_created_link_updates_creation_payload_as_well_as_its_display(qapp):
    creation = CreationWidget(Mock(), MemorySettings())
    creation.set_variants([{"part_number": "P", "ecu_type": "MG1"}])
    checklist = creation._checklist
    checklist.set_links({"P": "https://webflow/app/ShowJob/42"})
    checklist._checkboxes["P"].setChecked(True)

    assert checklist.selected_variants()[0]["webflow_link"] == "https://webflow/app/ShowJob/42"
    assert checklist._table.cellWidget(0, 5).text() == "WF42"


def test_created_links_reach_home_without_discarding_edits(qapp):
    settings = MemorySettings({"show_webflow_link": True})
    home = HomeWidget(Mock(), settings)
    creation = CreationWidget(Mock(last_elapsed_seconds=0.0), settings)
    MainWindow._wire_cross_module_signals([home, creation])
    rows = [
        {"_row": 11, "J": "P", "H": "edited", "_webflow_link": "https://webflow/app/ShowJob/1"},
        {"_row": 12, "J": "OTHER", "_webflow_link": "https://webflow/app/ShowJob/2"},
    ]
    home.show_rows(rows)
    home._presenter._loaded_rows = [dict(row) for row in rows]
    home._presenter.on_table_edited()
    home._presenter._deleted_rows = [13]
    home._variant_table.setRowHidden(0, True)
    edits = []
    home._variant_table.userEdited.connect(lambda: edits.append(True))
    link = "https://webflow/app/ShowJob/16409"

    creation._finish_webflow_jobs(
        [{"PartNumber": "P", "JobId": "16409", "Url": link, "LinkError": "Workbook locked"}],
        Mock(),
    )

    table = home._variant_table
    item = table.item(0, table._link_column)
    assert item.text() == "WF16409"
    assert item.data(Qt.UserRole) == link
    assert not item.flags() & Qt.ItemIsEditable
    assert table.isRowHidden(0)
    assert table.item(0, 1 + VARIANT_FIELD_ORDER.index("H")).text() == "edited"
    assert table.read()[0]["_webflow_link"] == link
    assert table.read()[1]["_webflow_link"].endswith("/2")
    assert home._presenter._loaded_rows[0]["_webflow_link"] == link
    assert home._presenter._deleted_rows == [13]
    assert home._update_btn.isEnabled()
    assert not edits
    home._presenter._show_rows(home._presenter._loaded_rows)
    assert table.item(0, table._link_column).text() == "WF16409"


@pytest.mark.parametrize("persisted", [True, False])
def test_allocated_numbers_sync_creation_home_and_preserve_other_edits(qapp, persisted):
    settings = MemorySettings()
    home = HomeWidget(Mock(), settings)
    creation = CreationWidget(Mock(last_elapsed_seconds=0.0), settings)
    MainWindow._wire_cross_module_signals([home, creation])
    rows = [{"_row": 11, "J": "P", "AX": "old SW", "AW": "old ECR", "H": "event"}]
    home._presenter._show_rows(rows)
    home._presenter._loaded_rows = [dict(row) for row in rows]
    creation.set_variants([{"part_number": "P", "ecu_type": "MG1", "hardware": {"software_part_number": "old SW"}}])
    results = [{"PartNumber": "P", "JobId": "42", "SoftwarePartNumber": "0010", "ECRNumber": "ECR42"}]
    if not persisted:
        results[0]["NumberError"] = "Workbook locked"
    window = Mock()
    creation._finish_webflow_jobs(results, window)
    assert home.read_rows()[0]["AX"] == "0010"
    assert home.read_rows()[0]["AW"] == "ECR42"
    assert home.read_rows()[0]["H"] == "event"
    assert home._presenter._loaded_rows[0]["AX"] == "0010"
    assert creation._checklist._table.item(0, 6).text() == "0010"
    assert creation._checklist._table.item(0, 7).text() == "ECR42"
    assert home._update_btn.isEnabled() is (not persisted)
    if not persisted:
        assert "Workbook locked" in window.succeed.call_args.args[0]


def test_number_updates_preserve_unrelated_edits_and_deletions(qapp):
    home = HomeWidget(Mock(), MemorySettings())
    home._presenter._show_rows([{"_row": 11, "J": "P", "H": "original"}])
    table = home._variant_table
    table.item(0, 1 + VARIANT_FIELD_ORDER.index("H")).setText("edited")
    home._presenter._deleted_rows = [14]
    table.setRowHidden(0, True)
    home.set_webflow_numbers({"P": {"AX": "00123", "AW": "ECR42"}})
    assert home.read_rows()[0]["H"] == "edited"
    assert home._presenter._original_rows[11]["H"] == "original"
    assert home._presenter._original_rows[11]["AX"] == "00123"
    assert home._presenter._deleted_rows == [14]
    assert table.isRowHidden(0)
    assert home._update_btn.isEnabled()


def test_link_updates_preserve_hidden_column_and_ignore_unknown_parts(qapp):
    home = HomeWidget(Mock(), MemorySettings())
    home.show_rows([{"J": "P"}])
    home.set_webflow_links({"P": "https://webflow/app/ShowJob/3", "UNKNOWN": "unused"})

    table = home._variant_table
    assert table.rowCount() == 1
    assert table.isColumnHidden(table._link_column)
    assert table.item(0, table._link_column).text() == "WF3"
    assert not home._update_btn.isEnabled()


def test_general_options_are_cached_and_reach_home(qapp):
    settings = MemorySettings({WEBFLOW_GENERAL_OPTIONS_KEY: {"market": ["Brazil"]}})
    home = HomeWidget(Mock(), settings)
    creation = CreationWidget(
        Mock(last_elapsed_seconds=0.0, last_general_options={"market": ["Brazil", "Japan"]}),
        settings,
    )
    MainWindow._wire_cross_module_signals([home, creation])

    creation._finish_webflow_jobs([], Mock())

    assert settings.load()[WEBFLOW_GENERAL_OPTIONS_KEY] == {"market": ["Brazil", "Japan"]}
    column = VARIANT_FIELD_ORDER.index("AJ") + 1
    assert home._variant_table.itemDelegateForColumn(column)._choices == ("Brazil", "Japan")
    restarted_home = HomeWidget(Mock(), settings)
    assert restarted_home._variant_table.itemDelegateForColumn(column)._choices == ("Brazil", "Japan")


def test_home_resolves_data_version_to_the_selected_calibration_file(qapp, tmp_path):
    from autohub.core.settings_keys import CALIBRATION_FOLDER_PATH_KEY

    calibration = tmp_path / "calibration-v3.hex"
    calibration.write_text(":00000001FF\n", encoding="ascii")
    home = HomeWidget(Mock(), MemorySettings({CALIBRATION_FOLDER_PATH_KEY: str(tmp_path)}))
    published = []
    home.variantsLoaded.connect(published.append)
    variants = [
        {"part_number": "P1", "hardware": {"data_version": calibration.name}},
        {"part_number": "P2", "hardware": {"data_version": "not-a-hex-file"}},
    ]

    home.publish_variants(variants)

    assert published[0][0]["_calibration_hex_path"] == str(calibration)
    assert "_calibration_hex_path" not in published[0][1]


@pytest.mark.parametrize("frozen", [False, True])
def test_job_link_opens_only_on_double_click(qapp, monkeypatch, frozen):
    table = table_module.VariantTable()
    link = "https://webflow/app/ShowJob/16409"
    table.populate([{"J": "P", "_webflow_link": link}])
    table.set_webflow_link_visible(True)
    table.resize(800, 300)
    table.show()
    qapp.processEvents()
    view = table._frozen.view if frozen else table
    if not frozen:
        table._frozen.view.hide()
    opened = Mock()
    monkeypatch.setattr(table_module.QDesktopServices, "openUrl", opened)
    index = table.model().index(0, table._link_column)
    position = view.visualRect(index).center()

    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=position)
    opened.assert_not_called()
    QTest.mouseDClick(view.viewport(), Qt.LeftButton, pos=position)
    opened.assert_called_once()
    assert opened.call_args.args[0].toString() == link
    table.close()
