"""Parses '| Key: value' text blocks of a dflashBlockOverview file (legacy: Split_Auto/dflashBlockOverview.py)."""
import re

from autohub.services.HexdumpAnalyzer.exceptions import RangeNotFoundError

FIELD_RE = re.compile(r"^\|\s*([A-Za-z ]+?):\s*(.*)$")
BORDER_RE = re.compile(r"^\+-+\+\s*$")


def parse_blocks(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    blocks: list[dict] = []
    current: dict | None = None

    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip()

        match = FIELD_RE.match(line)
        if match:
            key, value = match.group(1).strip(), match.group(2).strip()
            if key == "Id":
                if current:
                    blocks.append(current)
                current = {"start_line": lineno - 1}
            if current is not None:
                current[key] = value
                current["end_line"] = lineno + 1
            continue

        if current is not None and BORDER_RE.match(line):
            blocks.append(current)
            current = None

    if current:
        blocks.append(current)
    return blocks


def to_dictionary(blocks: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for b in blocks:
        key = b.get("Name") or f"line_{b['start_line']}"
        orig, n = key, 1
        while key in result:
            n += 1
            key = f"{orig}_{n}"
        result[key] = b
    return result


def find_dflash_block(path: str, block_name: str) -> tuple[int, int]:
    blocks = to_dictionary(parse_blocks(path))
    if block_name not in blocks:
        raise RangeNotFoundError(f"Block {block_name!r} not found in dflash blocks")
    block = blocks[block_name]
    return block["start_line"], block["end_line"]
