"""Shared short-link display, editing, and copy-context behavior."""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QMenu, QStyledItemDelegate

from autohub.core.webflow_links import is_link, webflow_link_text


COPY_TOOLTIP = "Right-click to copy full WebFlow link"


def webflow_link_display_text(link: str, fallback: str = "") -> str:
    link = (link or "").strip()
    return webflow_link_text(link) or (fallback or link)


def webflow_link_tooltip(link: str) -> str:
    return COPY_TOOLTIP if is_link(link or "") else ""


def format_webflow_link_item(item, link: str, *, editable: bool = False) -> None:
    link = (link or "").strip()
    item.setData(Qt.UserRole, link)
    item.setText(webflow_link_display_text(link))
    item.setToolTip(webflow_link_tooltip(link))
    if not editable:
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)


def _show_copy_menu(parent, link: str, position) -> None:
    menu = QMenu(parent)
    copy = menu.addAction("Copy WebFlow Link")
    if menu.exec(position) == copy:
        QApplication.clipboard().setText(link)


class WebFlowLinkContextMenu(QObject):
    """Install the shared copy menu on link cells or a link-display widget."""

    def __init__(self, *, table=None, columns=(), views=(), widget=None, link_getter=None):
        super().__init__(table or widget)
        self._table = table
        self._columns = set(columns)
        self._views = {view.viewport(): view for view in ((table, *views) if table else ())}
        self._widget = widget
        self._link_getter = link_getter
        if table:
            for viewport in self._views:
                viewport.installEventFilter(self)
        elif widget:
            widget.installEventFilter(self)

    @classmethod
    def for_table(cls, table, columns: tuple[int, ...], mirrored_views=()):
        return cls(table=table, columns=columns, views=mirrored_views)

    @classmethod
    def for_widget(cls, widget, link_getter):
        return cls(widget=widget, link_getter=link_getter)

    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()
        if event_type not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.ContextMenu):
            return super().eventFilter(watched, event)
        if self._table:
            view = self._views.get(watched)
            if view is None:
                return super().eventFilter(watched, event)
            position = event.pos() if event_type == QEvent.ContextMenu else event.position().toPoint()
            index = view.indexAt(position)
            if not index.isValid() or index.column() not in self._columns:
                return super().eventFilter(watched, event)
            link = index.data(Qt.UserRole) or ""
        else:
            link = self._link_getter() or ""
        if not is_link(link):
            return super().eventFilter(watched, event)
        if event_type == QEvent.ContextMenu:
            _show_copy_menu(self._table or self._widget, link, event.globalPos())
            return True
        if event.button() == Qt.RightButton:
            return True
        return super().eventFilter(watched, event)


class WebFlowLinkDelegate(QStyledItemDelegate):
    def __init__(self, table, columns: tuple[int, ...]):
        super().__init__(table)
        for column in columns:
            table.setItemDelegateForColumn(column, self)
        self._context_menu = WebFlowLinkContextMenu.for_table(table, columns)

    @staticmethod
    def format_item(item) -> None:
        format_webflow_link_item(item, item.text(), editable=True)

    def setEditorData(self, editor, index) -> None:
        editor.setText(index.data(Qt.UserRole) or index.data(Qt.EditRole) or "")
