"""Shared phase handling for Form B previews and exports."""
import re


def master_phase(variant: dict) -> str:
    event_name = str(variant.get("event_name") or "").strip()
    match = re.search(r"MP\d+", event_name, re.IGNORECASE)
    return match.group().upper() if match else ""


def manual_phase(value: str) -> str:
    value = value.strip().upper()
    return value if re.fullmatch(r"MP\d+", value) else ""


def form_b_phase(variant: dict) -> str:
    return master_phase(variant) or manual_phase(str(variant.get("form_b_phase") or ""))
