from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from autohub.modules.creation.variant_checklist import VariantChecklist
from autohub.ui import link_label


def test_creation_link_requires_left_double_click(qapp, monkeypatch):
    url = "https://webflow/app/ShowJob/16409"
    row = VariantChecklist()
    row.set_variants([{"part_number": "P", "ecu_type": "MG1CS022", "webflow_link": url}])
    row.show()
    qapp.processEvents()
    label = row.findChild(link_label.LinkLabel)
    opened = Mock()
    monkeypatch.setattr(link_label.QDesktopServices, "openUrl", opened)

    assert label.text() == "WF16409"
    assert not label.openExternalLinks()
    QTest.mouseClick(label, Qt.LeftButton)
    opened.assert_not_called()
    QTest.mouseDClick(label, Qt.LeftButton)
    opened.assert_called_once()
    assert opened.call_args.args[0].toString() == url
    row.close()


@pytest.mark.parametrize("button", [Qt.RightButton, Qt.MiddleButton])
def test_other_double_clicks_do_not_open_links(qapp, monkeypatch, button):
    label = link_label.LinkLabel("Job", "https://webflow/app/ShowJob/1")
    label.show()
    opened = Mock()
    monkeypatch.setattr(link_label.QDesktopServices, "openUrl", opened)
    QTest.mouseDClick(label, button)
    opened.assert_not_called()
    label.close()
