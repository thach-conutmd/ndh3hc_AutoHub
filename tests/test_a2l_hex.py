"""A2L-to-Intel-HEX component-ID lookup."""
from pathlib import Path

import pytest

from autohub.core.a2l_hex import (
    component_id_matches,
    files_in_folder,
    load_calibration_folder,
)


def _record(address: int, record_type: int, data: bytes = b"") -> str:
    record = bytes((len(data), address >> 8, address & 0xFF, record_type)) + data
    checksum = (-sum(record)) & 0xFF
    return ":" + (record + bytes((checksum,))).hex().upper()


def write_calibration_folder(
    folder: Path,
    comp_id: str,
    symbol: str = "I14229_numCompID_CA",
    additional_comp_ids: tuple[str, ...] = (),
) -> Path:
    folder.mkdir(exist_ok=True)
    (folder / "test.a2l").write_text(
        f'/begin CHARACTERISTIC {symbol} "Component ID" VAL_BLK 0x1000 '
        'ValA_Wu8 255.0 OneToOne 0.00 255.0 NUMBER 17 /end CHARACTERISTIC\n',
        encoding="ascii",
    )
    for index, value in enumerate((comp_id, *additional_comp_ids), start=3):
        encoded = value.encode("ascii")
        field = (bytes((len(encoded),)) + encoded).ljust(17, b"\x00")
        (folder / f"calibration-v{index}.hex").write_text(
            "\n".join((_record(0x1000, 0x00, field), _record(0x0000, 0x01))),
            encoding="ascii",
        )
    return folder


def test_reads_component_id_at_characteristic_address(tmp_path):
    folder = write_calibration_folder(tmp_path / "calibration", "P1")
    components = load_calibration_folder(folder, "I14229_numCompID_CA")

    assert [(item.hex_filename, item.component_id) for item in components] == [
        ("calibration-v3.hex", "P1")
    ]
    assert component_id_matches("P 1", "P1")
    assert component_id_matches("37820-6WZ-M710-M6", "378206WZM710M6")
    assert not component_id_matches("P2", "P1")


def test_reads_measurement_ecu_address(tmp_path):
    folder = tmp_path / "measurement"
    write_calibration_folder(folder, "P1")
    (folder / "test.a2l").write_text(
        '/begin MEASUREMENT I14229_numCompID_CA "Component ID" UBYTE NO_COMPU_METHOD '
        '1 0 0 0 ECU_ADDRESS 0x1000 NUMBER 17 /end MEASUREMENT\n',
        encoding="ascii",
    )

    assert load_calibration_folder(folder, "I14229_numCompID_CA")[0].component_id == "P1"


def test_reads_extended_linear_hex_address(tmp_path):
    folder = write_calibration_folder(tmp_path / "extended", "P1")
    (folder / "test.a2l").write_text(
        '/begin CHARACTERISTIC I14229_numCompID_CA "Component ID" VAL_BLK 0x10000 '
        'ValA_Wu8 255.0 OneToOne 0.00 255.0 NUMBER 17 /end CHARACTERISTIC\n',
        encoding="ascii",
    )
    field = b"\x02P1" + b"\x00" * 14
    (folder / "calibration-v3.hex").write_text(
        "\n".join(
            (
                _record(0, 0x04, b"\x00\x01"),
                _record(0, 0x00, field),
                _record(0, 0x01),
            )
        ),
        encoding="ascii",
    )

    assert load_calibration_folder(folder, "I14229_numCompID_CA")[0].component_id == "P1"


def test_strips_flash_padding_before_decoding_ascii(tmp_path):
    folder = write_calibration_folder(tmp_path / "padded", "P1")
    field = b"\x02P1" + b"\xff" * 14
    (folder / "calibration-v3.hex").write_text(
        _record(0x1000, 0x00, field) + "\n" + _record(0, 0x01) + "\n",
        encoding="ascii",
    )

    assert load_calibration_folder(folder, "I14229_numCompID_CA")[0].component_id == "P1"


def test_accepts_multiple_hex_files_for_variants(tmp_path):
    folder = write_calibration_folder(tmp_path / "calibration", "P1")
    (folder / "other.hex").write_text(
        _record(0x1000, 0x00, b"\x02P2" + b"\x00" * 14)
        + "\n"
        + _record(0, 0x01)
        + "\n",
        encoding="ascii",
    )

    assert len(files_in_folder(folder)[1]) == 2
    assert [item.component_id for item in load_calibration_folder(folder, "I14229_numCompID_CA")] == [
        "P1", "P2"
    ]


def test_missing_symbol_is_reported(tmp_path):
    folder = write_calibration_folder(tmp_path / "calibration", "P1")

    with pytest.raises(ValueError, match="symbol 'missing'"):
        load_calibration_folder(folder, "missing")


def test_checksum_errors_are_reported(tmp_path):
    folder = write_calibration_folder(tmp_path / "calibration", "P1")
    (folder / "calibration-v3.hex").write_text(":02000000000000\n", encoding="ascii")

    with pytest.raises(ValueError, match="checksum"):
        load_calibration_folder(folder, "I14229_numCompID_CA")
