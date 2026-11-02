from autohub.core.webflow_environment import ENVIRONMENT_URLS, selected_environment, webflow_base_url
from autohub.modules.creation.service import WebFlowConfig
from autohub.modules.settings.creation_form import CreationSettingsForm, load_config

PRODUCTION = "https://rb-webflow.bosch.com/app/dashboard"
ACCEPTANCE = "https://rb-pde-int.bosch.com:8881/app/dashboard"


def test_environment_urls_and_defaults():
    assert ENVIRONMENT_URLS == {"Production": PRODUCTION, "Acceptance": ACCEPTANCE}
    assert webflow_base_url({}) == PRODUCTION
    assert webflow_base_url({"webflow_environment": "Acceptance"}) == ACCEPTANCE
    assert webflow_base_url({"webflow_environment": "bogus"}) == PRODUCTION
    assert selected_environment({"webflow_base_url": ACCEPTANCE}) == "Acceptance"  # settings saved before the selector
    assert selected_environment({"webflow_base_url": "https://custom/x"}) == "Production"


def test_selector_is_exclusive_highlights_and_saves_environment_and_url(qapp):
    form = CreationSettingsForm(WebFlowConfig("", PRODUCTION, "", ""))
    try:
        buttons = {b.text(): b for b in form._environment_buttons.buttons()}
        assert list(buttons) == ["Production", "Acceptance"] and buttons["Production"].isChecked()
        assert "Selected: Production" in form._environment_summary.text()
        buttons["Acceptance"].click()
        assert not buttons["Production"].isChecked() and form.environment() == "Acceptance"
        values = form.values()
        assert values["webflow_environment"] == "Acceptance" and values["webflow_base_url"] == ACCEPTANCE
        form.restore({**values, "webflow_environment": "Production", "tool_version": "", "routing": "",
                      "change_engineer": "", "cost_allocation": "", "change_reason": ""})
        assert buttons["Production"].isChecked()
    finally:
        form.close(); form.deleteLater()


def test_load_config_uses_selected_environment():
    class Store:
        def __init__(self, data): self.data = data
        def load(self): return self.data
    assert load_config(Store({})).base_url == PRODUCTION
    assert load_config(Store({"webflow_environment": "Acceptance"})).base_url == ACCEPTANCE
