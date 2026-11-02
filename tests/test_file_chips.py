"""Reusable file chips wrap tightly, elide long names, and retain removal identity."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from autohub.ui.file_chips import FileChips
from autohub.ui.theme import apply_theme


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_file_chips_wrap_and_shrink_to_required_height(qapp, theme):
    apply_theme(qapp, theme)
    window = QWidget()
    layout = QVBoxLayout(window)
    chips = FileChips()
    layout.addWidget(chips)
    layout.addStretch(1)
    paths = [f"/exports/WF21821{index}_export.xml" for index in range(3)]
    chips.set_files(paths)
    window.resize(1000, 400)
    window.show()
    qapp.processEvents()
    try:
        first, second, third = chips.chips
        assert first.y() == second.y() == third.y()
        assert second.x() == first.geometry().right() + 1 + chips.layout().spacing()
        wide_height = chips.height()
        assert wide_height == first.height()
        window.resize(260, 400)
        qapp.processEvents()
        assert first.y() < second.y() < third.y()
        assert chips.height() == sum(chip.height() for chip in chips.chips) + 2 * chips.layout().spacing()
        window.resize(1000, 400)
        qapp.processEvents()
        assert chips.height() == wide_height
        assert first.y() == second.y() == third.y()
        chips.set_files(paths[:1])
        qapp.processEvents()
        assert chips.height() == chips.chips[0].height()
        chips.set_files([])
        assert chips.isHidden()
    finally:
        window.close()
        window.deleteLater()


def test_file_chip_limits_filename_width_and_keeps_remove_adjacent(qapp):
    chips = FileChips()
    path = "/exports/" + "very_long_export_name_" * 20 + ".xml"
    chips.set_files([path])
    chips.resize(1000, 80)
    chips.show()
    qapp.processEvents()
    try:
        chip = chips.chips[0]
        assert chip.width() <= 300
        assert chip.label.fontMetrics().horizontalAdvance(chip.label.text()) > chip.label.width()
        assert chip.label.fontMetrics().elidedText(chip.label.text(), Qt.ElideRight, chip.label.width()).endswith("\u2026")
        assert chip.toolTip() == path and chip.label.toolTip() == path
        assert chip.remove_button.x() - chip.label.geometry().right() - 1 == chip.layout().spacing()
        removed = []
        chips.removed.connect(removed.append)
        chip.remove_button.click()
        assert removed == [path]
    finally:
        chips.close()
        chips.deleteLater()
