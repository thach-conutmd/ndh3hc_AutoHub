"""Shared WebFlow widgets and the job-fill step plan, exercised with fake Selenium elements."""
import pytest
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys

from autohub.services.WebFlow import Constants, components
from autohub.services.WebFlow.Information import Information
from autohub.services.WebFlow import Information as information_module
from autohub.services.WebFlow import ECUTab as ecu_tab_module
from autohub.services.WebFlow import pst_lib_picker as picker_module
from autohub.services.WebFlow.ECUTab import ECUTab
from autohub.services.WebFlow.HardwareFields import HardwareFields
from autohub.services.WebFlow.components import Section, TabLink, select_dropdown, similar_option
from autohub.services.WebFlow.job_filler import JobFiller


class Element:
    def __init__(self, attrs=None, children=None, displayed=True, selected=False):
        self.attrs = attrs or {}
        self.children = children or {}
        self.displayed, self.selected = displayed, selected
        self.clicks, self.typed, self.cleared = 0, [], 0

    def get_attribute(self, name):
        return self.attrs.get(name)

    def find_element(self, by, value):
        if value not in self.children:
            raise NoSuchElementException(value)
        return self.children[value]

    def is_displayed(self):
        return self.displayed

    def is_selected(self):
        return self.selected

    def is_enabled(self):
        return True

    def click(self):
        self.clicks += 1

    def clear(self):
        self.cleared += 1

    def send_keys(self, text):
        self.typed.append(text)
        self.attrs["value"] = text


class Driver:
    def __init__(self):
        self.scripts = []

    def execute_script(self, script, element):
        self.scripts.append(element)


@pytest.fixture
def page(monkeypatch):
    """Locators resolve to the elements registered in the returned dict; WebFlow is always idle."""
    elements = {}

    def wait_for(driver, by, locator, timeout=None):
        if locator not in elements:
            raise LookupError(locator)
        return elements[locator]

    monkeypatch.setattr(components, "wait_for", wait_for)
    monkeypatch.setattr(ecu_tab_module, "wait_for", wait_for)
    monkeypatch.setattr(components, "wait_until_idle", lambda driver, timeout=None: True)
    monkeypatch.setattr(Constants, "WEBFLOW_TIMEOUT_CSS", 0)
    monkeypatch.setattr(Constants, "BODY_TIMEOUT", 0)
    return elements


def dropdown(page, selected=None):
    children = {f".//span[text()='{selected}']": Element()} if selected else {}
    button = Element(children=children)
    page["//title"] = Element(children={"..": Element(children={"div.btn": button})})
    return button


def test_dropdown_already_showing_the_value_is_not_clicked(page):
    button = dropdown(page, selected="MG1")
    assert select_dropdown(Driver(), "//title", "div.btn", "MG1", lambda: pytest.fail("options read")) is True
    assert button.clicks == 0


def test_idle_wait_covers_loading_overlay_without_activity_spinner():
    from unittest.mock import Mock

    driver = Mock()
    overlay = Mock()
    overlay.is_displayed.return_value = True
    driver.find_elements.side_effect = [[overlay], []]
    assert components.wait_until_idle(driver, 1)
    assert "loading-screen-wrapper" in driver.find_elements.call_args.args[1]
    assert driver.find_elements.call_count == 2


def test_dropdown_opens_and_clicks_the_option_without_fixed_pause(page, monkeypatch):
    button = dropdown(page)
    option = Element()

    def click_option():
        option.clicks += 1
        button.children[".//span[text()='MG1']"] = Element()

    option.click = click_option
    monkeypatch.setattr(components, "pause", lambda: pytest.fail("dropdown should use explicit waits"))

    assert select_dropdown(Driver(), "//title", "div.btn", "MG1", lambda: {"MG1": option, "MX17": Element()}) is True
    assert button.clicks == 1 and option.clicks == 1


def test_dropdown_matches_options_with_updated_unpadded_labels(page):
    button = dropdown(page)
    option = Element()

    def click_option():
        option.clicks += 1
        button.children[".//span[normalize-space(text())='10']"] = Element()

    option.click = click_option

    assert select_dropdown(Driver(), "//title", "div.btn", " 10", lambda: {"10": option}) is True
    assert button.clicks == 1 and option.clicks == 1


def test_dropdown_without_the_value_clicks_no_option(page):
    button = dropdown(page)
    other = Element()
    assert select_dropdown(Driver(), "//title", "div.btn", "MG1", lambda: {"MX17": other}) is False
    assert button.clicks == 1 and other.clicks == 0


def test_dropdown_missing_title_is_a_failure(page):
    assert select_dropdown(Driver(), "//missing", "div.btn", "MG1", dict) is False


def test_dropdown_rejects_a_value_that_does_not_stick(page):
    dropdown(page)
    assert select_dropdown(Driver(), "//title", "div.btn", "Pre-Production", lambda: {"Pre-Production": Element()}) is False


@pytest.mark.parametrize("value, labels, expected", [
    ("PD W0002", ["PD W0001 (Productive)", "PD W0002 (Productive)"], "PD W0002 (Productive)"),
    ("pd  w0002", ["PD W0002 (Productive)"], "PD W0002 (Productive)"),
    ("PD W0002", ["PD W0002", "PD W0002 (Productive)"], "PD W0002"),
    ("W0002", ["PD W0002 (Productive)", "PD W0003 (Productive)"], "PD W0002 (Productive)"),
    ("PD W0002 (Productive)", ["PD W0002"], "PD W0002"),
    ("PD W0002", ["PD W00021 (Productive)"], None),
    ("PD W0002", ["PD W0002 (Productive)", "PD W0002 (Test)"], None),
    ("", ["PD W0002 (Productive)"], None),
])
def test_similar_option(value, labels, expected):
    assert similar_option(value, labels) == expected


def test_similar_dropdown_selects_the_option_containing_the_value(page):
    button = dropdown(page)
    option, other = Element(), Element()

    def click_option():
        option.clicks += 1
        button.children[".//span[text()='PD W0002 (Productive)']"] = Element()

    option.click = click_option
    options = {"PD W0001 (Productive)": other, "PD W0002 (Productive)": option}

    assert select_dropdown(Driver(), "//title", "div.btn", "PD W0002", lambda: options, similar=True) is True
    assert option.clicks == 1 and other.clicks == 0


def test_similar_dropdown_already_showing_a_similar_value_is_not_clicked(page):
    button = dropdown(page)
    shown = Element()
    shown.text = "PD W0002 (Productive)"
    button.children[".//span[contains(normalize-space(text()), 'PD W0002')]"] = shown
    assert select_dropdown(
        Driver(), "//title", "div.btn", "PD W0002", lambda: pytest.fail("options read"), similar=True
    ) is True
    assert button.clicks == 0


def test_exact_dropdowns_do_not_pick_similar_options(page):
    dropdown(page)
    option = Element()
    assert select_dropdown(Driver(), "//title", "div.btn", "PD W0002", lambda: {"PD W0002 (Productive)": option}) is False
    assert option.clicks == 0


def section(page, style):
    body = Element({"style": style}, displayed=False)
    header = Element(children={"../..": Element(children={"div.body": body})})
    page["//section"] = Element(children={"..": header, "../..": header.children["../.."]})
    return header, body


def test_section_expands_only_when_collapsed(page):
    header, body = section(page, "display: none;")
    driver = Driver()
    sec = Section(driver, "//section", "div.body")
    assert sec.is_collapsed() and not sec.is_expanded()
    assert sec.expand() is True and header.clicks == 1
    assert driver.scripts and set(driver.scripts) == {body}  # the hidden body is scrolled into view while read

    body.attrs["style"] = "display: block;"
    assert sec.expand() is True and header.clicks == 1
    assert sec.collapse() is True and header.clicks == 2


def test_section_state_of_a_missing_section_is_neither(page):
    sec = Section(Driver(), "//missing", "div.body")
    assert sec.is_expanded() is False and sec.is_collapsed() is False
    assert sec.expand() is False


def test_section_fills_an_input(page):
    _, body = section(page, "display: block;")
    field = Element()
    body.children["input.x"] = field
    sec = Section(Driver(), "//section", "div.body")
    assert sec.fill_input("input.x", "ABC") is True
    assert field.cleared == 1 and field.typed == ["ABC"]
    assert sec.fill_input("input.missing", "ABC") is False


def test_tab_link_clicks_only_an_unselected_tab(page):
    tab = Element()
    page["//tab"] = tab
    link = TabLink(Driver(), "//tab")
    assert link.select() is True and tab.clicks == 1
    tab.selected = True
    assert link.is_selected() and link.select() is True and tab.clicks == 1
    assert TabLink(Driver(), "//missing").select() is False


def test_job_information_reports_whether_it_clicked(page, monkeypatch):
    monkeypatch.setattr(Constants, "BODY_INFORMATION_TITLE_XPATH", "//section")
    monkeypatch.setattr(Constants, "BODY_INFORMATION_BODY_CSS", "div.body")
    header, body = section(page, "display: block;")
    monkeypatch.setattr(information_module, "wait_until_idle", lambda *_: True)
    def toggle():
        header.clicks += 1
        body.attrs["style"] = "display: none;" if "block" in body.attrs["style"] else "display: block;"
    header.click = toggle
    info = Information(Driver())
    assert info.collapse_job_information() is True and header.clicks == 1
    body.attrs["style"] = "display: none;"
    assert info.collapse_job_information() is True
    assert info.expand_job_information() is True and header.clicks == 2


@pytest.mark.parametrize(
    ("icon", "check", "clicks"),
    [(None, None, 0), (None, True, 1), (None, False, 2), ("check", True, 0), ("check", False, 1), ("check", None, 2),
     ("uncheck", False, 0), ("uncheck", None, 1), ("uncheck", True, 2)],
)
def test_lctvorb_checkbox_cycles_to_the_requested_value(page, monkeypatch, icon, check, clicks):
    monkeypatch.setattr(Constants, "ECU_PROJECT_LCTVORB_TITLE_XPATH", "//lctvorb")
    icons = {
        "check": {'checkicon[data-pc-section="checkIcon"]': Element()},
        "uncheck": {'timesicon[data-pc-section="uncheckIcon"]': Element()},
    }
    checkbox = Element(children=icons.get(icon, {}))
    page["//lctvorb"] = Element(children={"..": Element(children={Constants.ECU_PROJECT_LCTVORB_CHECKBOX_CSS: checkbox})})
    tab = ECUTab(Driver())
    tab.expand_ecu_specific_parameters = lambda: True
    assert tab.select_project_lctvorb(check) is True
    assert checkbox.clicks == clicks


class Recorder:
    """Any page method: records its call and returns the configured result."""

    def __init__(self, calls, results):
        self.calls, self.results = calls, results
        self.skipped_fields = []
        self.imported_software_part_number = ""
        self.imported_ecr_number = ""

    def __getattr__(self, name):
        def method(*args):
            self.calls.append((name, *args))
            return self.results.get(name, True)
        return method


def filler(results=None):
    calls = []
    pages = Recorder(calls, results or {})

    class Tabs:
        generaltab = ecutab = customertab = pages

    class Body:
        tab, information, actions = Tabs, pages, pages

    return JobFiller(pages, Body), calls, pages


VARIANT = {
    "part_number": "37820-ABC",
    "general": {"delivery_type": "Plant", "release_class": "C", "release_scope": "S", "limitations": "NO",
                "safety_monitoring": True, "safety_calibration": None, "calibration": False, "data_integration": True},
    "hardware": {"program_version": "PV01"},
    "ecu": {"indi_spec": "Spec", "family_name": "", "project_version": "P001", "program_version": None, "tp_level": "3"},
    "customer": {"ecu_default_id": "1", "ecu_program_id": "", "ecu_rewriting_id": "3", "security_coefficient": "",
                 "sw_version": "01", "component_id": "C"},
}


@pytest.fixture(autouse=True)
def _fresh_variant():
    yield
    VARIANT.pop("attempted_imports", None)  # fill() records number imports on the variant


def test_job_filler_plans_the_legacy_steps_in_order():
    job_filler, _, _ = filler()
    names = [step[0] for step in job_filler.steps(VARIANT)]
    assert names == [
        "Close the side menu",
        "Collapse the job information",
        "General: delivery type = Plant",
        "General: release class = C",
        "General: release scope = S",
        "General: limitations = NO",
        "General: safety monitoring SW = True",
        "General: safety calibration response = False",
        "General: Bosch calibration data response = False",
        "General: data integration response = True",
        "General: Program version = PV01",
        "Save the job before Pick PST_Lib",
        "General: Pick PST_Lib for PVER PV01",
        "Select the ECU tab",
        "ECU: indi_spec = Spec",
        "ECU: project_version = P001",
        "ECU: tp_level = 3",
        "Select the Customer tab",
        "Customer: ecu_default_id = 1",
        "Customer: ecu_rewriting_id = 3",
        "Customer: sw_version = 01",
        "Customer: component_id = C",
        "Save the job",
    ]


@pytest.mark.parametrize("part_number", ["37820-6WZ-M610-M6", "37820-6WZ-M710-M6"])
def test_sheet_release_class_reaches_the_webflow_selector(part_number, caplog):
    from autohub.services.MasterSheet.webflow_variants import webflow_variant_from_row

    variant = webflow_variant_from_row(part_number, {"U": "Pre-Production"})
    job_filler, calls, _ = filler()
    with caplog.at_level("INFO", logger="autohub.services.WebFlow"):
        job_filler.fill(variant)
    assert ("select_release_class", "Pre-Production") in calls
    assert ("select_release_class", "Production") not in calls
    assert f"[{part_number}] General: release class = Pre-Production" in caplog.text


def test_job_filler_logs_every_value(caplog):
    job_filler, _, _ = filler()
    with caplog.at_level("INFO", logger="autohub.services.WebFlow"):
        job_filler.fill(VARIANT)
    summary = next(r.getMessage() for r in caplog.records if "Values to fill" in r.getMessage())
    assert "[37820-ABC] Values to fill: General[delivery_type=Plant" in summary
    assert "safety_calibration=(none)" in summary and "family_name=(empty)" in summary
    assert "Customer[ecu_default_id=1" in summary and "component_id=C]" in summary
    assert any("Step: [37820-ABC] General: limitations = NO" == r.getMessage() for r in caplog.records)


def test_job_filler_runs_every_step_and_returns_warnings():
    job_filler, calls, pages = filler()
    pages.skipped_fields.append("stale warning")
    assert job_filler.fill(VARIANT) == []  # warnings are cleared per job
    assert calls[0] == ("select_general_tab",)
    assert ("select_safety_calibration_response", None) not in calls
    assert ("select_safety_calibration_response", False) in calls
    assert ("select_tp_level", "3") in calls and calls[-1] == ("save",)


def test_job_filler_names_every_failed_step():
    job_filler, calls, _ = filler({"fill_sw_version": False, "save": False})
    with pytest.raises(RuntimeError, match=r"37820-ABC.*Customer: sw_version = 01; \[37820-ABC\] Save the job"):
        job_filler.fill({**VARIANT, "hardware": {}})
    assert calls[-1] == ("save",)  # later steps still ran


def test_job_filler_stops_when_the_general_tab_cannot_be_selected():
    job_filler, calls, _ = filler({"select_general_tab": False})
    with pytest.raises(RuntimeError, match="General tab"):
        job_filler.fill(VARIANT)
    assert calls == [("select_general_tab",)]


@pytest.mark.parametrize("action,hardware,ecr", [
    ("import_software_part_number", {"lead_plant": "SaW"}, {}),
    ("pick_pst_lib", {"program_version": "PV01"}, {}),
    ("import_ecr", {}, {"change_reason": "Reason"}),
])
@pytest.mark.parametrize("saved", [True, False])
def test_save_precedes_each_import_and_picker_without_consuming_import_on_failure(action, hardware, ecr, saved):
    from unittest.mock import Mock

    job_filler, calls, pages = filler({"save": saved})
    job_filler.checkpoint = Mock()
    pages.imported_software_part_number = "SW123"
    pages.imported_ecr_number = "ECR123"
    variant = {**VARIANT, "hardware": hardware, "ecr": ecr}
    if saved:
        job_filler.fill(variant)
        action_index = next(index for index, recorded in enumerate(calls) if recorded[0] == action)
        assert calls[action_index - 1] == ("save",)
        assert calls[-1] == ("save",)
    else:
        with pytest.raises(RuntimeError, match="Could not save the job before"):
            job_filler.fill(variant)
        assert not any(recorded[0] == action for recorded in calls)
        assert variant["attempted_imports"] == []
        job_filler.checkpoint.assert_not_called()
        pages.results["save"] = True
        job_filler.fill(variant)
        assert sum(recorded[0] == action for recorded in calls) == 1


def test_job_filler_saves_before_picker_but_stops_when_no_pst_lib_matches():
    job_filler, calls, _ = filler({"pick_pst_lib": False})
    with pytest.raises(RuntimeError, match="PST_Lib entry matching PVER 'PV01'"):
        job_filler.fill(VARIANT)
    assert ("pick_pst_lib", "PV01") in calls
    assert calls.count(("save",)) == 1
    assert calls[-2:] == [("save",), ("pick_pst_lib", "PV01")]


@pytest.mark.parametrize("failure", [None, "fill_hardware_field", "import_ecr"])
def test_ecr_workflow_retains_number_and_stops_before_save_on_failure(failure):
    job_filler, calls, pages = filler({failure: False} if failure else {})
    pages.imported_ecr_number = "ECR123"
    variant = {
        **VARIANT,
        "hardware": {**VARIANT.get("hardware", {}), "ecr_number": "sheet ECR"},
        "ecr": {"change_engineer": "Engineer", "cost_allocation": "Allocation",
                "change_reason": "Reason", "ecr_notes": "Notes"},
    }
    if failure:
        with pytest.raises(RuntimeError, match="Could not fill"):
            job_filler.fill(variant)
        assert calls.count(("save",)) == (2 if failure == "import_ecr" else 0)
        assert "imported_ecr_number" not in variant
    else:
        assert job_filler.fill(variant) == []
        assert variant["imported_ecr_number"] == "ECR123"
        assert calls[calls.index(("import_ecr",)) - 1] == ("save",)
        assert calls.index(("import_ecr",)) < calls.index(("select_ecu_tab",)) < len(calls) - 1
        assert ("fill_hardware_field", "change_engineer", "Engineer") in calls
        assert ("fill_hardware_field", "cost_allocation", "Allocation") in calls
        assert ("fill_hardware_field", "ecr_number", "sheet ECR") not in calls


@pytest.mark.parametrize("pver", ["MG1CS022_62XSC_V020_CS", "MG1CS022_62XSC/V020_CS"])
@pytest.mark.parametrize("revision_count", [0, 1, 2])
@pytest.mark.parametrize("shows_warning", [False, True])
def test_pick_pst_lib_searches_and_selects_the_matching_project_identification(monkeypatch, pver, revision_count, shows_warning):
    from unittest.mock import Mock

    class Cell:
        def __init__(self, text):
            self.text = text

    class Row(Element):
        def __init__(self, identification):
            super().__init__()
            self.cells = [Cell(identification)]

        def find_elements(self, by, value):
            return self.cells if value == "td" else []

    class Search(Element):
        def send_keys(self, text):
            self.typed.append(text)

    class Dialog(Element):
        def __init__(self, rows):
            super().__init__(displayed=True)
            self.text = "PST_Lib and PVER selection"
            self.rows = rows
            self.search = Search()
            self.pick = Element()
            self.pick.click = self.close

        def close(self):
            self.clicks += 1
            self.displayed = False

        def find_element(self, by, value):
            if value.startswith("input[placeholder^="):
                return self.search
            if value.endswith('normalize-space(.)="Pick PST"]]'):
                return self.pick
            raise NoSuchElementException(value)

        def find_elements(self, by, value):
            return self.rows if value == "table tbody tr" else []

    matching = Row("MG1CS022_62XSC/V020_CS;0")
    other = Row("MG1CS022_62XSC/V020_CNT;0")
    prefix_match = Row("MG1CS022_62XSC/V020_CS_TEST;0")
    rows = [other, prefix_match]
    if revision_count:
        rows.append(matching)
    if revision_count == 2:
        rows.append(Row("MG1CS022_62XSC/V020_CS;1"))
    dialog = Dialog(rows)
    open_button = Element()
    open_button.click = lambda: None
    body = Element(children={
        './/button[.//span[normalize-space(.)="Pick PST_Lib"]]': open_button,
    })
    hardware = HardwareFields(Driver())
    hardware.sections["Ident Numbers"] = type(
        "SectionStub", (), {"expand": lambda _self: True, "body": lambda _self: body}
    )()
    warning = Mock()
    warning.text = "Data filled in by you will be saved before import. Do you want to continue?"
    warning.is_displayed.return_value = shows_warning
    yes = warning.find_element.return_value
    yes.click.side_effect = lambda: setattr(warning.is_displayed, "return_value", False)
    hardware.driver.find_elements = lambda by, value: [warning, dialog]

    class Wait:
        def __init__(self, _driver, _timeout, **_kwargs):
            pass

        def until(self, condition):
            for _ in range(3):
                result = condition(hardware.driver)
                if result:
                    return result
            raise TimeoutError("condition not met")

    monkeypatch.setattr(picker_module, "WebDriverWait", Wait)
    assert hardware.pick_pst_lib(pver) is (revision_count == 1)
    assert yes.click.call_count == (1 if shows_warning else 0)
    assert dialog.search.typed == ["MG1CS022_62XSC/V020_CS", Keys.ENTER]
    assert matching.clicks == (1 if revision_count == 1 else 0)
    assert other.clicks == 0 and prefix_match.clicks == 0
    assert dialog.clicks == (1 if revision_count == 1 else 0)


def test_extra_sheet_fields_without_webflow_controls_are_ignored():
    from autohub.services.MasterSheet.webflow_variants import webflow_variant_from_row

    variant = webflow_variant_from_row("PN", {"AB": "62XS", "AC": 120.0, "AJ": "Brazil", "CS": "DWG"})
    job_filler, calls, _ = filler()
    warnings = job_filler.fill(variant)
    assert ("fill_hardware_field", "vehicle_model", "62XS") in calls
    assert ("fill_hardware_field", "power", "120") in calls
    assert ("fill_hardware_field", "market", "Brazil") in calls
    assert warnings == []
    assert ("select_safety_monitoring_sw", False) in calls
    assert ("select_safety_calibration_response", False) in calls


def test_job_filler_uses_requested_priority_then_form_order():
    from autohub.core.webflow_fields import HARDWARE_FIELDS

    variant = {
        **VARIANT,
        "general": {**VARIANT["general"], "safety_calibration": False},
        "hardware": {key: key for _, key, _, _ in HARDWARE_FIELDS},
    }
    job_filler, calls, _ = filler()
    job_filler.fill(variant)
    field_calls = calls[3:]  # Select General, close menu, collapse information.
    assert [call[0] for call in field_calls[:8]] == [
        "select_delivery_type",
        "select_release_class",
        "select_release_scope",
        "select_limitations",
        "select_safety_monitoring_sw",
        "select_safety_calibration_response",
        "select_bosch_cal_data_response",
        "select_data_integration_response",
    ]
    hardware_calls = [call for call in field_calls if call[0] == "fill_hardware_field"]
    assert [call[1] for call in hardware_calls] == [
        "hardware_part_number", "development_number", "lead_plant",
        "vehicle_model", "engine_family", "power", "emission_norm", "immobilizer",
        "transmission", "displacement", "market", "model_year", "cylinders",
        "project_number_first", "project_number_second", "ecu_hardware_name",
        "customer_order_number", "customer_hardware_part_number",
        "car", "customer_name",
        "program_version", "data_version", "ecr_number",
    ]
    assert field_calls[8:10] == hardware_calls[:2]
    assert field_calls[10] == ("prepare_classification",)
    assert field_calls[11] == hardware_calls[2]
    assert field_calls[12:14] == [("save",), ("import_software_part_number",)]
    assert field_calls[14:11 + len(hardware_calls)] == hardware_calls[3:]
    assert field_calls[11 + len(hardware_calls):14 + len(hardware_calls)] == [
        ("save",), ("pick_pst_lib", "program_version"), ("select_ecu_tab",),
    ]
    assert calls[-1] == ("save",)


def test_imported_software_number_is_not_overwritten_from_sheet():
    variant = {**VARIANT, "hardware": {
        "lead_plant": "SaW", "software_part_number": "0", "customer_software_part_number": "OLD",
    }}
    job_filler, calls, pages = filler()
    pages.imported_software_part_number = "10SW072930"
    job_filler.fill(variant)
    lead_index = calls.index(("fill_hardware_field", "lead_plant", "SaW"))
    assert calls[lead_index + 1:lead_index + 3] == [("save",), ("import_software_part_number",)]
    assert ("fill_hardware_field", "software_part_number", "0") not in calls
    assert ("fill_hardware_field", "customer_software_part_number", "OLD") not in calls
    assert variant["imported_software_part_number"] == "10SW072930"


def test_blank_priority_fields_are_skipped_without_reordering_remaining_fields():
    variant = {
        **VARIANT,
        "hardware": {"hardware_part_number": "", "development_number": "DEV", "lead_plant": "", "vehicle_model": "Model"},
    }
    job_filler, calls, _ = filler()
    job_filler.fill(variant)
    assert [call for call in calls if call[0] == "fill_hardware_field"] == [
        ("fill_hardware_field", "development_number", "DEV"),
        ("fill_hardware_field", "vehicle_model", "Model"),
    ]
