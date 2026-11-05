"""Parses FEE_BLOCK_PROP entries of secumgr_fee_export XML (legacy: Split_Auto/secumgr_fee_export.py)."""
import xml.etree.ElementTree as ET

from autohub.services.HexdumpAnalyzer.exceptions import RangeNotFoundError


def get_block_line_ranges(xml_file: str) -> dict[int, dict[str, int]]:
    """Physical start/end line of every FEE_BLOCK_PROP, keyed by block index (from 0)."""
    ranges: dict[int, dict[str, int]] = {}
    start_line = None
    block_index = 0

    with open(xml_file, "r", encoding="ISO-8859-1") as f:
        for line_number, line in enumerate(f, start=1):
            if "<FEE_BLOCK_PROP>" in line:
                start_line = line_number
            elif "</FEE_BLOCK_PROP>" in line and start_line is not None:
                ranges[block_index] = {"start_line": start_line, "end_line": line_number}
                block_index += 1
                start_line = None

    return ranges


def parse_secumgr_fee(xml_file: str) -> dict[str, dict]:
    tree = ET.parse(xml_file)
    root = tree.getroot()
    line_ranges = get_block_line_ranges(xml_file)

    fee_dict: dict[str, dict] = {}
    for index, block in enumerate(root.findall(".//FEE_BLOCK_PROP")):
        block_data: dict = {}
        for child in block:
            block_data[child.tag] = child.text.strip() if child.text is not None else None

        key_id = block_data.get("FEE_BLOCK_CONFIGURED_NAME")
        if key_id is not None:
            block_data["start_line"] = line_ranges[index]["start_line"]
            block_data["end_line"] = line_ranges[index]["end_line"]
            fee_dict[key_id] = block_data

    return fee_dict


def find_key_secumgr_fee(xml_file: str, key_id: str) -> tuple[int, int]:
    fee_data = parse_secumgr_fee(xml_file)
    if key_id not in fee_data:
        raise RangeNotFoundError(f"Key {key_id!r} not found in secumgr_fee_export")
    return fee_data[key_id]["start_line"], fee_data[key_id]["end_line"]
