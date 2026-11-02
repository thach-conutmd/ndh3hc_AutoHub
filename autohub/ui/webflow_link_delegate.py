"""Shared short-link display, editing, and copy-context behavior."""
from PySide6.QtCore import QEvent, QObject, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMenu, QStyledItemDelegate

from autohub.core.webflow_links import is_link, webflow_link_text


COPY_TOOLTIP = "Double-click to open. Right-click for options"


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
    item.setFlags(item.flags() | Qt.ItemIsEditable if editable else item.flags() & ~Qt.ItemIsEditable)
    if is_link(link):
        item.setForeground(QApplication.palette().link())
    else:
        item.setData(Qt.ForegroundRole, None)


def open_webflow_link(link: str) -> None:
    if is_link(link):
        QDesktopServices.openUrl(QUrl(link))


def _show_link_menu(parent, link: str, position, *, edit=None, clear=None) -> None:
    menu = QMenu(parent)
    copy = menu.addAction("Copy WebFlow Link")
    copy.setEnabled(is_link(link))
    edit_action = menu.addAction("Edit WebFlow Link") if edit is not None else None
    clear_action = menu.addAction("Clear WebFlow Link") if clear is not None else None
    selected = menu.exec(position)
    if selected == copy and is_link(link):
        QApplication.clipboard().setText(link)
    elif edit_action is not None and selected == edit_action:
        edit()
    elif clear_action is not None and selected == clear_action:
        clear()


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
        if event_type not in (
            QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick, QEvent.ContextMenu,
        ):
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
            editable = bool(index.flags() & Qt.ItemIsEditable)
        else:
            link = self._link_getter() or ""
            editable = False
        if not is_link(link) and not editable:
            return super().eventFilter(watched, event)
        if event_type == QEvent.MouseButtonDblClick:
            if self._table and event.button() == Qt.LeftButton and is_link(link):
                open_webflow_link(link)
                return True
            return super().eventFilter(watched, event)
        if event_type == QEvent.ContextMenu:
            _show_link_menu(
                self._table or self._widget, link, event.globalPos(),
                edit=(lambda: view.edit(index)) if editable else None,
                clear=(lambda: self._table.item(index.row(), index.column()).setText("")) if editable else None,
            )
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
