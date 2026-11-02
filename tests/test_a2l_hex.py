"""A2L-to-Intel-HEX component-ID lookup."""
from pathlib import Path

import pytest

from autohub.core.a2l_hex import (
    component_id_matches,
    files_in_folder,
    read_component_id,
)


def _record(address: int, record_type: int, data: bytes = b"") -> str:
    record = bytes((len(data), address >> 8, address & 0xFF, record_type)) + data
    checksum = (-sum(record)) & 0xFF
    return ":" + (record + bytes((checksum,))).hex().upper()


def write_calibration_folder(folder: Path, comp_id: str, symbol: str = "I14229_numCompID_CA") -> Path:
    folder.mkdir(exist_ok=True)
    (folder / "test.a2l").write_text(
        f'/begin CHARACTERISTIC {symbol} "Component ID" VALUE 0x1000 '
        'DIRECT 0 NO_COMPU_METHOD 0 0 /end CHARACTERISTIC\n',
        encoding="ascii",
    )
    (folder / "calibration-v3.hex").write_text(
        "\n".join(
            (
                _record(0x1000, 0x00, comp_id.encode("ascii")),
                _record(0x0000, 0x01),
            )
        ),
        encoding="ascii",
    )
    return folder


def test_reads_component_id_at_characteristic_address(tmp_path):
    folder = write_calibration_folder(tmp_path / "calibration", "P1")

    assert read_component_id(folder, "I14229_numCompID_CA", 2) == ("calibration-v3.hex", "P1")
    assert component_id_matches("P 1", "P1")
    assert not component_id_matches("P2", "P1")


def test_reads_measurement_ecu_address(tmp_path):
    folder = tmp_path / "measurement"
    write_calibration_folder(folder, "P1")
    (folder / "test.a2l").write_text(
        '/begin MEASUREMENT I14229_numCompID_CA "Component ID" UBYTE NO_COMPU_METHOD '
        '1 0 0 0 ECU_ADDRESS 0x1000 /end MEASUREMENT\n',
        encoding="ascii",
    )

    assert read_component_id(folder, "I14229_numCompID_CA", 2)[1] == "P1"


def test_reads_extended_linear_hex_address(tmp_path):
    folder = write_calibration_folder(tmp_path / "extended", "P1")
    (folder / "test.a2l").write_text(
        '/begin CHARACTERISTIC I14229_numCompID_CA "Component ID" VALUE 0x10000 '
        'DIRECT 0 NO_COMPU_METHOD 0 0 /end CHARACTERISTIC\n',
        encoding="ascii",
    )
    (folder / "calibration-v3.hex").write_text(
        "\n".join(
            (
                _record(0, 0x04, b"\x00\x01"),
                _record(0, 0x00, b"P1"),
                _record(0, 0x01),
            )
        ),
        encoding="ascii",
    )

    assert read_component_id(folder, "I14229_numCompID_CA", 2)[1] == "P1"


def test_strips_flash_padding_before_decoding_ascii(tmp_path):
    folder = write_calibration_folder(tmp_path / "padded", "P1")
    (folder / "calibration-v3.hex").write_text(
        _record(0x1000, 0x00, b"P1\xff\xff") + "\n" + _record(0, 0x01) + "\n",
        encoding="ascii",
    )

    assert read_component_id(folder, "I14229_numCompID_CA", 4)[1] == "P1"


def test_requires_exactly_one_a2l_and_hex_file(tmp_path):
    folder = write_calibration_folder(tmp_path / "calibration", "P1")
    (folder / "other.hex").write_text("", encoding="ascii")

    with pytest.raises(ValueError, match="exactly one .hex"):
        files_in_folder(folder)


def test_missing_symbol_is_reported(tmp_path):
    folder = write_calibration_folder(tmp_path / "calibration", "P1")

    with pytest.raises(ValueError, match="symbol 'missing'"):
        read_component_id(folder, "missing", 2)


def test_checksum_errors_are_reported(tmp_path):
    folder = write_calibration_folder(tmp_path / "calibration", "P1")
    (folder / "calibration-v3.hex").write_text(":02000000000000\n", encoding="ascii")

    with pytest.raises(ValueError, match="checksum"):
        read_component_id(folder, "I14229_numCompID_CA", 2)
