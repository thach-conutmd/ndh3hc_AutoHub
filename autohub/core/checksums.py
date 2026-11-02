"""CRC32 formatting and file helpers."""
from __future__ import annotations

import re
import zlib
from pathlib import Path
from typing import Any


def normalize_crc32(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        raise ValueError("CRC32 must be an eight-digit hexadecimal value.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    else:
        text = str(value).strip().upper()
        if text in ("-", "---", "N/A"):
            return ""
        if text.startswith("0X"):
            text = text[2:]
        if not re.fullmatch(r"[0-9A-F]{1,8}", text):
            raise ValueError(f"Invalid CRC32 value: {value!r}.")
        number = int(text, 16)
    if not 0 <= number <= 0xFFFFFFFF:
        raise ValueError(f"CRC32 value is out of range: {value!r}.")
    return f"{number:08X}"


def crc32_file(path: str | Path) -> str:
    checksum = 0
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum = zlib.crc32(chunk, checksum)
    return f"{checksum & 0xFFFFFFFF:08X}"
