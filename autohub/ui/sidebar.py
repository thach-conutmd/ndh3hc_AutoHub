"""Collapsible sidebar: logo/title header + icon+label navigation list."""
from __future__ import annotations

from typing import Collection

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from autohub.config import APP_NAME, ICONS_DIR, LOGO_PATH
from autohub.ui.hover_cursor import HoverCursor

_EXPANDED_WIDTH = 170
_COLLAPSED_WIDTH = 56
_ICON_SIZE = QSize(20, 20)
_ROW_HEIGHT = 40  # 36 px item + 2 * 2 px margin, as in the theme

# Segoe MDL2 Assets glyphs: Cancel (X, shown when open) / GlobalNavButton (hamburger, shown when closed)
_OPEN_GLYPH = "\uE711"
_CLOSED_GLYPH = "\uE700"


class Sidebar(QWidget):
    """Sidebar navigation list that can collapse down to icon-only width."""

    moduleSelected = Signal(int)

    def __init__(self, items: list[tuple[str | None, str]], pinned_bottom: Collection[int] = ()):
        """``items`` is a list of (icon_file, display_name) pairs, in display order;
        the ``pinned_bottom`` indexes are listed at the bottom of the sidebar instead."""
        super().__init__()
        self.setObjectName("Sidebar")
        self._titles = [title for _, title in items]
        self._icon_files = [icon_file for icon_file, _ in items]
        self._collapsed = False

        self._logo = QLabel()
        if LOGO_PATH.exists():
            self._logo.setPixmap(QPixmap(str(LOGO_PATH)))
        self._logo.setFixedSize(28, 28)
        self._logo.setScaledContents(True)

        self._title_label = QLabel(APP_NAME)
        self._title_label.setObjectName("sidebarTitle")

        self._toggle_btn = QPushButton(_OPEN_GLYPH)  # sidebar starts expanded
        self._toggle_btn.setObjectName("toggleButton")
        self._toggle_btn.setFont(QFont("Segoe MDL2 Assets", 12))
        self._toggle_btn.setFixedSize(28, 28)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.clicked.connect(self.toggle_collapsed)

        self._header = QHBoxLayout()
        self._header.setContentsMargins(12, 12, 8, 12)
        self._header.addWidget(self._logo)
        self._header.addWidget(self._title_label, stretch=1)
        self._header.addWidget(self._toggle_btn)

        pinned = set(pinned_bottom)
        self._list = self._new_list()
        self._bottom_list = self._new_list()
        #: list -> module index of each of its rows
        self._module_of_row: dict[QListWidget, list[int]] = {self._list: [], self._bottom_list: []}
        self._items: list[QListWidgetItem] = []
        for module_index, (icon_file, title) in enumerate(items):
            target = self._bottom_list if module_index in pinned else self._list
            item = QListWidgetItem(self._resolve_icon(icon_file), title)
            target.addItem(item)
            self._module_of_row[target].append(module_index)
            self._items.append(item)
        self._bottom_list.setFixedHeight(self._bottom_list.count() * _ROW_HEIGHT + 8)
        self._bottom_list.setVisible(self._bottom_list.count() > 0)
        for source in (self._list, self._bottom_list):
            source.currentRowChanged.connect(lambda row, source=source: self._on_row_selected(source, row))
        self._hover = HoverCursor((self._list, self._bottom_list), lambda index: index.isValid())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(self._header)
        layout.addWidget(self._list, stretch=1)
        layout.addWidget(self._bottom_list)  # pinned modules, e.g. Settings

        self.setFixedWidth(_EXPANDED_WIDTH)

        if self._module_of_row[self._list]:
            self._list.setCurrentRow(0)

    @staticmethod
    def _new_list() -> QListWidget:
        widget = QListWidget()
        widget.setObjectName("sidebarList")
        widget.setFocusPolicy(Qt.NoFocus)
        widget.setIconSize(_ICON_SIZE)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return widget

    def select_module(self, index: int) -> None:
        """Highlights a module without emitting ``moduleSelected``."""
        for source, indexes in self._module_of_row.items():
            source.blockSignals(True)
            source.setCurrentRow(indexes.index(index) if index in indexes else -1)
            source.blockSignals(False)

    def _on_row_selected(self, source: QListWidget, row: int) -> None:
        if row < 0:
            return
        other = self._bottom_list if source is self._list else self._list
        other.blockSignals(True)
        other.setCurrentRow(-1)  # only one module is selected across both lists
        other.blockSignals(False)
        self.moduleSelected.emit(self._module_of_row[source][row])

    def _resolve_icon(self, icon_file: str | None) -> QIcon:
        path = ICONS_DIR / icon_file if icon_file else None
        if not path or not path.exists():
            return QIcon()
        if path.suffix.lower() == ".svg":
            renderer = QSvgRenderer(str(path))
            if not renderer.isValid():
                raise ValueError(f"Invalid sidebar icon: {path}")
            image = QImage(_ICON_SIZE.width() * 3, _ICON_SIZE.height() * 3, QImage.Format_ARGB32)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
        else:
            image = QImage(str(path))
            if image.isNull():
                raise ValueError(f"Invalid sidebar icon: {path}")
        if self.palette().window().color().lightness() > 128:
            image.invertPixels(QImage.InvertRgb)  # the icons are light; a light theme needs them dark
        return QIcon(QPixmap.fromImage(image))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange and hasattr(self, "_list"):
            for item, icon_file in zip(self._items, self._icon_files):
                item.setIcon(self._resolve_icon(icon_file))

    def toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        self._toggle_btn.setText(_CLOSED_GLYPH if self._collapsed else _OPEN_GLYPH)
        self.setFixedWidth(_COLLAPSED_WIDTH if self._collapsed else _EXPANDED_WIDTH)
        self._logo.setVisible(not self._collapsed)
        self._title_label.setVisible(not self._collapsed)
        # keep margins tight enough that the toggle button never overflows the collapsed width
        self._header.setContentsMargins(*((4, 12, 4, 12) if self._collapsed else (12, 12, 8, 12)))
        for item, title in zip(self._items, self._titles):
            item.setText("" if self._collapsed else title)
