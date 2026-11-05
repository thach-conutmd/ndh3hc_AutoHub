class HexdumpAnalyzerError(Exception):
    """Base error for the HexdumpAnalyzer feature."""


class RangeNotFoundError(HexdumpAnalyzerError, ValueError):
    """The requested key/parameter/block does not exist in the input file."""


class HexdumpSettingsError(HexdumpAnalyzerError):
    """A settings file is invalid. `errors` lists every problem found, in source order."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors: tuple[str, ...] = tuple(errors)
