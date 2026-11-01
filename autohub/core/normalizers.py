"""Pure text normalisers for values copied from the source documents into the Master Sheet."""
from __future__ import annotations

import re


def clean_text(value) -> str:
    return "" if value is None else str(value).strip()


def normalize_part_number(value) -> str:
    return "" if value is None else re.sub(r"\s+", "", str(value))


def normalize_key_text(value) -> str:
    return re.sub(r"\s+", " ", clean_text(value)).casefold()


def normalize_project_purpose(value) -> str:
    """Use the current purpose format for comparisons with legacy Master Sheet rows."""
    text = clean_text(value)
    match = re.fullmatch(r"(.+?)\s+for\s+(.+?)/(.+?)\s+event", text, re.IGNORECASE)
    if match:
        project, event, milestone = (part.strip() for part in match.groups())
        text = f"{project} - {event} Lot / {milestone}"
    return normalize_key_text(text)


def normalize_displacement(value) -> str:
    return re.sub(r"(?i)L$", "", clean_text(value))


def displacement_litres(cubic_centimetres) -> str:
    """Engine size in litres with one decimal (1199 -> "1.2", 1498 -> "1.5")."""
    return f"{int(str(cubic_centimetres).replace(',', '')) / 1000:.1f}"


def normalize_model_year(value) -> str:
    """A four-digit year: "27.0MY", "MY28" and "19" give 2027, 2028 and 2019; anything else is kept."""
    text = clean_text(value)
    match = re.fullmatch(r"(?:MY\s*)?(\d{2}|\d{4})(?:\.0+)?\s*(?:MY)?", text, re.IGNORECASE)
    if not match:
        return text
    year = match.group(1)
    return year if len(year) == 4 else f"20{year}"


def normalize_emission(value) -> str:
    text = re.sub(r"\s*\([^)]*\)\s*$", "", clean_text(value))
    return text.replace("-", " ")


def emission_standard(value) -> str:
    """A comparison key for an emission norm: "BS6 + RDE", "BS-6" and "Bharat Stage 6" all give "bs6"."""
    text = re.sub(r"(?i)bharat\s*stage", "bs", clean_text(value))
    return re.sub(r"[^a-z0-9]", "", re.sub(r"(?i)\+?\s*\bRDE\b", "", text).casefold())


def same_emission(first, second) -> bool:
    key = emission_standard(first)
    return bool(key) and key == emission_standard(second)


def tidy_emission(value) -> str:
    """"BS6 +RDE" -> "BS6 + RDE"."""
    return re.sub(r"\s*\+\s*", " + ", clean_text(value))


def immobilizer_label(generation) -> str:
    return f"IMMO{generation}"


def normalize_list(value) -> str:
    return re.sub(r",?\s*[\r\n]+\s*", "|", clean_text(value))


def normalize_program_version(value) -> str:
    text = clean_text(value)
    match = re.search(r"V\d+", text, re.IGNORECASE)
    return match.group(0).upper() if match else text


def title_status(value) -> str:
    text = clean_text(value)
    return text.title() if text else ""


def customer_hardware_part_number(part_number: str) -> str:
    return re.sub(r"0-M6$", "", part_number)


def development_number(value) -> str:
    """Bosch development number without its "-00" suffix (0261B00DA8-00 -> 0261B00DA8)."""
    return re.sub(r"-00$", "", clean_text(value))


_EXCEL_NUMBER_LOOKALIKE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)[eE][+-]?\d+$")


def needs_text_format(value) -> bool:
    """True for text Excel would turn into a number: leading zeros lost, or 4E5 read as 400000."""
    if not isinstance(value, str):
        return False
    return (len(value) > 1 and value.startswith("0")) or bool(_EXCEL_NUMBER_LOOKALIKE.match(value.strip()))


def ascii_hex(value) -> str:
    return "".join(f"{ord(character):02X}" for character in clean_text(value))


def hex_text(value) -> str:
    """A hex value read from a cell as text; drops the ".0" Excel adds to numbers (2025.0 -> 2025)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return re.sub(r"^([0-9A-Fa-f]+)\.0+$", r"\1", clean_text(value))


def parse_event(project_purpose) -> str:
    """Extract a project-version/event label from current or legacy Project Purpose text."""
    text = clean_text(project_purpose)
    match = re.fullmatch(r"(.+?)\s+-\s+(.+?)\s+Lot\s*/\s*.+", text, re.IGNORECASE)
    if not match:
        match = re.fullmatch(r"(.+?)\s+for\s+([^/]+?)(?:\s*/\s*.+?)?\s+event", text, re.IGNORECASE)
    return f"{match.group(1).strip()} - {match.group(2).strip()}" if match else text


def tp_level(rom_check, tuning_protection) -> str:
    """TP9 when both ROM Check and Tuning Protection are ACTIVE, otherwise TP3."""
    both_active = all(clean_text(value).upper() == "ACTIVE" for value in (rom_check, tuning_protection))
    return "TP9" if both_active else "TP3"
