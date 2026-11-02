from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from autohub.modules.creation.variant_checklist import VariantChecklist
from autohub.ui import link_label
from autohub.ui import webflow_link_delegate


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


def test_creation_link_context_menu_copies_full_url_without_breaking_open(qapp, monkeypatch):
    url = "https://webflow/app/ShowJob/16409"
    row = VariantChecklist()
    row.set_variants([{"part_number": "P", "ecu_type": "MG1", "webflow_link": url}])
    label = row._table.cellWidget(0, 5)
    opened = Mock()
    monkeypatch.setattr(link_label.QDesktopServices, "openUrl", opened)
    menu = Mock()
    menu.exec.return_value = menu.addAction.return_value
    monkeypatch.setattr(webflow_link_delegate, "QMenu", Mock(return_value=menu))
    QApplication.clipboard().setText("before")
    event = QContextMenuEvent(QContextMenuEvent.Mouse, label.rect().center(), label.mapToGlobal(label.rect().center()))
    QApplication.sendEvent(label, event)
    assert menu.addAction.call_args.args == ("Copy WebFlow Link",)
    assert QApplication.clipboard().text() == url
    assert label.text() == "WF16409"
    assert label.toolTip() == "Right-click to copy full WebFlow link"
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
