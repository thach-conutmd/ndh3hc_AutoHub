"""Characterization and parity tests for the HexdumpAnalyzer range finders.

Parity tests compare against the legacy Hexdump/Capture_Auto modules when that folder is present.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

from autohub.services.HexdumpAnalyzer.container_parser import find_parameter
from autohub.services.HexdumpAnalyzer.dflash_block_parser import find_dflash_block
from autohub.services.HexdumpAnalyzer.exceptions import HexdumpAnalyzerError, RangeNotFoundError
from autohub.services.HexdumpAnalyzer.fee_parser import find_key_secumgr_fee
from autohub.services.HexdumpAnalyzer.range_finder import FINDERS, find_range
from autohub.services.HexdumpAnalyzer.mem_overview_parser import find_mem_overview_block

LEGACY_SPLIT = Path(__file__).resolve().parent.parent / "Hexdump" / "Capture_Auto" / "Split_Auto"

CNT_TEXT = """<PARAMETER>
<PARAMETER-NAME>FOO</PARAMETER-NAME>
<PARAMETER-VALUE>1</PARAMETER-VALUE>
</PARAMETER>
<PARAMETER>
<PARAMETER-NAME>DYN_BLOCK_SHORT_NAME</PARAMETER-NAME>
<PARAMETER-VALUE>DCM_SIGNALG_KEYID</PARAMETER-VALUE>
</PARAMETER>
<PARAMETER>
<PARAMETER-NAME>DYN_VALUE</PARAMETER-NAME>
<PARAMETER-VALUE>0x12</PARAMETER-VALUE>
</PARAMETER>
"""

DFLASH_TEXT = """+-------+
| Id: 7
| Name: BLK_A
| Info: x
+-------+
+-------+
| Id: 8
| Name: BLK_B
| Info: y
+-------+
"""

FEE_XML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<ROOT>
  <FEE_BLOCK_PROP>
    <FEE_BLOCK_CONFIGURED_NAME>KEY_A</FEE_BLOCK_CONFIGURED_NAME>
  </FEE_BLOCK_PROP>
  <FEE_BLOCK_PROP>
    <FEE_BLOCK_CONFIGURED_NAME>KEY_B</FEE_BLOCK_CONFIGURED_NAME>
  </FEE_BLOCK_PROP>
</ROOT>
"""

MEM_XML = """<ROOT>
  <MEM_OVERVIEW_BLOCK>
    <MEM_OVERVIEW_BLOCK_ID>0x0703</MEM_OVERVIEW_BLOCK_ID>
    <MEM_OVERVIEW_BLOCK_DATA>
      <MEM_OVERVIEW_PAGE_DATA>AA</MEM_OVERVIEW_PAGE_DATA>
    </MEM_OVERVIEW_BLOCK_DATA>
  </MEM_OVERVIEW_BLOCK>
</ROOT>
"""


@pytest.fixture
def cnt(tmp_path):
    path = tmp_path / "x.cnt"
    path.write_text(CNT_TEXT, encoding="utf-8")
    return str(path)


@pytest.fixture
def dflash(tmp_path):
    path = tmp_path / "x.txt"
    path.write_text(DFLASH_TEXT, encoding="utf-8")
    return str(path)


@pytest.fixture
def fee(tmp_path):
    path = tmp_path / "fee.xml"
    path.write_text(FEE_XML, encoding="utf-8")
    return str(path)


@pytest.fixture
def mem(tmp_path):
    path = tmp_path / "hsm.xml"
    path.write_text(MEM_XML, encoding="utf-8")
    return str(path)


def test_cnt_plain_parameter_returns_its_line_span(cnt):
    assert find_parameter(cnt, "FOO") == (1, 4)


def test_cnt_dcm_signalg_keyid_resolves_through_block_short_name(cnt):
    assert find_parameter(cnt, "DCM_SIGNALG_KEYID") == (9, 12)


def test_cnt_missing_parameter_raises_range_not_found(cnt):
    with pytest.raises(RangeNotFoundError, match="'NOPE' not found"):
        find_parameter(cnt, "NOPE")


def test_dflash_block_span_matches_legacy_convention(dflash):
    assert find_dflash_block(dflash, "BLK_A") == (1, 5)
    assert find_dflash_block(dflash, "BLK_B") == (6, 10)


def test_dflash_missing_block_raises(dflash):
    with pytest.raises(RangeNotFoundError):
        find_dflash_block(dflash, "BLK_Z")


def test_fee_key_spans(fee):
    assert find_key_secumgr_fee(fee, "KEY_A") == (3, 5)
    assert find_key_secumgr_fee(fee, "KEY_B") == (6, 8)


def test_fee_missing_key_raises(fee):
    with pytest.raises(RangeNotFoundError, match="'KEY_Z' not found"):
        find_key_secumgr_fee(fee, "KEY_Z")


def test_mem_block_span(mem):
    assert find_mem_overview_block(mem, "0x0703") == (2, 7)


def test_mem_missing_block_raises(mem):
    with pytest.raises(RangeNotFoundError):
        find_mem_overview_block(mem, "0x9999")


def test_range_not_found_is_value_error_for_legacy_callers():
    assert issubclass(RangeNotFoundError, ValueError)
    assert issubclass(RangeNotFoundError, HexdumpAnalyzerError)


def test_find_range_dispatches_by_mode(cnt, dflash, fee, mem):
    assert find_range("cnt", cnt, "FOO") == (1, 4)
    assert find_range("block", dflash, "BLK_A") == (1, 5)
    assert find_range("fee", fee, "KEY_A") == (3, 5)
    assert find_range("mem_block", mem, "0x0703") == (2, 7)


def test_find_range_rejects_unknown_mode(cnt):
    with pytest.raises(ValueError, match="unknown MODE 'nope'"):
        find_range("nope", cnt, "FOO")


def test_find_range_rejects_non_pair_results(monkeypatch, cnt):
    monkeypatch.setitem(FINDERS, "bad", lambda path, key: (1, True))
    with pytest.raises(ValueError, match="two integers"):
        find_range("bad", cnt, "FOO")


def _load_legacy(name: str):
    """Load a legacy Split_Auto module without running its import-time sample code (hsm_dflash has it)."""
    spec = importlib.util.spec_from_file_location(f"legacy_{name}", LEGACY_SPLIT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not LEGACY_SPLIT.is_dir(), reason="legacy Hexdump source not present")
def test_parity_with_legacy_finders(cnt, dflash, fee, mem):
    legacy_container = _load_legacy("container_file")
    legacy_dflash = _load_legacy("dflashBlockOverview")
    legacy_fee = _load_legacy("secumgr_fee_export")
    assert legacy_container.find_parameter(cnt, "DCM_SIGNALG_KEYID") == find_parameter(cnt, "DCM_SIGNALG_KEYID")
    assert legacy_container.find_parameter(cnt, "FOO") == find_parameter(cnt, "FOO")
    assert legacy_dflash.find_dflash_block(dflash, "BLK_B") == find_dflash_block(dflash, "BLK_B")
    assert legacy_fee.find_key_secumgr_fee(fee, "KEY_B") == find_key_secumgr_fee(fee, "KEY_B")
