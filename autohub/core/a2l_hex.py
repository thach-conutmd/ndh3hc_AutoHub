"""Read an A2L-addressed ASCII component ID from an Intel HEX calibration."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from autohub.core.normalizers import normalize_part_number

DEFAULT_COMP_ID_SYMBOL = "I14229_numCompID_CA"
_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[^\s]+')
_COMMENTS = re.compile(r"/\*.*?\*/|//[^\r\n]*", re.DOTALL)


def files_in_folder(folder: str | Path) -> tuple[Path, Path]:
    path = Path(folder)
    if not path.is_dir():
        raise ValueError(f"Calibration folder not found: {path}")
    a2l_files = [item for item in path.iterdir() if item.is_file() and item.suffix.casefold() == ".a2l"]
    hex_files = [item for item in path.iterdir() if item.is_file() and item.suffix.casefold() == ".hex"]
    if len(a2l_files) != 1:
        raise ValueError(f"Calibration folder must contain exactly one .a2l file (found {len(a2l_files)}).")
    if len(hex_files) != 1:
        raise ValueError(f"Calibration folder must contain exactly one .hex file (found {len(hex_files)}).")
    return a2l_files[0], hex_files[0]


def _a2l_address(a2l_path: Path, symbol: str) -> int:
    text = _COMMENTS.sub("", a2l_path.read_text(encoding="latin-1"))
    tokens = _TOKEN.findall(text)
    matches: list[tuple[str, list[str]]] = []
    for start in range(len(tokens) - 2):
        if tokens[start] != "/begin" or tokens[start + 1] not in {"CHARACTERISTIC", "MEASUREMENT"}:
            continue
        kind = tokens[start + 1]
        depth = 1
        end = start + 2
        while end < len(tokens) and depth:
            if tokens[end] == "/begin":
                depth += 1
            elif tokens[end] == "/end":
                depth -= 1
            end += 1
        if depth:
            raise ValueError(f"Unclosed {kind} block in {a2l_path.name}.")
        body = tokens[start + 2 : end - 1]
        if body and body[0] == symbol:
            matches.append((kind, body))
    if len(matches) != 1:
        raise ValueError(f"A2L symbol '{symbol}' must occur exactly once (found {len(matches)}).")

    kind, body = matches[0]
    address = None
    if kind == "CHARACTERISTIC" and len(body) >= 4:
        address = body[3]
    elif kind == "MEASUREMENT":
        for index, token in enumerate(body[:-1]):
            if token == "ECU_ADDRESS":
                address = body[index + 1]
                break
    if address is None:
        raise ValueError(f"A2L symbol '{symbol}' has no supported ECU address.")
    try:
        return int(address, 0)
    except ValueError as error:
        raise ValueError(f"A2L symbol '{symbol}' has an invalid ECU address: {address}.") from error


def _intel_hex_data(hex_path: Path, target_address: int, target_length: int) -> bytes:
    target = bytearray(target_length)
    found = bytearray(target_length)
    base_address = 0
    has_data = False
    try:
        lines = hex_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"Could not read Intel HEX file {hex_path.name}: {error}") from error
    for line_number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            if not line.startswith(":"):
                raise ValueError("missing ':'")
            record = bytes.fromhex(line[1:])
            if len(record) < 5 or (sum(record) & 0xFF):
                raise ValueError("invalid length or checksum")
            size = record[0]
            address = int.from_bytes(record[1:3], "big")
            record_type = record[3]
            data = record[4:-1]
            if len(data) != size:
                raise ValueError("byte count does not match record")
            if record_type == 0x00:
                has_data = has_data or bool(data)
                record_start = base_address + address
                overlap_start = max(target_address, record_start)
                overlap_end = min(target_address + target_length, record_start + len(data))
                if overlap_start < overlap_end:
                    target_start = overlap_start - target_address
                    record_offset = overlap_start - record_start
                    count = overlap_end - overlap_start
                    target[target_start : target_start + count] = data[record_offset : record_offset + count]
                    found[target_start : target_start + count] = b"\x01" * count
            elif record_type == 0x01:
                if size:
                    raise ValueError("EOF record must not contain data")
                break
            elif record_type == 0x02:
                if size != 2:
                    raise ValueError("extended segment address must contain two bytes")
                base_address = int.from_bytes(data, "big") << 4
            elif record_type == 0x04:
                if size != 2:
                    raise ValueError("extended linear address must contain two bytes")
                base_address = int.from_bytes(data, "big") << 16
            elif record_type in (0x03, 0x05):
                if size != 4:
                    raise ValueError("start address record must contain four bytes")
            else:
                raise ValueError(f"unsupported record type 0x{record_type:02X}")
        except ValueError as error:
            raise ValueError(f"Invalid Intel HEX record at line {line_number}: {error}.") from error
    if not has_data:
        raise ValueError(f"Intel HEX file {hex_path.name} contains no data records.")
    if any(value == 0 for value in found):
        raise ValueError(f"Intel HEX data is missing the A2L symbol at 0x{target_address:X}.")
    return bytes(target)


@dataclass(frozen=True)
class A2LHexCalibration:
    hex_filename: str
    symbol: str
    address: int
    id_bytes: bytes

    def read_component_id(self, expected_length: int) -> str:
        if expected_length < 1:
            raise ValueError("Expected component ID length must be positive.")
        if expected_length > len(self.id_bytes):
            raise ValueError(f"HEX value for '{self.symbol}' is shorter than the expected ID.")
        raw = self.id_bytes[:expected_length]
        try:
            value = raw.rstrip(b"\x00\xff").decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise ValueError(f"Intel HEX value for '{self.symbol}' is not ASCII text.") from error
        if not value:
            raise ValueError(f"Intel HEX value for '{self.symbol}' is empty.")
        return value


def load_calibration_folder(
    folder: str | Path, symbol: str, expected_length: int
) -> A2LHexCalibration:
    a2l_path, hex_path = files_in_folder(folder)
    address = _a2l_address(a2l_path, symbol.strip())
    id_bytes = _intel_hex_data(hex_path, address, expected_length)
    return A2LHexCalibration(hex_path.name, symbol, address, id_bytes)


def read_component_id(folder: str | Path, symbol: str, expected_length: int) -> tuple[str, str]:
    """Return the hex filename and ASCII ID bytes at the A2L symbol address."""
    calibration = load_calibration_folder(folder, symbol, expected_length)
    return calibration.hex_filename, calibration.read_component_id(expected_length)


def component_id_matches(value: str, expected: str) -> bool:
    return normalize_part_number(value).casefold() == normalize_part_number(expected).casefold()
