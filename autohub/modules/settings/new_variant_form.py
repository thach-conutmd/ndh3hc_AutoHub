"""Editable defaults used when building new Master Sheet variants."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QFormLayout, QLineEdit, QSpinBox, QWidget

from autohub.core.webflow_defaults import (
    WebFlowDefaults,
    editable_new_variant_defaults,
    new_variant_defaults,
)

_TEXT_FIELDS = (
    ("ecu_generation", "ECU Generation"),
    ("brand", "Brand"),
    ("delivery_type", "Delivery Type"),
    ("release_class", "Release Class"),
    ("release_scope", "Release Scope"),
    ("limitations", "Limitations"),
    ("ecu_default_id", "ECU Default ID"),
    ("ecu_rewriting_id", "ECU ReWrite ID"),
    ("sw_version", "SW Version"),
    ("sw_version_hardware", "SW Version ECU HW Name"),
    ("no_sw_version", "SW Version for other ECU HW"),
    ("indi_spec_template", "Indi Spec template"),
    ("customer_name", "Customer Name"),
    ("security_coefficient_hardware", "Security coefficient ECU HW Name"),
    ("security_coefficient", "Security coefficient"),
)
_BOOLEAN_FIELDS = (
    ("safety_monitoring", "Safety Monitoring SW by RB"),
    ("safety_calibration", "Safety Calibration Responsibility"),
    ("calibration", "Cal Data Responsibility"),
    ("data_integration", "Data Integration Responsibility"),
)


class NewVariantSettingsForm(QWidget):
    def __init__(self, defaults: WebFlowDefaults, parent: QWidget | None = None):
        super().__init__(parent)
        values = editable_new_variant_defaults(defaults)
        self._text_fields = {key: QLineEdit(str(values[key])) for key, _label in _TEXT_FIELDS}
        self._boolean_fields = {
            key: QCheckBox(label) for key, label in _BOOLEAN_FIELDS
        }
        for key, checkbox in self._boolean_fields.items():
            checkbox.setChecked(values[key])
        self._project_number = QSpinBox()
        self._project_number.setRange(0, 999999)
        self._project_number.setValue(values["project_number_first_part"])

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(12)
        for key, label in _TEXT_FIELDS:
            form.addRow(f"{label}:", self._text_fields[key])
        form.addRow("Project Number (1st part):", self._project_number)
        for key, _label in _BOOLEAN_FIELDS:
            form.addRow(self._boolean_fields[key])

    def values(self) -> dict:
        return {
            **{key: field.text().strip() for key, field in self._text_fields.items()},
            "project_number_first_part": self._project_number.value(),
            **{key: checkbox.isChecked() for key, checkbox in self._boolean_fields.items()},
        }

    def restore(self, values: dict) -> None:
        defaults = editable_new_variant_defaults(new_variant_defaults({
            "new_variant_defaults": values,
        }))
        for key, field in self._text_fields.items():
            field.setText(defaults[key])
        self._project_number.setValue(defaults["project_number_first_part"])
        for key, checkbox in self._boolean_fields.items():
            checkbox.setChecked(defaults[key])
