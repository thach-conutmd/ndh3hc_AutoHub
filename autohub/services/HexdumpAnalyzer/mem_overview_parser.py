"""Parses MEM_OVERVIEW_BLOCK entries of hsm_dflash XML (legacy: Split_Auto/hsm_dflash.py)."""
import xml.etree.ElementTree as ET

from autohub.services.HexdumpAnalyzer.exceptions import RangeNotFoundError


def get_block_line_ranges(xml_file: str) -> list[dict[str, int]]:
    """Physical start/end line of every MEM_OVERVIEW_BLOCK, in document order."""
    ranges: list[dict[str, int]] = []
    start_line = None

    with open(xml_file, "r", encoding="utf-8", errors="ignore") as f:
        for line_number, line in enumerate(f, start=1):
            if "<MEM_OVERVIEW_BLOCK>" in line:
                start_line = line_number
            elif "</MEM_OVERVIEW_BLOCK>" in line and start_line is not None:
                ranges.append({"START_LINE": start_line, "END_LINE": line_number})
                start_line = None

    return ranges


def parse_mem_overview_blocks(xml_file: str) -> dict[str, dict]:
    block_ranges = get_block_line_ranges(xml_file)
    tree = ET.parse(xml_file)
    root = tree.getroot()

    result: dict[str, dict] = {}
    for index, block in enumerate(root.findall(".//MEM_OVERVIEW_BLOCK")):
        block_dict: dict = {}
        for child in block:
            if child.tag == "MEM_OVERVIEW_BLOCK_DATA":
                block_dict["MEM_OVERVIEW_BLOCK_DATA"] = [
                    page.text.strip() for page in child.findall("MEM_OVERVIEW_PAGE_DATA") if page.text
                ]
            else:
                block_dict[child.tag] = child.text.strip() if child.text else None

        if index < len(block_ranges):
            block_dict["START_LINE"] = block_ranges[index]["START_LINE"]
            block_dict["END_LINE"] = block_ranges[index]["END_LINE"]

        block_id = block_dict.get("MEM_OVERVIEW_BLOCK_ID")
        if block_id:
            result[block_id] = block_dict

    return result


def find_mem_overview_block(xml_file: str, block_id: str) -> tuple[int, int]:
    mem_blocks = parse_mem_overview_blocks(xml_file)
    if block_id not in mem_blocks:
        raise RangeNotFoundError(f"Block ID {block_id!r} not found in mem_overview_blocks")
    block = mem_blocks[block_id]
    return block["START_LINE"], block["END_LINE"]
