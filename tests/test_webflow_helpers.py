import pytest
from unittest.mock import Mock
from selenium.common.exceptions import TimeoutException

from autohub.services.WebFlow import GeneralTab as general_tab_module
from autohub.services.WebFlow.GeneralTab import (
    GeneralTab,
    _checkbox_value,
    _click_count,
)
from autohub.services.WebFlow import Actions as actions_module
from autohub.services.WebFlow.Actions import Actions
from autohub.services.WebFlow.dropdown import read_options
from autohub.services.WebFlow.toast import toast_severity


def test_toast_severity_from_the_primeng_class():
    assert toast_severity("ng-trigger p-toast-message-success p-toast-message") == "success"
    assert toast_severity("p-toast-message-error p-toast-message") == "error"
    assert toast_severity("p-toast-message") is None and toast_severity(None) is None


@pytest.mark.parametrize(
    ("toast_class", "toast_text", "expected"),
    [
        ("p-toast-message-success", "Success Message Saved successfully", True),
        ("p-toast-message-error", "Error Message Save failed", False),
        ("p-toast-message-success", "Success Message Unexpected confirmation", False),
        (None, "", False),
    ],
)
def test_save_waits_for_confirmation_without_waiting_for_activity_indicator(
    monkeypatch, toast_class, toast_text, expected
):
    toast = Mock()
    toast.get_attribute.return_value = toast_class
    toast.text = toast_text
    driver = Mock()
    driver.find_elements.return_value = [toast]
    button = Mock()
    button.get_attribute.return_value = ""
    actions = Actions(driver)
    actions.get_button_by_text = Mock(return_value=button)
    waits = []

    class Wait:
        def __init__(self, _driver, timeout):
            waits.append(timeout)

        def until(self, condition):
            result = condition(driver)
            if not result:
                raise TimeoutException()
            return result

    monkeypatch.setattr(actions_module, "WebDriverWait", Wait)
    monkeypatch.setattr(
        actions_module, "wait_until_idle", Mock(side_effect=AssertionError("unexpected idle wait"))
    )
    collapse = Mock(return_value=True)
    monkeypatch.setattr(actions_module.Information, "collapse_job_information", collapse)

    assert actions.save() is expected
    button.click.assert_called_once_with()
    assert waits == [actions_module.Constants.SAVE_TIMEOUT]
    assert collapse.call_count == (1 if expected else 0)


@pytest.mark.parametrize("disabled_state", ["class", "native", "aria-disabled", "ng-reflect-disabled"])
def test_gray_save_is_not_clicked_or_collapsed(monkeypatch, disabled_state):
    button = Mock()
    button.is_enabled.return_value = disabled_state != "native"
    button.get_attribute.side_effect = lambda attr: (
        "action disabled" if attr == "class" and disabled_state == "class"
        else "true" if attr == disabled_state else None
    )
    actions = Actions(Mock())
    actions.get_button_by_text = Mock(return_value=button)
    actions._saved_toast_shown = Mock()
    collapse = Mock()
    monkeypatch.setattr(actions_module.Information, "collapse_job_information", collapse)

    assert actions.save()
    button.click.assert_not_called()
    actions._saved_toast_shown.assert_not_called()
    collapse.assert_not_called()


@pytest.mark.parametrize("collapsed", [True, False])
def test_collapse_runs_only_after_confirmed_save(monkeypatch, collapsed):
    events = []
    button = Mock()
    button.get_attribute.return_value = None
    button.click.side_effect = lambda: events.append("click")
    actions = Actions(Mock())
    actions.get_button_by_text = Mock(return_value=button)
    actions._saved_toast_shown = Mock(side_effect=lambda: events.append("saved") or True)
    monkeypatch.setattr(
        actions_module.Information, "collapse_job_information",
        lambda _self: events.append("collapse") or collapsed,
    )
    assert actions.save() is collapsed
    assert events == ["click", "saved", "collapse"]


class El:
    def __init__(self, attrs=None, children=None, displayed=True):
        self.attrs, self.children = attrs or {}, children or {}
        self.displayed = displayed

    def get_attribute(self, name):
        return self.attrs.get(name)

    def find_element(self, by, value):
        return self.children[value][0]

    def find_elements(self, by, value):
        return self.children.get(value, [])


class Driver:
    def __init__(self, wrapper):
        self.wrapper = wrapper
        self.implicit = [1]

    def implicitly_wait(self, seconds):
        self.implicit.append(seconds)

    def find_element(self, by, value):
        if self.wrapper is None:
            raise LookupError(value)
        return self.wrapper

    def find_elements(self, by, value):
        return [] if self.wrapper is None else [self.wrapper]


def test_every_item_is_read_in_one_query_without_the_old_item_cap():
    items = [El({"aria-label": f"opt{n}"}) for n in range(40)]
    wrapper = El(children={"ul": [El({"id": "x_list"}, {"li[aria-label]": items})]})
    driver = Driver(wrapper)
    options = read_options(driver, "p-dropdown-items-wrapper", 15)
    assert len(options) == 40 and options["opt39"] is items[39]
    assert driver.implicit[-1] == 1 and 0 in driver.implicit  # implicit wait restored afterwards


def test_no_open_list_gives_none():
    assert read_options(Driver(None), "w", 5) is None


def test_checkbox_value_uses_aria_checked_and_keeps_icon_fallback():
    assert _checkbox_value(El({"aria-checked": "true"})) is True
    assert _checkbox_value(El({"aria-checked": "false"})) is None
    assert _checkbox_value(El({"aria-checked": "mixed"})) is None

    unchecked = El({"aria-checked": "false"}, children={'timesicon[data-pc-section="uncheckIcon"]': [El()]})
    assert _checkbox_value(unchecked) is False


@pytest.mark.parametrize(
    ("current", "target", "clicks"),
    [(False, False, 0), (False, True, 1), (True, False, 1), (True, None, 2), (None, False, 2)],
)
def test_tristate_checkbox_click_count(current, target, clicks):
    assert _click_count(current, target) == clicks


def test_disabled_checkbox_mismatch_is_reported_without_clicking(monkeypatch):
    class Element:
        def __init__(self, attrs=None, children=None):
            self.attrs = attrs or {}
            self.children = children or {}
            self.clicks = 0

        def get_attribute(self, name):
            return self.attrs.get(name)

        def find_element(self, by, value):
            return self.children[value]

        def click(self):
            self.clicks += 1

    checkbox = Element(
        {"aria-checked": "false", "class": "p-checkbox-box p-disabled"},
        children={'timesicon[data-pc-section="uncheckIcon"]': Element()},
    )
    host = Element({"ng-reflect-disabled": "true"})
    form = Element(children={
        "div[role=\"checkbox\"]": checkbox,
        "p-tristatecheckbox": host,
    })
    title = Element(children={"..": form})

    class Wait:
        def until(self, _condition):
            return title

    monkeypatch.setattr(general_tab_module.EC, "presence_of_element_located", lambda _locator: None)
    monkeypatch.setattr(general_tab_module, "WebDriverWait", lambda *_args: Wait())

    tab = GeneralTab(object())
    tab.expand_configurator_items = lambda: True
    assert tab.select_safety_monitoring_sw(True) is True
    assert checkbox.clicks == 0
    assert len(tab.skipped_fields) == 1
    assert "current value False" in tab.skipped_fields[0]
    assert "requested True" in tab.skipped_fields[0]


@pytest.mark.parametrize("method", [
    "select_safety_monitoring_sw", "select_safety_calibration_response",
    "select_bosch_cal_data_response", "select_data_integration_response",
])
@pytest.mark.parametrize("initial", [None, True, False])
@pytest.mark.parametrize("requested", [True, False, None])
def test_general_checkbox_reaches_nonblank_state(monkeypatch, method, initial, requested):
    checkbox = Mock()
    state = [initial]
    clicks = []

    def attribute(name):
        return ("true" if state[0] is True else "false") if name == "aria-checked" else None

    def icon(_by, selector):
        if state[0] is True and selector.startswith("checkicon"):
            return object()
        if state[0] is False and selector.startswith("timesicon"):
            return object()
        raise LookupError(selector)

    def click():
        clicks.append(state[0])
        state[0] = {None: True, True: False, False: None}[state[0]]

    checkbox.get_attribute.side_effect = attribute
    checkbox.find_element.side_effect = icon
    checkbox.click.side_effect = click
    form, title = Mock(), Mock()
    form.find_element.return_value = checkbox
    title.find_element.return_value = form
    wait = Mock()
    wait.until.return_value = title
    monkeypatch.setattr(general_tab_module, "WebDriverWait", lambda *_args: wait)
    monkeypatch.setattr(general_tab_module, "_checkbox_is_disabled", lambda *_args: False)
    monkeypatch.setattr(general_tab_module.time, "sleep", lambda *_args: None)
    tab = GeneralTab(object())
    tab.expand_configurator_items = lambda: True
    assert getattr(tab, method)(requested) is True
    target = False if requested is None else requested
    assert state[0] is target
    if initial is None:
        assert len(clicks) == (1 if target else 2)


def test_disabled_blank_checkbox_fails_instead_of_being_skipped(monkeypatch):
    wait = Mock()
    monkeypatch.setattr(general_tab_module, "WebDriverWait", lambda *_args: wait)
    monkeypatch.setattr(general_tab_module, "_checkbox_value", lambda *_args: None)
    monkeypatch.setattr(general_tab_module, "_checkbox_is_disabled", lambda *_args: True)
    tab = GeneralTab(object())
    tab.expand_configurator_items = lambda: True
    assert tab.select_safety_monitoring_sw(False) is False
    wait.until.return_value.find_element.return_value.find_element.return_value.click.assert_not_called()
