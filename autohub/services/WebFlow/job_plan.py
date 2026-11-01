"""Build ordered job-fill steps without executing browser actions."""
from __future__ import annotations

from typing import Any, Protocol

from autohub.core.webflow_fields import HARDWARE_FIELDS

from .Actions import save_before_action
from .step_log import Step

ECU_FIELDS = (
    ("fill_indi_spec", "indi_spec"),
    ("fill_family_name", "family_name"),
    ("fill_project_version", "project_version"),
    ("fill_program_version", "program_version"),
    ("select_tp_level", "tp_level"),
)
CUSTOMER_FIELDS = (
    ("fill_ecu_default_id", "ecu_default_id"),
    ("fill_ecu_program_id", "ecu_program_id"),
    ("fill_ecu_rewriting_id", "ecu_rewriting_id"),
    ("fill_security_coefficient", "security_coefficient"),
    ("fill_sw_version", "sw_version"),
    ("fill_component_id", "component_id"),
)
GENERAL_FIELDS = (
    ("delivery type", "select_delivery_type", "delivery_type"),
    ("release class", "select_release_class", "release_class"),
    ("release scope", "select_release_scope", "release_scope"),
    ("limitations", "select_limitations", "limitations"),
    ("safety monitoring SW", "select_safety_monitoring_sw", "safety_monitoring"),
    ("safety calibration response", "select_safety_calibration_response", "safety_calibration"),
    ("Bosch calibration data response", "select_bosch_cal_data_response", "calibration"),
    ("data integration response", "select_data_integration_response", "data_integration"),
)
_GENERAL_CHECKBOX_KEYS = {"safety_monitoring", "safety_calibration", "calibration", "data_integration"}


class StepPlan(Protocol):
    def steps(self, variant: dict) -> list[Step]: ...


class JobPlan:
    def __init__(self, side_menu_bar: Any, body: Any):
        self.side_menu_bar = side_menu_bar
        self.body = body

    def steps(self, variant: dict) -> list[Step]:
        general, ecu_tab, customer_tab = self.body.tab.generaltab, self.body.tab.ecutab, self.body.tab.customertab
        steps: list[Step] = [
            ("Close the side menu", self.side_menu_bar.close_menubar),
            ("Collapse the job information", self.body.information.collapse_job_information),
        ]
        for label, method, key in GENERAL_FIELDS:
            value = variant["general"].get(key)
            if key in _GENERAL_CHECKBOX_KEYS and value in (None, ""):
                value = False
            if value not in (None, ""):
                steps.append((f"General: {label} = {display_value(value)}", getattr(general, method), value))
        for _, key, label, _ in HARDWARE_FIELDS:
            if key == "software_part_number":
                continue  # WebFlow allocates this number through Import from pool.
            if key == "ecr_number" and variant.get("ecr"):
                continue  # ECR Import supplies this read-only field.
            if key == "customer_software_part_number" and variant.get("hardware", {}).get("lead_plant"):
                continue  # The pool import copies its allocated number into this control.
            value = variant.get("hardware", {}).get(key)
            if value:
                if key == "lead_plant":
                    steps.append((
                        "General: Number of variants = 1; Time limitation required = False (X); "
                        "Successor to Time Limited Delivery ECU = False (X)",
                        general.prepare_classification,
                    ))
                steps.append((f"General: {label} = {value}", general.fill_hardware_field, key, value))
                if key == "lead_plant":
                    steps.append((
                        "Save the job before Import from pool",
                        save_before_action, self.body.actions.save, "Import from pool",
                    ))
                    steps.append(("General: Import software part number from pool", general.import_software_part_number))
        pver = variant.get("hardware", {}).get("program_version")
        if pver:
            steps.append((
                "Save the job before Pick PST_Lib",
                save_before_action, self.body.actions.save, "Pick PST_Lib",
            ))
            steps.append((f"General: Pick PST_Lib for PVER {pver}", general.pick_pst_lib, pver))
        if variant.get("ecr"):
            for key, value in variant["ecr"].items():
                steps.append((f"General: ECR {key} = {value}", general.fill_hardware_field, key, value))
            steps.append((
                "Save the job before ECR Import",
                save_before_action, self.body.actions.save, "ECR Import",
            ))
            steps.append(("General: ECR Import", general.import_ecr))
        steps.append(("Select the ECU tab", ecu_tab.select_ecu_tab))
        steps += _optional_steps("ECU", ecu_tab, ECU_FIELDS, variant["ecu"])
        steps.append(("Select the Customer tab", customer_tab.select_customer_tab))
        steps += _optional_steps("Customer", customer_tab, CUSTOMER_FIELDS, variant["customer"])
        steps.append(("Save the job", self.body.actions.save))
        return steps


def display_value(value: Any) -> str:
    if value is None:
        return "(none)"
    if value == "":
        return "(empty)"
    return str(value)


def describe_values(variant: dict) -> str:
    return "; ".join(
        f"{title}[" + ", ".join(f"{key}={display_value(value)}" for key, value in variant.get(section, {}).items()) + "]"
        for title, section in (("General", "general"), ("Hardware/Plant", "hardware"), ("ECU", "ecu"), ("Customer", "customer"))
    )


def _optional_steps(section: str, page: Any, fields: tuple, values: dict) -> list[Step]:
    return [
        (f"{section}: {key} = {values[key]}", getattr(page, method), values[key])
        for method, key in fields if values.get(key)
    ]
