"""Maps a settings MODE to its range finder (legacy: get_input.FINDERS and get_input.Call)."""
from collections.abc import Callable

from autohub.services.HexdumpAnalyzer.container_parser import find_parameter
from autohub.services.HexdumpAnalyzer.dflash_block_parser import find_dflash_block
from autohub.services.HexdumpAnalyzer.fee_parser import find_key_secumgr_fee
from autohub.services.HexdumpAnalyzer.mem_overview_parser import find_mem_overview_block

RangeFinder = Callable[[str, str], tuple[int, int]]

FINDERS: dict[str, RangeFinder] = {
    "block": find_dflash_block,
    "cnt": find_parameter,
    "mem_block": find_mem_overview_block,
    "fee": find_key_secumgr_fee,
}


def find_range(mode: str, path: str, key: str) -> tuple[int, int]:
    """Return (start_line, end_line), both 1-based and inclusive."""
    if mode not in FINDERS:
        raise ValueError(f"unknown MODE {mode!r} (available: {', '.join(sorted(FINDERS))})")
    result = FINDERS[mode](path, key)
    if not (isinstance(result, tuple) and len(result) == 2
            and all(isinstance(x, int) and not isinstance(x, bool) for x in result)):
        raise ValueError(f"finder for MODE {mode!r} must return (start_line, end_line) as two integers, got {result!r}")
    return result
