from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from selenium.common.exceptions import TimeoutException

from autohub.core.webflow_fields import HARDWARE_FIELDS
from autohub.modules.creation import service as creation_service
from autohub.modules.creation.service import WebFlowConfig, WebFlowJobService
from autohub.services.MasterSheet.webflow_variants import WEBFLOW_SOURCE_COLUMNS, webflow_variant_from_row
from autohub.services.WebFlow import HardwareFields as hardware_module
from autohub.services.WebFlow.HardwareFields import HardwareFields
from autohub.services.WebFlow.WebFlow import WebFlow
from tests.fakes import FakeWebFlow


@pytest.mark.parametrize("column,key,label,kind", HARDWARE_FIELDS)
def test_every_hardware_field_reads_its_sheet_column(column, key, label, kind):
    assert column in WEBFLOW_SOURCE_COLUMNS
    variant = webflow_variant_from_row("PN", {column: "sheet value"})
    assert variant["hardware"][key] == "sheet value"


@pytest.mark.parametrize("value,expected", [(True, True), (False, False), (1.0, True), (0.0, False),
                                            ("YES", True), ("No", False), ("X", True), ("", False), (None, False)])
def test_checkbox_sheet_values(value, expected):
    assert webflow_variant_from_row("PN", {"X": value})["general"]["safety_monitoring"] is expected


def test_invalid_checkbox_is_not_silently_replaced():
    with pytest.raises(ValueError, match="PN.*column X"):
        webflow_variant_from_row("PN", {"X": "unexpected"})


def test_blank_cells_stay_empty_except_checkboxes_default_to_false():
    variant = webflow_variant_from_row("PN", {})
    assert not variant["ecu_generation"] and not variant["brand"] and not variant["ecu_type"]
    assert all(variant["general"][key] is False for key in (
        "safety_monitoring", "safety_calibration", "calibration", "data_integration",
    ))
    assert all(variant["general"][key] == "" for key in (
        "delivery_type", "release_class", "release_scope", "limitations",
    ))
    assert all(value == "" for value in variant["ecu"].values())
    assert all(value == "" for value in variant["customer"].values())


@pytest.mark.parametrize("missing", ["ecu_generation", "brand", "ecu_type"])
def test_required_creation_fields_are_rejected_before_submission(missing):
    session = Mock()
    variant = {"part_number": "PN", "ecu_generation": "MG1", "brand": "Honda", "ecu_type": "MG1CS022"}
    variant[missing] = ""
    with pytest.raises(ValueError, match=f"PN.*{missing}"):
        WebFlow.create_and_fill_jobs(session, [variant], "tool", "routing")
    session.open_dashboard_page.assert_not_called()


def test_mixed_creation_values_are_rejected():
    session = Mock()
    variant = {"part_number": "PN", "ecu_generation": "MG1", "brand": "Honda", "ecu_type": "MG1CS022"}
    with pytest.raises(ValueError, match="same Master Sheet"):
        WebFlow.create_and_fill_jobs(session, [variant, {**variant, "brand": "Other brand"}], "tool", "routing")


def test_brand_and_ecu_type_are_taken_from_sheet_not_method_defaults():
    session = Mock()
    session.body.job_creation.jobs_creation.return_value = True
    session.body.job_creation.get_new_jobs_ids.return_value = ["1"]
    session._fill_job.return_value = []
    variant = webflow_variant_from_row("PN", {"Q": "MED17", "R": "Sheet brand", "S": "MED17.9"})
    WebFlow.create_and_fill_jobs(session, [variant], "tool", "routing")
    args = session.body.job_creation.jobs_creation.call_args.kwargs
    assert args["ecu_generation"] == "MED17" and args["ecu_type"] == "MED17.9"
    assert args["brand"] == "Sheet brand"


def test_job_results_retain_each_variants_allocated_number():
    session = Mock()
    session.body.job_creation.get_new_jobs_ids.return_value = ["1", "2"]
    variants = [
        webflow_variant_from_row(part_number, {"Q": "MG1", "R": "Honda", "S": "MG1CS022"})
        for part_number in ("PN1", "PN2")
    ]
    numbers = {"PN1": "10SW072930", "PN2": "10SW072931"}

    def fill_job(variant):
        variant["imported_software_part_number"] = numbers[variant["part_number"]]
        variant["imported_ecr_number"] = f"ECR-{variant['part_number']}"
        return []

    session._fill_job.side_effect = fill_job
    results = WebFlow.create_and_fill_jobs(session, variants, "tool", "routing")
    assert [(item["PartNumber"], item["JobId"], item["SoftwarePartNumber"]) for item in results] == [
        ("PN1", "1", "10SW072930"), ("PN2", "2", "10SW072931"),
    ]
    assert [item["ECRNumber"] for item in results] == ["ECR-PN1", "ECR-PN2"]


def test_ecr_settings_are_loaded_and_editable(qapp, monkeypatch):
    from autohub.modules.settings.creation_form import load_config, CreationSettingsForm as WebFlowSettingsDialog
    from tests.fakes import MemorySettings

    monkeypatch.delenv("USERNAME", raising=False)
    monkeypatch.delenv("USERDNSDOMAIN", raising=False)
    values = {
        "change_engineer": "Configured engineer",
        "cost_allocation": "Configured allocation",
        "change_reason": "Customer requirement (Target: Customer covers costs)",
    }
    config = load_config(MemorySettings({**values, "ecr_notes": "Old saved notes"}))
    dialog = WebFlowSettingsDialog(config)
    assert dialog.values() == {**dialog.values(), **values}
    assert "ecr_notes" not in dialog.values()
    assert not hasattr(dialog, "_ecr_notes")


def test_change_reason_list_matches_webflow_options_and_saves_multiple_selections(qapp):
    from PySide6.QtCore import Qt
    from autohub.modules.settings.creation_form import CreationSettingsForm as WebFlowSettingsDialog

    expected = [
        "Correction of a situation (e.g. out of audits, legal requirements, specification)",
        "Customer requirement (Target: Customer covers costs)",
        "New supplier / increase of capacity / relocation / standards / others",
        "Q-Problem (in the plant, at supplier or customer site)",
    ]
    dialog = WebFlowSettingsDialog(WebFlowConfig("", "", "", "", change_reason=expected[1]))
    widget = dialog._change_reason
    assert [widget.item(index).text() for index in range(widget.count())] == expected
    assert widget.item(1).checkState() == Qt.Checked
    widget.item(3).setCheckState(Qt.Checked)
    assert dialog.values()["change_reason"] == f"{expected[1]}|{expected[3]}"
    restored = WebFlowSettingsDialog(WebFlowConfig("", "", "", "", change_reason=dialog.values()["change_reason"]))
    assert restored.values()["change_reason"] == dialog.values()["change_reason"]
    for index in range(widget.count()):
        widget.item(index).setCheckState(Qt.Unchecked)
    assert dialog.values()["change_reason"] == ""


def test_change_reason_list_preserves_unrecognized_previous_setting(qapp):
    from autohub.modules.settings.creation_form import CreationSettingsForm as WebFlowSettingsDialog

    dialog = WebFlowSettingsDialog(WebFlowConfig("", "", "", "", change_reason="Previously saved reason"))
    assert dialog.values()["change_reason"] == "Previously saved reason"
    assert dialog._change_reason.item(4).toolTip()


def test_creation_settings_width_fits_reason_options_and_input_content(qapp):
    from autohub.modules.settings.creation_form import CreationSettingsForm as WebFlowSettingsDialog

    config = WebFlowConfig("", "https://example.com/" + "wide-content/" * 8, "", "")
    dialog = WebFlowSettingsDialog(config)
    dialog.show()
    dialog._reason_button.click()
    qapp.processEvents()
    reasons = dialog._change_reason
    assert reasons.viewport().width() >= reasons.sizeHintForColumn(0)
    assert dialog._base_url.width() >= dialog._base_url.fontMetrics().horizontalAdvance(config.base_url) + 24
    assert reasons.horizontalScrollBar().maximum() == 0
    dialog._reason_popup.close()
    dialog.close()


def test_creation_reason_dropdown_opens_filters_and_keeps_multiple_checks(qapp):
    from PySide6.QtCore import Qt
    from autohub.modules.settings.creation_form import CreationSettingsForm as WebFlowSettingsDialog, CHANGE_REASON_OPTIONS

    dialog = WebFlowSettingsDialog(WebFlowConfig("", "", "", ""))
    dialog.show()
    qapp.processEvents()
    assert not dialog._reason_popup.isVisible()
    dialog._reason_button.click()
    qapp.processEvents()
    assert dialog._reason_popup.isVisible()
    dialog._reason_search.setText("Customer requirement")
    assert not dialog._change_reason.item(1).isHidden()
    assert dialog._change_reason.item(0).isHidden()
    dialog._reason_all.click()
    assert dialog.values()["change_reason"] == CHANGE_REASON_OPTIONS[1]
    assert dialog._reason_popup.isVisible()
    dialog._reason_search.clear()
    dialog._change_reason.item(3).setCheckState(Qt.Checked)
    assert dialog.values()["change_reason"] == f"{CHANGE_REASON_OPTIONS[1]}|{CHANGE_REASON_OPTIONS[3]}"
    assert "(+1)" in dialog._reason_button.text()
    dialog._reason_popup.close()
    assert not dialog._reason_popup.isVisible()
    assert dialog.values()["change_reason"]
    dialog.close()


def test_creation_service_passes_ecr_settings_without_mutating_sheet_variants():
    factory = Mock()
    factory.return_value.create_and_fill_jobs.return_value = []
    service = WebFlowJobService(factory)
    variants = [
        {"part_number": "PN", "project": "62XS", "event_name": "HIN"},
        {"part_number": "PN2", "project": "6WZX", "event_name": "MP0"},
    ]
    original = [dict(variant) for variant in variants]
    config = WebFlowConfig(
        "", "", "", "", change_engineer="Engineer", cost_allocation="Allocation", change_reason="Reason",
    )
    service.create_jobs(variants, config)
    sent = factory.return_value.create_and_fill_jobs.call_args.args[0]
    assert sent[0]["ecr"] == {
        "change_engineer": "Engineer", "cost_allocation": "Allocation",
        "change_reason": "Reason", "ecr_notes": "This container is for 62XS HIN event.",
    }
    assert sent[1]["ecr"]["ecr_notes"] == "This container is for 6WZX MP0 event."
    assert variants == original


def test_ecr_notes_need_a_recognised_project_purpose_before_opening_browser():
    factory = Mock()
    service = WebFlowJobService(factory)
    config = WebFlowConfig("", "", "", "", change_engineer="E", cost_allocation="A", change_reason="R")
    with pytest.raises(ValueError, match="Project Purpose has no project and event for PN"):
        service.create_jobs([{"part_number": "PN", "project": "", "event_name": ""}], config)
    factory.assert_not_called()


def test_ecr_notes_are_not_needed_without_ecr_settings():
    factory = Mock()
    factory.return_value.create_and_fill_jobs.return_value = []
    WebFlowJobService(factory).create_jobs([{"part_number": "PN"}], WebFlowConfig("", "", "", ""))
    assert "ecr" not in factory.return_value.create_and_fill_jobs.call_args.args[0][0]


def test_partial_ecr_settings_fail_before_opening_browser():
    factory = Mock()
    service = WebFlowJobService(factory)
    with pytest.raises(ValueError, match="Complete ECR settings"):
        service.create_jobs([{"part_number": "PN"}], WebFlowConfig("", "", "", "", change_reason="Reason"))
    factory.assert_not_called()


@pytest.mark.parametrize("fails_later", [False, True])
def test_creation_service_retains_allocated_ecr_on_original_variant(fails_later):
    factory = Mock()
    def create(variants, **_kwargs):
        variants[0]["imported_ecr_number"] = "ECR123"
        if fails_later:
            raise RuntimeError("later tab failed")
        return [{"PartNumber": "PN", "ECRNumber": "ECR123"}]
    factory.return_value.create_and_fill_jobs.side_effect = create
    service = WebFlowJobService(factory, sleep=lambda _seconds: None)
    variants = [{"part_number": "PN", "project": "62XS", "event_name": "HIN", "imported_ecr_number": "previous run"}]
    config = WebFlowConfig(
        "", "", "", "", change_engineer="Engineer", cost_allocation="Allocation", change_reason="Reason",
    )
    if fails_later:
        with pytest.raises(RuntimeError, match="later tab failed"):
            service.create_jobs(variants, config)
    else:
        assert service.create_jobs(variants, config)[0]["ECRNumber"] == "ECR123"
    assert variants == [{"part_number": "PN", "project": "62XS", "event_name": "HIN", "imported_ecr_number": "ECR123"}]


def test_ecr_notes_use_a_textarea(monkeypatch):
    fields, form = _hardware(monkeypatch)
    control = form.find_element.return_value
    control.get_attribute.side_effect = lambda name: "Notes" if name == "value" else None
    assert fields.fill("ecr_notes", "Notes") is True
    form.find_element.assert_called_once_with(hardware_module.By.CSS_SELECTOR, "textarea")


@pytest.mark.parametrize("value,expected", [("ECR123", True), ("", False), ("0", False)])
def test_ecr_import_is_scoped_single_click_and_retains_number(monkeypatch, value, expected):
    fields, _ = _hardware(monkeypatch)
    fields.imported_ecr_number = "previous job"
    monkeypatch.setattr(hardware_module.Constants, "WEBFLOW_TIMEOUT", 0)
    body = fields.sections["ECR Information"].body.return_value
    button = Mock()
    button.get_attribute.return_value = None
    field = Mock()
    field.get_attribute.return_value = value
    body.find_element.side_effect = lambda _by, locator: button if locator.startswith(".//button") else field
    assert fields.import_ecr() is expected
    assert fields.imported_ecr_number == (value if expected else "")
    button.click.assert_called_once()
    assert "ECR Import" in body.find_element.call_args_list[0].args[1]


def _hardware(monkeypatch):
    fields = HardwareFields(Mock())
    fields._read_software_part_number = Mock(return_value="")
    fields.driver.find_elements.return_value = []
    fields.sections = {panel: Mock() for panel in fields.sections}
    for section in fields.sections.values():
        section.body.return_value = fields.sections["General info"].body.return_value
    fields.sections["General info"].body.return_value.find_element.return_value.get_attribute.return_value = None
    form = fields.sections["General info"].body.return_value.find_element.return_value.find_element.return_value
    monkeypatch.setattr(hardware_module, "pause", lambda: None)
    monkeypatch.setattr(hardware_module, "wait_until_idle", lambda driver, timeout=None: True)
    return fields, form


@pytest.mark.parametrize(
    ("key", "filled", "imported", "expected"),
    [
        ("hardware_part_number", True, True, True),
        ("hardware_part_number", False, True, False),
        ("hardware_part_number", True, False, False),
        ("development_number", True, False, True),
        ("customer_hardware_part_number", True, False, True),
    ],
)
def test_race_import_follows_only_successfully_filled_hardware_number(monkeypatch, key, filled, imported, expected):
    from autohub.services.WebFlow.GeneralTab import GeneralTab
    from autohub.services.WebFlow.Actions import Actions
    from autohub.services.WebFlow.Information import Information

    save = Mock(return_value=True)
    monkeypatch.setattr(Actions, "save", save)
    collapse = Mock(return_value=True)
    monkeypatch.setattr(Information, "collapse_job_information", collapse)
    general = GeneralTab(Mock())
    general.driver.find_elements.return_value = []
    general._hardware = Mock()
    general._hardware.fill.return_value = filled
    general._hardware.import_from_race.return_value = imported

    assert general.fill_hardware_field(key, "part number") is expected
    assert collapse.call_count == (1 if key == "hardware_part_number" and filled and imported else 0)
    general._hardware.fill.assert_called_once_with(key, "part number")
    if key == "hardware_part_number" and filled:
        save.assert_called_once()
        assert general._hardware.method_calls == [
            call.fill(key, "part number"), call.import_from_race(),
        ]
    else:
        save.assert_not_called()
        general._hardware.import_from_race.assert_not_called()


def test_failed_save_prevents_race_import(monkeypatch):
    from autohub.services.WebFlow.GeneralTab import GeneralTab
    from autohub.services.WebFlow.Actions import Actions

    monkeypatch.setattr(Actions, "save", Mock(return_value=False))
    general = GeneralTab(Mock())
    general._hardware = Mock()
    general._hardware.fill.return_value = True
    with pytest.raises(RuntimeError, match="before Import from Race"):
        general.fill_hardware_field("hardware_part_number", "HW123")
    general._hardware.import_from_race.assert_not_called()


def test_race_import_saves_after_hardware_number_and_before_import(monkeypatch):
    from autohub.services.WebFlow.GeneralTab import GeneralTab
    from autohub.services.WebFlow.Actions import Actions
    from autohub.services.WebFlow.Information import Information

    events = []
    monkeypatch.setattr(Actions, "save", lambda _self: events.append("save") or True)
    monkeypatch.setattr(Information, "collapse_job_information", lambda _self: events.append("collapse") or True)
    general = GeneralTab(Mock())
    general.driver.find_elements.return_value = []
    general._hardware = Mock()
    general._hardware.fill.side_effect = lambda *_: events.append("fill") or True
    general._hardware.import_from_race.side_effect = lambda: events.append("import") or True
    assert general.fill_hardware_field("hardware_part_number", "HW123")
    assert events == ["fill", "save", "import", "collapse"]


def test_race_import_clicks_classification_button_once_and_waits(monkeypatch):
    fields, _ = _hardware(monkeypatch)
    section = fields.sections["Classification"]
    button = section.body.return_value.find_element.return_value
    idle = Mock(return_value=True)
    monkeypatch.setattr(hardware_module, "wait_until_idle", idle)

    assert fields.import_from_race()
    section.expand.assert_called_once()
    section.body.return_value.find_element.assert_called_once_with(
        hardware_module.By.XPATH, './/button[.//span[normalize-space(.)="Import from Race"]]'
    )
    button.click.assert_called_once()
    idle.assert_called_once_with(fields.driver, hardware_module.Constants.WEBFLOW_TIMEOUT)


def test_race_import_confirms_save_warning_before_waiting_for_completion(monkeypatch):
    fields, _ = _hardware(monkeypatch)
    dialog = Mock()
    dialog.text = "Data filled in by you will be saved before import. Do you want to continue?"
    dialog.is_displayed.return_value = True
    yes = dialog.find_element.return_value
    yes.click.side_effect = lambda: setattr(dialog.is_displayed, "return_value", False)
    fields.driver.find_elements.return_value = [dialog]
    idle = Mock(return_value=True)
    monkeypatch.setattr(hardware_module, "wait_until_idle", idle)

    assert fields.import_from_race()
    yes.click.assert_called_once()
    idle.assert_called_once()
    fields.sections["Classification"].body.return_value.find_element.return_value.click.assert_called_once()


@pytest.mark.parametrize("failure", ["expand", "disabled", "click", "wait"])
def test_race_import_reports_failures_without_repeating_click(monkeypatch, failure, caplog):
    fields, _ = _hardware(monkeypatch)
    section = fields.sections["Classification"]
    button = section.body.return_value.find_element.return_value
    monkeypatch.setattr(hardware_module.Constants, "BODY_TIMEOUT", 0)
    if failure == "expand":
        section.expand.return_value = False
    elif failure == "disabled":
        button.is_enabled.return_value = False
    elif failure == "click":
        button.click.side_effect = RuntimeError("connection lost")
    else:
        monkeypatch.setattr(hardware_module, "wait_until_idle", Mock(side_effect=TimeoutException()))

    assert fields.import_from_race() is False
    assert button.click.call_count == (1 if failure in ("click", "wait") else 0)
    assert "import from Race" in caplog.text


@pytest.mark.parametrize("column,key,label,kind", [field for field in HARDWARE_FIELDS if field[3] == "text"])
def test_hardware_text_fields_are_written_and_verified(monkeypatch, column, key, label, kind):
    fields, form = _hardware(monkeypatch)
    control = form.find_element.return_value
    state = {"value": "old value"}
    control.get_attribute.side_effect = lambda name: state["value"] if name == "value" else None
    control.send_keys.side_effect = lambda value: state.update(value=value)
    assert fields.fill(key, "sheet value") is True
    control.clear.assert_called_once()
    control.send_keys.assert_called_once_with("sheet value")
    locator = fields.sections[hardware_module._FIELD_PANELS[key]].body.return_value.find_element.call_args.args[1]
    assert label in locator
    fields.sections[hardware_module._FIELD_PANELS[key]].expand.assert_called_once()


@pytest.mark.parametrize("readonly", [False, True])
@pytest.mark.parametrize("key,value", [
    ("vehicle_model", "62XS"), ("ecr_notes", "Notes"),
    ("hardware_part_number", "0261S10BN8"), ("software_name", "10SW072930"),
])
def test_matching_hardware_values_skip_editing(monkeypatch, readonly, key, value):
    fields, form = _hardware(monkeypatch)
    control = form.find_element.return_value
    control.is_enabled.return_value = not readonly
    control.get_attribute.side_effect = lambda attr: value if attr == "value" else "true" if readonly else None
    assert fields.fill(key, value)
    control.clear.assert_not_called()
    control.send_keys.assert_not_called()


def test_hardware_read_only_field_fails_explicitly(monkeypatch):
    fields, form = _hardware(monkeypatch)
    form.find_element.return_value.is_enabled.return_value = False
    assert fields.fill("vehicle_model", "62XS") is False
    form.find_element.return_value.send_keys.assert_not_called()


def test_field_expands_only_its_own_panel(monkeypatch):
    fields, form = _hardware(monkeypatch)
    control = form.find_element.return_value
    control.get_attribute.side_effect = lambda name: "0261S10BN8" if name == "value" else None
    assert fields.fill("hardware_part_number", "0261S10BN8") is True
    fields.sections["Bosch logistic info"].expand.assert_called_once()
    for name, section in fields.sections.items():
        if name != "Bosch logistic info":
            section.expand.assert_not_called()


def test_missing_panel_stops_before_typing(monkeypatch):
    fields, form = _hardware(monkeypatch)
    fields.sections["Ident Numbers"].expand.return_value = False
    assert fields.fill("lead_plant", "SaW") is False
    form.find_element.assert_not_called()


def test_hardware_dropdown_passes_the_sheet_value(monkeypatch):
    fields, form = _hardware(monkeypatch)
    select = Mock(return_value=True)
    monkeypatch.setattr(fields, "_select_plant", select)
    assert fields.fill("lead_plant", "Sheet plant") is True
    select.assert_called_once_with(form, "Sheet plant")


def test_hardware_multiselect_replaces_previous_selection(monkeypatch):
    fields, form = _hardware(monkeypatch)
    first, second = Mock(), Mock()
    for item, name, initial in ((first, "Brazil", False), (second, "Japan", True)):
        state = {"selected": initial}
        item.get_attribute.side_effect = lambda attr, state=state, name=name: name if attr == "aria-label" else str(state["selected"]).lower()
        item.click.side_effect = lambda state=state: state.update(selected=not state["selected"])
    panel = Mock()
    panel.find_elements.return_value = [first, second]
    fields.driver.find_elements.return_value = [panel]
    assert fields._select_multiple(form, "Brazil") is True
    fields.driver.execute_script.assert_any_call("arguments[0].scrollIntoView({block: 'center'});", form.find_element.return_value)
    first.click.assert_called_once()
    second.click.assert_called_once()
    assert form.find_element.return_value.find_element.return_value.click.call_count == 2


def test_hardware_multiselect_missing_option_fails(monkeypatch):
    fields, form = _hardware(monkeypatch)
    panel = Mock()
    panel.find_elements.return_value = []
    fields.driver.find_elements.return_value = [panel]
    assert fields._select_multiple(form, "Brazil") is False


@pytest.mark.parametrize("key,value,names,expected", [
    ("model_year", "MY27/MY28", ["2027", "2028"], True),
    ("emission_norm", "PROCONVE-L8", ["PROCONVE L8"], True),
    ("transmission", "manual", ["MT", "AT"], True),
    ("immobilizer", "Active|IMMO 6", ["active", "IMMO6"], True),
    ("market", "UK/Brazil", ["GB", "Brazil"], True),
    ("market", "Brazil/Unknown", ["Brazil", "Japan"], False),
])
def test_hardware_fill_resolves_general_lists_before_clicking(monkeypatch, key, value, names, expected):
    fields, form = _hardware(monkeypatch)
    panel = Mock()
    items = []
    for name in names:
        item = Mock()
        state = {"selected": False}
        item.get_attribute.side_effect = lambda attr, state=state, name=name: (
            name if attr == "aria-label" else str(state["selected"]).lower()
        )
        item.click.side_effect = lambda state=state: state.update(selected=not state["selected"])
        items.append(item)
    panel.find_elements.return_value = items
    fields.driver.find_elements.return_value = [panel]

    assert fields.fill(key, value) is expected
    if expected:
        items[0].click.assert_called_once()
    else:
        for item in items:
            item.click.assert_not_called()
    assert form.find_element.return_value.find_element.return_value.click.call_count == 2


def test_pool_import_waits_for_number_and_clicks_only_once(monkeypatch, caplog):
    fields, _ = _hardware(monkeypatch)
    fields.fill = Mock(return_value=True)
    button = fields.sections["Ident Numbers"].body.return_value.find_element.return_value
    button.is_displayed.return_value = True
    button.is_enabled.return_value = True
    field = fields.sections["Ident Numbers"].body.return_value.find_element.return_value
    values = iter(["", "0", "10SW137784"])
    field.get_attribute.side_effect = lambda attr: next(values) if attr == "value" else None
    with caplog.at_level("INFO", logger=hardware_module.__name__):
        assert fields.import_software_part_number() is True
    button.click.assert_called_once()
    fields.driver.find_element.assert_not_called()
    locator = fields.sections["Ident Numbers"].body.return_value.find_element.call_args_list[0].args[1]
    assert locator.startswith(".//button") and "Import from pool" in locator
    assert "Software part number = 10SW137784" in caplog.text
    assert fields.imported_software_part_number == "10SW137784"
    assert fields.fill.call_args_list == [
        (("software_name", "10SW137784"),),
        (("customer_software_part_number", "10SW137784"),),
    ]


@pytest.mark.parametrize("method,panel", [
    ("import_from_race", "Classification"),
    ("import_software_part_number", "Ident Numbers"),
    ("import_ecr", "ECR Information"),
    ("pick_pst_lib", "Ident Numbers"),
])
@pytest.mark.parametrize("state", ["native", "disabled", "p-disabled", "bg-disabled", "aria-disabled", "ng-reflect-disabled"])
def test_disabled_import_buttons_are_never_clicked(monkeypatch, method, panel, state):
    fields, _ = _hardware(monkeypatch)
    monkeypatch.setattr(hardware_module.Constants, "BODY_TIMEOUT", 0)
    button = fields.sections[panel].body.return_value.find_element.return_value
    button.is_enabled.return_value = state != "native"
    button.get_attribute.side_effect = lambda attr: (
        state if attr == "class" and state in ("disabled", "p-disabled", "bg-disabled")
        else "true" if attr == state else None
    )
    args = ("PV01",) if method == "pick_pst_lib" else ()
    assert getattr(fields, method)(*args) is False
    button.click.assert_not_called()


@pytest.mark.parametrize("method,panel", [
    ("import_from_race", "Classification"),
    ("import_software_part_number", "Ident Numbers"),
    ("import_ecr", "ECR Information"),
])
def test_import_button_disabled_after_scroll_is_not_clicked(monkeypatch, method, panel):
    fields, _ = _hardware(monkeypatch)
    button = fields.sections[panel].body.return_value.find_element.return_value
    button.is_enabled.side_effect = [True, False]
    assert getattr(fields, method)() is False
    button.click.assert_not_called()


def test_pool_import_timeout_is_failure_without_retry(monkeypatch):
    fields, _ = _hardware(monkeypatch)
    fields.imported_software_part_number = "previous job number"
    monkeypatch.setattr(hardware_module.Constants, "WEBFLOW_TIMEOUT", 0)
    button = fields.sections["Ident Numbers"].body.return_value.find_element.return_value
    button.is_displayed.return_value = True
    button.is_enabled.return_value = True
    field = fields.sections["Ident Numbers"].body.return_value.find_element.return_value
    field.get_attribute.return_value = ""
    assert fields.import_software_part_number() is False
    assert fields.imported_software_part_number == ""
    button.click.assert_called_once()


def test_existing_software_number_is_copied_without_pool_import(monkeypatch):
    fields, _ = _hardware(monkeypatch)
    fields._read_software_part_number.return_value = "10SW072930"
    fields._import_number = Mock()
    fields.fill = Mock(return_value=True)
    assert fields.import_software_part_number()
    fields._import_number.assert_not_called()
    assert fields.imported_software_part_number == "10SW072930"
    assert fields.fill.call_args_list == [
        call("software_name", "10SW072930"),
        call("customer_software_part_number", "10SW072930"),
    ]


@pytest.mark.parametrize("value,expected", [
    (" 10SW072930 ", "10SW072930"), ("", ""), ("0", ""), ("---", ""),
])
def test_reads_software_number_from_ident_numbers(monkeypatch, value, expected):
    fields, _ = _hardware(monkeypatch)
    field = fields.sections["Ident Numbers"].body.return_value.find_element.return_value
    field.get_attribute.return_value = value
    assert HardwareFields._read_software_part_number(fields) == expected
    assert "Software part number" in fields.sections["Ident Numbers"].body.return_value.find_element.call_args.args[1]


@pytest.mark.parametrize("panel,method", [
    ("Ident Numbers", "import_software_part_number"), ("ECR Information", "import_ecr"),
])
def test_import_does_not_retry_uncertain_click(monkeypatch, panel, method):
    fields, _ = _hardware(monkeypatch)
    button = fields.sections[panel].body.return_value.find_element.return_value
    button.is_displayed.return_value = True
    button.is_enabled.return_value = True
    button.click.side_effect = RuntimeError("connection lost")
    assert getattr(fields, method)() is False
    button.click.assert_called_once()


@pytest.mark.parametrize("panel,method", [
    ("Ident Numbers", "import_software_part_number"), ("ECR Information", "import_ecr"),
])
def test_import_confirms_save_warning_once_then_waits_for_number(monkeypatch, panel, method):
    fields, _ = _hardware(monkeypatch)
    fields.fill = Mock(return_value=True)
    control = fields.sections[panel].body.return_value.find_element.return_value
    control.is_displayed.return_value = True
    control.is_enabled.return_value = True
    control.get_attribute.return_value = "10SW137784"
    dialog = Mock()
    dialog.text = "Data filled in by you will be saved before import. Do you want to continue?"
    yes = dialog.find_element.return_value
    fields.driver.find_elements.side_effect = [[dialog], [dialog], []]
    assert getattr(fields, method)() is True
    yes.click.assert_called_once()
    control.click.assert_called_once()
    assert "Yes" in dialog.find_element.call_args.args[1]


def test_pool_import_does_not_confirm_unrelated_dialog(monkeypatch):
    fields, _ = _hardware(monkeypatch)
    fields.fill = Mock(return_value=True)
    control = fields.sections["Ident Numbers"].body.return_value.find_element.return_value
    control.get_attribute.return_value = "10SW137784"
    dialog = Mock()
    dialog.text = "An unrelated confirmation"
    fields.driver.find_elements.return_value = [dialog]
    assert fields.import_software_part_number() is True
    dialog.find_element.assert_not_called()


@pytest.mark.parametrize("failed_key", ["software_name", "customer_software_part_number"])
def test_pool_import_copy_failure_retains_allocated_number(monkeypatch, failed_key):
    fields, _ = _hardware(monkeypatch)
    fields.fill = Mock(side_effect=lambda key, value: key != failed_key)
    control = fields.sections["Ident Numbers"].body.return_value.find_element.return_value
    control.get_attribute.return_value = "10SW072930"
    assert fields.import_software_part_number() is False
    assert fields.imported_software_part_number == "10SW072930"
    control.click.assert_called_once()


def test_software_name_is_written_in_ident_numbers(monkeypatch):
    fields, form = _hardware(monkeypatch)
    control = form.find_element.return_value
    state = {"value": ""}
    control.get_attribute.side_effect = lambda name: state["value"] if name == "value" else None
    control.send_keys.side_effect = lambda value: state.update(value=value)
    assert fields.fill("software_name", "10SW072930") is True
    control.send_keys.assert_called_once_with("10SW072930")
    fields.sections["Ident Numbers"].expand.assert_called_once()


def test_lead_plant_waits_until_requested_option_is_loaded(monkeypatch):
    fields, _ = _hardware(monkeypatch)
    option = Mock()
    option.get_attribute.return_value = "SaW"
    panel = Mock()
    panel.find_elements.return_value = [option]
    fields.driver.find_elements.side_effect = [[], [], [panel]]
    assert fields._loaded_options("SaW") == {"SaW": option}
    assert fields.driver.find_elements.call_count == 3


def test_plant_scrolls_clicks_trigger_and_waits_for_selection(monkeypatch):
    fields, form = _hardware(monkeypatch)
    control = Mock()
    selected = Mock()
    selected.get_attribute.return_value = "SaW"
    form.find_element.side_effect = [control, selected]
    control.find_element.return_value.get_attribute.return_value = "---"
    fields._loaded_options = Mock(return_value={"SaW": Mock()})
    monkeypatch.setattr(hardware_module.EC, "element_to_be_clickable", lambda element: lambda driver: element)
    assert fields._select_plant(form, "SaW") is True
    fields.driver.execute_script.assert_any_call("arguments[0].scrollIntoView({block: 'center'});", control)
    control.find_element.return_value.click.assert_called_once()
    fields._loaded_options.assert_called_once_with("SaW")


@pytest.mark.parametrize("initial", [None, True, False])
def test_classification_sets_one_variant_and_x_checkboxes(monkeypatch, initial):
    fields, _ = _hardware(monkeypatch)
    section = fields.sections["Classification"]
    checkbox = section.body.return_value.find_element.return_value.find_element.return_value
    checkbox.get_attribute.return_value = None
    states = [initial]
    def value(_checkbox):
        return states[0]
    def click():
        states[0] = {None: True, True: False, False: None}[states[0]]
    checkbox.click.side_effect = click
    monkeypatch.setattr(hardware_module, "checkbox_value", value)
    monkeypatch.setattr(hardware_module.EC, "element_to_be_clickable", lambda element: lambda _driver: element)
    assert fields.prepare_classification() is True
    assert section.fill_input.call_args.args[1] == "1"
    assert states[0] is False


def test_classification_scrolls_before_clicking_and_checks_final_transition(monkeypatch):
    fields, _ = _hardware(monkeypatch)
    checkbox = fields.sections["Classification"].body.return_value.find_element.return_value.find_element.return_value
    states = iter([None, True, None, False, False])
    monkeypatch.setattr(hardware_module, "checkbox_value", lambda _checkbox: next(states))
    monkeypatch.setattr(hardware_module, "checkbox_is_disabled", lambda *_: False)
    events = []
    fields.driver.execute_script.side_effect = lambda *_: events.append("scroll")
    monkeypatch.setattr(
        hardware_module.EC, "element_to_be_clickable",
        lambda _element: lambda _driver: events.append("ready") or True,
    )
    checkbox.click.side_effect = lambda: events.append("click")
    assert fields.prepare_classification() is True
    assert events == ["scroll", "ready", "click"] * 3


def test_classification_disabled_host_is_not_clicked(monkeypatch):
    fields, _ = _hardware(monkeypatch)
    checkbox = fields.sections["Classification"].body.return_value.find_element.return_value.find_element.return_value
    monkeypatch.setattr(hardware_module, "checkbox_value", lambda _checkbox: None)
    monkeypatch.setattr(hardware_module, "checkbox_is_disabled", lambda *_: True)
    assert fields.prepare_classification() is False
    checkbox.click.assert_not_called()


def test_classification_nonclickable_checkbox_fails_explicitly(monkeypatch):
    fields, _ = _hardware(monkeypatch)
    checkbox = fields.sections["Classification"].body.return_value.find_element.return_value.find_element.return_value
    monkeypatch.setattr(hardware_module.Constants, "BODY_TIMEOUT", 0)
    monkeypatch.setattr(hardware_module, "checkbox_value", lambda _checkbox: None)
    monkeypatch.setattr(hardware_module, "checkbox_is_disabled", lambda *_: False)
    monkeypatch.setattr(hardware_module.EC, "element_to_be_clickable", lambda _element: lambda _driver: False)
    assert fields.prepare_classification() is False
    checkbox.click.assert_not_called()


def test_classification_failure_is_reported(monkeypatch):
    fields, _ = _hardware(monkeypatch)
    fields.sections["Classification"].fill_input.return_value = False
    assert fields.prepare_classification() is False


@pytest.mark.parametrize("succeed", [True, False])
def test_total_duration_includes_browser_and_link_writing(monkeypatch, caplog, succeed):
    ticks = iter((10.0, 135.5))
    monkeypatch.setattr(creation_service, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))
    service = WebFlowJobService(FakeWebFlow)
    if not succeed:
        service._create = Mock(side_effect=RuntimeError("browser failed"))
    with caplog.at_level("INFO", logger=creation_service.__name__):
        if succeed:
            service.create_jobs([{"part_number": "PN"}], WebFlowConfig("", "", "", ""))
        else:
            with pytest.raises(RuntimeError, match="browser failed"):
                service.create_jobs([{"part_number": "PN"}], WebFlowConfig("", "", "", ""))
    assert service.last_elapsed_seconds == 125.5
    assert "total time 125.5 seconds" in caplog.text
    assert ("completed" if succeed else "failed") in caplog.text
