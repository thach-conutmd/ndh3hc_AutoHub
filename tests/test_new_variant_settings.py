from autohub.core.settings_keys import NEW_VARIANT_DEFAULTS_KEY
from autohub.modules.settings.ui import SettingsWidget
from tests.fakes import FakeDialogs, MemorySettings


def test_new_variant_defaults_are_saved_and_restored(qapp):
    settings = MemorySettings()
    page = SettingsWidget(settings, FakeDialogs())
    changed = []
    page.settingsChanged.connect(changed.append)
    page._new_variant_defaults._text_fields["brand"].setText("Acme")
    page._new_variant_defaults._boolean_fields["safety_monitoring"].setChecked(False)
    page._new_variant_defaults._project_number.setValue(271)
    assert page._apply.isEnabled()

    page._on_apply()

    saved = settings.load()[NEW_VARIANT_DEFAULTS_KEY]
    assert saved["brand"] == "Acme"
    assert saved["safety_monitoring"] is False
    assert saved["project_number_first_part"] == 271
    assert "delivery_type" not in saved
    assert page._new_variant_defaults._groups.keys() == {"General", "Hardware/Plant", "ECU", "Customer"}
    assert NEW_VARIANT_DEFAULTS_KEY in changed[0]
    restored = SettingsWidget(settings, FakeDialogs())
    assert restored._new_variant_defaults.values() == saved


def test_discarding_new_variant_default_edits_restores_applied_values(qapp):
    settings = MemorySettings()
    page = SettingsWidget(settings, FakeDialogs(table_answer=False))
    page._new_variant_defaults._text_fields["brand"].setText("Acme")

    assert page.confirm_leave()
    assert page._new_variant_defaults.values()["brand"] == "Honda"
    assert not page._apply.isEnabled()
