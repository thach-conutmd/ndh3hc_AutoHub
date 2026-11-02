"""Fixed WebFlow job values for Honda MG1 variants, in one place so a change touches one file."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Mapping

from autohub.core.settings_keys import NEW_VARIANT_DEFAULTS_KEY

_EDITABLE_DEFAULTS = (
    "ecu_generation", "brand",
    "safety_monitoring", "safety_calibration", "calibration", "data_integration",
    "ecu_default_id", "ecu_rewriting_id", "sw_version", "sw_version_hardware", "no_sw_version",
    "indi_spec_template", "project_number_first_part", "customer_name",
    "security_coefficient_hardware", "security_coefficient",
)


@dataclass(frozen=True)
class WebFlowDefaults:
    ecu_generation: str = "MG1"
    brand: str = "Honda"
    safety_monitoring: bool = True
    safety_calibration: bool = False
    calibration: bool = True
    data_integration: bool = True
    tp_level: str = "3"
    ecu_default_id: str = "FFFFEFFFFFEE00000000"
    ecu_rewriting_id: str = "00000000"
    sw_version: str = "01"
    sw_version_hardware: str = "MG1CS022"  # the only ECU type that has a SW version
    no_sw_version: str = "-"
    component_id: str = "-"
    indi_spec_template: str = "Honda_{hardware}{type}_IndiSpec_01"
    project_number_first_part: int = 159
    customer_name: str = "HONDA"
    security_coefficient_hardware: str = "MG1CS022"
    security_coefficient: str = "FFFFFFFFFFFF"

    def general(self) -> dict:
        return {
            "safety_monitoring": self.safety_monitoring,
            "safety_calibration": self.safety_calibration,
            "calibration": self.calibration,
            "data_integration": self.data_integration,
        }

    def sw_version_for(self, hardware: str) -> str:
        return self.sw_version if hardware.strip().upper() == self.sw_version_hardware else self.no_sw_version

    def indi_spec(self, hardware: str) -> str:
        ecu_type = "_CS" if hardware.find("CS") != -1 else ""
        return self.indi_spec_template.format(hardware=hardware, type=ecu_type) if hardware else ""


WEBFLOW_DEFAULTS = WebFlowDefaults()


def new_variant_defaults(settings: Mapping) -> WebFlowDefaults:
    """Return saved, validated New variants defaults, falling back field-by-field to current values."""
    saved = settings.get(NEW_VARIANT_DEFAULTS_KEY, {})
    if not isinstance(saved, Mapping):
        return WEBFLOW_DEFAULTS
    current = asdict(WEBFLOW_DEFAULTS)
    for key in _EDITABLE_DEFAULTS:
        value = saved.get(key)
        default = current[key]
        if isinstance(default, bool):
            if type(value) is bool:
                current[key] = value
        elif isinstance(default, int):
            if type(value) is int:
                current[key] = value
        elif isinstance(value, str):
            current[key] = value
    return replace(WEBFLOW_DEFAULTS, **{key: current[key] for key in _EDITABLE_DEFAULTS})


def editable_new_variant_defaults(defaults: WebFlowDefaults) -> dict:
    return {key: getattr(defaults, key) for key in _EDITABLE_DEFAULTS}
