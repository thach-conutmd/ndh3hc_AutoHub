"""Read a length-prefixed ASCII component ID from an A2L-addressed Intel HEX value block."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

DEFAULT_COMP_ID_SYMBOL = "I14229_numCompID_CA"
_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[^\s]+')
_COMMENTS = re.compile(r"/\*.*?\*/|//[^\r\n]*", re.DOTALL)


def files_in_folder(folder: str | Path) -> tuple[Path, list[Path]]:
    path = Path(folder)
    if not path.is_dir():
        raise ValueError(f"Calibration folder not found: {path}")
    a2l_files = sorted(
        item for item in path.iterdir() if item.is_file() and item.suffix.casefold() == ".a2l"
    )
    hex_files = sorted(
        item for item in path.iterdir() if item.is_file() and item.suffix.casefold() == ".hex"
    )
    if len(a2l_files) != 1:
        raise ValueError(f"Calibration folder must contain exactly one .a2l file (found {len(a2l_files)}).")
    if not hex_files:
        raise ValueError("Calibration folder must contain at least one .hex file.")
    return a2l_files[0], hex_files


def _a2l_symbol_info(a2l_path: Path, symbol: str) -> tuple[int, int]:
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
        address = int(address, 0)
    except ValueError as error:
        raise ValueError(f"A2L symbol '{symbol}' has an invalid ECU address: {address}.") from error

    element_count = None
    for index, token in enumerate(body[:-1]):
        if token == "NUMBER":
            try:
                element_count = int(body[index + 1], 0)
            except ValueError as error:
                raise ValueError(f"A2L symbol '{symbol}' has an invalid NUMBER value.") from error
            break
    if element_count is None or element_count < 2:
        raise ValueError(f"A2L symbol '{symbol}' must declare at least two NUMBER elements.")
    return address, element_count


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
class CalibrationComponentId:
    hex_filename: str
    component_id: str


def _decode_component_id(raw: bytes, symbol: str, hex_path: Path) -> str:
    length = raw[0]
    if length <= len(raw) - 1:
        value_bytes = raw[1 : length + 1]
    else:
        value_bytes = raw.rstrip(b"\x00\xff")
    try:
        value = value_bytes.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ValueError(f"Intel HEX value for '{symbol}' in {hex_path.name} is not ASCII text.") from error
    if not value:
        raise ValueError(f"Intel HEX value for '{symbol}' in {hex_path.name} is empty.")
    return value


def load_calibration_folder(folder: str | Path, symbol: str) -> list[CalibrationComponentId]:
    """Read the configured component-ID value from each HEX file beside the A2L."""
    a2l_path, hex_files = files_in_folder(folder)
    address, element_count = _a2l_symbol_info(a2l_path, symbol.strip())
    return [
        CalibrationComponentId(
            hex_path.name,
            _decode_component_id(_intel_hex_data(hex_path, address, element_count), symbol, hex_path),
        )
        for hex_path in hex_files
    ]


def component_id_matches(value: str, expected: str) -> bool:
    normalized_value = re.sub(r"[^a-z0-9]", "", value.casefold())
    normalized_expected = re.sub(r"[^a-z0-9]", "", expected.casefold())
    return normalized_value == normalized_expected


def find_calibration_hex(folder: str | Path, symbol: str, expected: str) -> Path:
    """The HEX file in `folder` whose component ID matches the DWG number `expected` (same check as the Home sheet)."""
    calibrations = load_calibration_folder(folder, symbol)
    match = next((item for item in calibrations if component_id_matches(item.component_id, expected)), None)
    if match is None:
        available = ", ".join(f"{item.hex_filename}: {item.component_id}" for item in calibrations)
        raise ValueError(f"no calibration HEX file matches the DWG number {expected} (found {available}).")
    return Path(folder) / match.hex_filename
