"""Hexdump module navigation and placeholder page."""
from PySide6.QtWidgets import QLabel

from autohub.modules.hexdump.module import HexdumpModule


def test_hexdump_module_shows_centered_coming_soon(qapp):
    module = HexdumpModule()
    assert module.display_name == "Hexdump"
    page = module.create_widget()
    try:
        labels = [label.text() for label in page.findChildren(QLabel)]
        assert labels == ["Coming Soon"]
    finally:
        page.close()
