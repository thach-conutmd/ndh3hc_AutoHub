"""Map existing Master Sheet payloads and match exports by Variant + SW Part Number."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from urllib.parse import quote, urlsplit

from autohub.core.normalizers import clean_text, normalize_part_number
from autohub.core.webflow_fields import HARDWARE_FIELDS
from autohub.core.webflow_links import is_link, job_number
from autohub.core.webflow_options import GENERAL_OPTION_FIELDS, normalize_option_value

from .xml_parser import ParameterMap, ParameterValue

VARIANT_PATH = "General/CustomerOrderNumber"
SOFTWARE_PATH = "General/SoftwarePartNumber"
JOB_PATH = "Job Information/JobId"

_HARDWARE_NAMES = {
    "hardware_part_number": "HardwarePartNumber", "development_number": "DevelopmentNumber",
    "lead_plant": "FactoryShort", "vehicle_model": "Model", "engine_family": "EngineFamily",
    "power": "Power", "emission_norm": "EmissionNorm", "immobilizer": "Immobilizer",
    "transmission": "Transmission", "displacement": "Displacement", "market": "Market",
    "model_year": "ModelYear", "cylinders": "NumberOfCylinders",
    "project_number_first": "CustomerCodeNumber", "project_number_second": "ProjectCodeNumber",
    "ecu_hardware_name": "ECU_HardwareName", "customer_order_number": "CustomerOrderNumber",
    "customer_hardware_part_number": "CustomerHardwarePartNumber",
    "customer_software_part_number": "CustomerSoftwarePartNumber", "car": "Car",
    "customer_name": "Customer_Name", "program_version": "ProgramVersion",
    "software_part_number": "SoftwarePartNumber", "data_version": "DataVersion", "ecr_number": "ECRNumber",
}
_GENERAL_PATHS = {
    "delivery_type": "General/DeliveryType_CF", "release_class": "General/ReleaseClass",
    "release_scope": "General/ReleaseScope", "limitations": "General/Limitations",
    "safety_monitoring": "Check/Safety_Monitoring_SW_by_RB",
    "safety_calibration": "Check/SafetyCalibrationResponsibility",
    "calibration": "Check/CalibrationResponsibility",
    "data_integration": "Check/DataIntegrationResponsibility",
}
_ECU_NAMES = {
    "indi_spec": "IndiSpec", "family_name": "FamilyName", "project_version": "FSWID_ProjectVersion",
    "program_version": "FSWID_ProgramVersion", "tp_level": "TP_Level",
}
_CUSTOMER_NAMES = {
    "ecu_default_id": "ECU_default_ID", "ecu_program_id": "ECU_progam_ID",
    "ecu_rewriting_id": "ECU_rewriting_ID", "security_coefficient": "SecurityCoefficient",
    "sw_version": "SW_Version", "component_id": "Component_ID",
}
OPTION_PATHS = {
    f"General/{_HARDWARE_NAMES[key]}": key
    for _, key, _, _ in HARDWARE_FIELDS if key in GENERAL_OPTION_FIELDS
}


def scalar(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = clean_text(value)
    return None if text in ("", "---") else text


def master_parameters(variant: Mapping) -> ParameterMap:
    """Map only known sheet-backed fields, never manufacture values for absent payload keys."""
    result: ParameterMap = {}
    for key, name in (("ecu_generation", "ECUGeneration"), ("brand", "Brand"), ("ecu_type", "ECUType")):
        if key in variant:
            result[f"Job Information/{name}"] = scalar(variant[key])
    for section, paths in (
        ("general", _GENERAL_PATHS),
        ("hardware", {key: f"General/{_HARDWARE_NAMES[key]}" for _, key, _, _ in HARDWARE_FIELDS}),
        ("ecu", {key: f"ECU/{name}" for key, name in _ECU_NAMES.items()}),
        ("customer", {key: f"Customer/{name}" for key, name in _CUSTOMER_NAMES.items()}),
    ):
        values = variant.get(section, {})
        for key, path in paths.items():
            if key not in values:
                continue
            value = scalar(values[key])
            if path in OPTION_PATHS and value:
                value = normalize_option_value(key, value)
                result[path] = tuple(sorted(set(value.split("|")))) or None
            else:
                result[path] = value
    for label, value in variant.get("unmapped_fields", {}).items():
        result[f"Master/{quote(label, safe=' _-().')}"] = scalar(value)
    return result


def variant_identity(variant: Mapping) -> tuple[str, str]:
    return _identity(variant.get("part_number"), variant.get("hardware", {}).get("software_part_number"))


def _identity(part: object, software: object) -> tuple[str, str]:
    return normalize_part_number(scalar(part)).upper(), normalize_part_number(scalar(software)).upper()


def export_identity(parameters: Mapping[str, ParameterValue]) -> tuple[str, str]:
    values = (parameters.get(VARIANT_PATH), parameters.get(SOFTWARE_PATH))
    if any(not isinstance(value, str) or not value.strip() or value.strip() in ("---", "0") for value in values):
        raise ValueError("XML must contain nonblank required variant matching fields.")
    return _identity(*values)


def match_variant(variants: Sequence[dict], parameters: Mapping[str, ParameterValue]) -> dict:
    identity = export_identity(parameters)
    matches = [variant for variant in variants if variant_identity(variant) == identity]
    if not matches:
        raise ValueError(f"No Master Sheet variant matches the exported identity for Variant {identity[0]}.")
    if len(matches) != 1:
        raise ValueError(f"Multiple Master Sheet variants match {identity[0]}; reload an unambiguous sheet.")
    return matches[0]


def validate_link(link: str) -> str:
    link = link.strip()
    try:
        parsed = urlsplit(link)
        number = job_number(parsed.path)
        valid = (
            is_link(link) and parsed.hostname and parsed.port != 0
            and not parsed.username and not parsed.password
            and parsed.path.rstrip("/").endswith(f"/app/ShowJob/{number}")
            and number is not None and number > 0
            and not any(character.isspace() for character in link)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Enter a valid WebFlow job link (http(s)://host/app/ShowJob/<job number>).")
    return link


def validate_export_link(parameters: Mapping[str, ParameterValue], link: str) -> None:
    validated = validate_link(link)
    exported_job = parameters.get(JOB_PATH)
    if exported_job is not None and str(exported_job).strip() != str(job_number(urlsplit(validated).path)):
        raise ValueError("The uploaded XML JobId does not match the WebFlow link.")
