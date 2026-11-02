from xml.etree import ElementTree

from autohub.config import ICONS_DIR
from autohub.bootstrap import build_modules
from autohub.core.module_base import AutoHubModule
from autohub.ui.main_window import MainWindow
from tests.fakes import MemorySettings


class _StubModule(AutoHubModule):
    display_name = "Stub"

    def create_widget(self):
        from PySide6.QtWidgets import QLabel

        return QLabel("stub")


def test_registered_modules_create_widgets(qapp):
    modules = build_modules(MemorySettings())
    assert [m.display_name for m in modules] == ["Home", "Creation", "Form B", "Comparison", "Settings"]
    for module in modules:
        assert module.create_widget() is not None


def test_module_icons_match_their_sidebar_labels():
    modules = build_modules(MemorySettings())
    expected = {
        "Home": "home.svg",
        "Creation": "creation.svg",
        "Form B": "creation.svg",
        "Comparison": "comparison.svg",
        "Settings": "settings.svg",
    }

    for module in modules:
        assert module.icon_file == expected[module.display_name]
        root = ElementTree.parse(ICONS_DIR / module.icon_file).getroot()
        assert root.tag.endswith("svg")


def test_a_new_module_appears_in_the_window_without_other_changes(qapp):
    window = MainWindow([*build_modules(MemorySettings()), _StubModule()])
    assert window._pages.count() == 6
