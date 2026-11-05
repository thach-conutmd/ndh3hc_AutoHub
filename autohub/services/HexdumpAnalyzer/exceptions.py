class HexdumpAnalyzerError(Exception):
    """Base error for the HexdumpAnalyzer feature."""


class RangeNotFoundError(HexdumpAnalyzerError, ValueError):
    """The requested key/parameter/block does not exist in the input file."""
