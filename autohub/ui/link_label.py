"""External link label activated only by a left-button double-click."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QMouseEvent
from PySide6.QtWidgets import QLabel

from autohub.ui.webflow_link_delegate import (
    WebFlowLinkContextMenu, webflow_link_display_text, webflow_link_tooltip,
)


class LinkLabel(QLabel):
    def __init__(self, text: str, url: str):
        super().__init__(text)
        self._url = QUrl(url)
        self._link_context_menu = WebFlowLinkContextMenu.for_widget(self, lambda: self._url.toString())
        self.setText(webflow_link_display_text(url, text))
        self.setTextFormat(Qt.PlainText)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(webflow_link_tooltip(url))
        self.setStyleSheet("color: palette(link);")
        font = self.font()
        font.setUnderline(True)
        self.setFont(font)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            QDesktopServices.openUrl(self._url)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
