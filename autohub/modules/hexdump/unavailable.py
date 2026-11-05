"""Placeholder Hexdump backend used until the new service is wired in."""
from autohub.core.ports import HexdumpInputError


class UnavailableHexdumpService:
    _MESSAGE = "The Hexdump service is not available yet."

    def modes(self) -> tuple[str, ...]:
        return ()

    def check_settings(self, path: str) -> str:
        raise HexdumpInputError(self._MESSAGE)

    def find_range(self, mode: str, path: str, key: str) -> tuple[int, int]:
        raise HexdumpInputError(self._MESSAGE)
