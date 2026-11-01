from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QLabel

from autohub.modules.creation.variant_checklist import VariantChecklist
from autohub.services.MasterSheet.webflow_variants import webflow_variant_from_row


def test_selection_buttons_follow_checkbox_changes(qapp):
    checklist = VariantChecklist()
    assert not checklist._clear_selection_btn.isEnabled()
    assert not checklist._select_visible_btn.isEnabled()
    checklist.set_variants([
        {"part_number": "P", "ecu_type": "MG1", "event": "A"},
        {"part_number": "Q", "ecu_type": "MG1", "event": "A"},
    ])
    assert not checklist._clear_selection_btn.isEnabled()
    assert checklist._select_visible_btn.isEnabled()
    checklist._checkboxes["P"].click()
    assert checklist._clear_selection_btn.isEnabled()
    assert checklist._select_visible_btn.isEnabled()
    checklist._checkboxes["Q"].click()
    assert not checklist._select_visible_btn.isEnabled()
    checklist._clear_selection_btn.click()
    assert checklist.selected_variants() == []
    assert not any(checkbox.isChecked() for checkbox in checklist._checkboxes.values())
    assert not checklist._clear_selection_btn.isEnabled()
    assert checklist._select_visible_btn.isEnabled()
    checklist._select_visible_btn.click()
    assert len(checklist.selected_variants()) == 2
    assert checklist._clear_selection_btn.isEnabled()
    assert not checklist._select_visible_btn.isEnabled()


def test_event_filter_keeps_projects_with_the_same_event_separate(qapp):
    checklist = VariantChecklist()
    checklist.set_variants([
        webflow_variant_from_row("P", {"H": "62XS - HIN Lot / MP1"}),
        webflow_variant_from_row("Q", {"H": "6WZX for HIN/MP1 event"}),
        webflow_variant_from_row("R", {"H": "62XS for HIN/MP2 event"}),
    ])
    assert [checklist._event_filter.itemText(i) for i in range(checklist._event_filter.count())] == [
        "All events", "62XS - HIN", "6WZX - HIN",
    ]
    assert checklist._event_filter.currentText() == "62XS - HIN"
    assert set(checklist._checkboxes) == {"P", "R"}
    checklist._event_filter.setCurrentText("62XS - HIN")
    assert set(checklist._checkboxes) == {"P", "R"}
    checklist._event_filter.setCurrentText("6WZX - HIN")
    assert set(checklist._checkboxes) == {"Q"}


def test_creation_headers_and_ecu_values(qapp):
    checklist = VariantChecklist()
    checklist.set_variants([{
        "part_number": "P", "ecu_type": "MG1CS022",
        "ecu": {"family_name": "MG1CS022", "project_version": "6WZX", "program_version": "V037"},
    }])
    table = checklist._table
    assert [table.horizontalHeaderItem(col).text() for col in range(8)] == [
        "Select", "Part Number", "Family Name", "FSWID Project Version", "FSWID Program Version", "WebFlow Link",
        "SW Part Number", "ECR Number",
    ]
    assert [table.item(0, col).text() for col in range(1, 5)] == [
        "P", "MG1CS022", "6WZX", "V037",
    ]
    assert table.showGrid()
    assert checklist._checkboxes["P"].text() == ""
    assert not any(label.text().startswith("Variants (") for label in checklist.findChildren(QLabel))
    checklist._checkboxes["P"].setChecked(True)
    checklist.set_links({"P": "https://webflow/app/ShowJob/42"})
    assert checklist._checkboxes["P"].isChecked()
    assert table.cellWidget(0, 5).text() == "WF42"
    assert table.item(0, 3).text() == "6WZX"
    checklist.set_numbers({"P": {"AX": "10SW001", "AW": "ECR123"}})
    assert [table.item(0, col).text() for col in (6, 7)] == ["10SW001", "ECR123"]
    checklist._apply_filter()
    assert table.item(0, 6).text() == "10SW001"


def test_missing_ecu_values_and_event_filter(qapp):
    checklist = VariantChecklist()
    checklist.set_variants([
        {"part_number": "P", "ecu_type": "MG1", "event": "A"},
        {"part_number": "Q", "ecu_type": "MG2", "event": "B"},
    ])
    checklist._event_filter.setCurrentText("A")
    table = checklist._table
    assert set(checklist._checkboxes) == {"P"}
    assert table.item(0, 2).text() == "MG1"
    assert table.item(0, 3).text() == ""
    assert table.item(0, 4).text() == ""
    checklist.set_variants([])
    assert table.horizontalHeaderItem(0).text() == "Select"
    assert table.rowCount() == 0
    assert checklist._empty_label in checklist.findChildren(QLabel)


def test_event_is_left_aligned_and_columns_fit_individual_content(qapp):
    checklist = VariantChecklist()
    checklist.set_variants([{
        "part_number": "37820-6WZ-M610-M6", "ecu_type": "MG1CS022",
        "webflow_link": "https://webflow/app/ShowJob/16413",
        "ecu": {"project_version": "6WZX", "program_version": "V037"},
    }])
    checklist.resize(950, 300)
    checklist.show()
    qapp.processEvents()
    toolbar = checklist.layout().itemAt(0).layout()
    assert toolbar.itemAt(0).widget().text() == "Event:"
    assert toolbar.itemAt(1).widget() is checklist._event_filter
    header = checklist._table.horizontalHeader()
    assert not header.stretchLastSection()
    for width in (600, 800, 950, 1100):
        checklist.resize(width, 300)
        qapp.processEvents()
        table = checklist._table
        assert sum(table.columnWidth(col) for col in range(table.columnCount())) == table.viewport().width()
        assert table.columnWidth(1) > max(table.columnWidth(col) for col in range(table.columnCount()) if col != 1)
        assert table.horizontalScrollBar().maximum() == 0
        assert table.columnWidth(5) < table.columnWidth(3)
        assert table.columnWidth(5) >= table.cellWidget(0, 5).sizeHint().width()
        assert all(table.item(0, col).textAlignment() == Qt.AlignCenter for col in range(1, 5))
        assert table.cellWidget(0, 5).alignment() == Qt.AlignCenter
    checklist.close()


def test_columns_resize_after_import_and_filter_changes(qapp):
    checklist = VariantChecklist()
    checklist.set_variants([
        {"part_number": "P", "ecu_type": "MG1", "event": "A"},
        {"part_number": "Q", "ecu_type": "MG1", "event": "B"},
    ])
    checklist.resize(1400, 300)
    checklist.show()
    checklist._event_filter.setCurrentText("A")
    qapp.processEvents()
    table = checklist._table
    initial = table.columnWidth(7)
    number = "ECR-" + "1234567890" * 4
    checklist.set_numbers({"P": {"AW": number}})
    checklist.set_links({"P": "https://webflow/app/ShowJob/123456789012345"})
    qapp.processEvents()
    assert table.columnWidth(7) > initial
    assert table.columnWidth(7) >= table.fontMetrics().horizontalAdvance(number)
    assert table.columnWidth(5) >= table.cellWidget(0, 5).sizeHint().width()
    checklist._event_filter.setCurrentText("B")
    qapp.processEvents()
    assert table.columnWidth(7) == initial
    checklist.close()
