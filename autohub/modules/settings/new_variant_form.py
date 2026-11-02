"""Editable defaults used when building new Master Sheet variants."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QFormLayout, QGroupBox, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from autohub.core.webflow_defaults import (
    WebFlowDefaults,
    editable_new_variant_defaults,
    new_variant_defaults,
)

_FIELD_GROUPS = (
    ("General", (
        ("ecu_generation", "ECU Generation"),
        ("brand", "Brand"),
        ("safety_monitoring", "Safety Monitoring SW by RB"),
        ("safety_calibration", "Safety Calibration Responsibility"),
        ("calibration", "Cal Data Responsibility"),
        ("data_integration", "Data Integration Responsibility"),
    )),
    ("Hardware/Plant", (
        ("project_number_first_part", "Project Number (1st part)"),
    )),
    ("ECU", (
        ("indi_spec_template", "Indi Spec template"),
    )),
    ("Customer", (
        ("ecu_default_id", "ECU Default ID"),
        ("ecu_rewriting_id", "ECU ReWrite ID"),
        ("sw_version", "SW Version"),
        ("sw_version_hardware", "SW Version ECU HW Name"),
        ("no_sw_version", "SW Version for other ECU HW"),
        ("customer_name", "Customer Name"),
        ("security_coefficient_hardware", "Security coefficient ECU HW Name"),
        ("security_coefficient", "Security coefficient"),
    )),
)


class NewVariantSettingsForm(QWidget):
    def __init__(self, defaults: WebFlowDefaults, parent: QWidget | None = None):
        super().__init__(parent)
        values = editable_new_variant_defaults(defaults)
        self._text_fields = {
            key: QLineEdit(str(values[key]))
            for _group, fields in _FIELD_GROUPS
            for key, _label in fields
            if key != "project_number_first_part" and not isinstance(values[key], bool)
        }
        self._boolean_fields = {
            key: QCheckBox(label)
            for group_name, fields in _FIELD_GROUPS if group_name == "General"
            for key, label in fields if isinstance(values[key], bool)
        }
        for key, checkbox in self._boolean_fields.items():
            checkbox.setChecked(values[key])
        self._project_number = QSpinBox()
        self._project_number.setRange(0, 999999)
        self._project_number.setValue(values["project_number_first_part"])
        self._groups = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        for group_name, fields in _FIELD_GROUPS:
            group = QGroupBox(group_name)
            form = QFormLayout(group)
            form.setHorizontalSpacing(20)
            form.setVerticalSpacing(12)
            for key, label in fields:
                if key in self._boolean_fields:
                    form.addRow(self._boolean_fields[key])
                else:
                    field = self._project_number if key == "project_number_first_part" else self._text_fields[key]
                    form.addRow(f"{label}:", field)
            layout.addWidget(group)
            self._groups[group_name] = group

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
