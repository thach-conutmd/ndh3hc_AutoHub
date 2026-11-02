"""Compact, wrapping file selections shared by local-file workflows."""
from __future__ import annotations

import os

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QWidget,
)


class _FilenameLabel(QLabel):
    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(min(hint.width(), 240), hint.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(24, super().minimumSizeHint().height())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(
            self.contentsRect(), Qt.AlignLeft | Qt.AlignVCenter,
            self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.contentsRect().width()),
        )


class FileChip(QFrame):
    removed = Signal(str)

    def __init__(self, path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.path = path
        self.setObjectName("fileChip")
        self.setToolTip(path)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.label = _FilenameLabel(os.path.basename(path))
        self.label.setTextFormat(Qt.PlainText)
        self.label.setToolTip(path)
        self.remove_button = QPushButton("\u00d7")
        self.remove_button.setObjectName("removeFileChip")
        self.remove_button.setFixedSize(20, 20)
        self.remove_button.setToolTip(f"Remove {os.path.basename(path)}")
        self.remove_button.setAccessibleName(f"Remove {os.path.basename(path)}")
        self.remove_button.clicked.connect(lambda: self.removed.emit(path))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 5, 3)
        layout.setSpacing(4)
        layout.addWidget(self.label)
        layout.addWidget(self.remove_button)
        self.setStyleSheet(
            "QFrame#fileChip { background: palette(alternate-base); border: 1px solid palette(mid); "
            "border-radius: 6px; }"
            "QFrame#fileChip QLabel { background: transparent; border: none; }"
            "QPushButton#removeFileChip { background: transparent; color: palette(window-text); "
            "border: none; border-radius: 4px; padding: 0; min-width: 0; min-height: 0; }"
            "QPushButton#removeFileChip:hover { background: palette(midlight); }"
        )


class _FlowLayout(QLayout):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Horizontal

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, rect: QRect, apply: bool) -> int:
        x, y, row_height = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            width = min(hint.width(), rect.width())
            if x > rect.x() and x + width > rect.x() + rect.width():
                x = rect.x()
                y += row_height + self.spacing()
                row_height = 0
            if apply:
                item.setGeometry(QRect(x, y, width, hint.height()))
            x += width + self.spacing()
            row_height = max(row_height, hint.height())
        return y + row_height - rect.y()


class FileChips(QWidget):
    removed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._flow = _FlowLayout(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.chips: list[FileChip] = []
        self.hide()

    def set_files(self, paths: list[str]) -> None:
        while self._flow.count():
            item = self._flow.takeAt(0)
            item.widget().hide()
            item.widget().deleteLater()
        self.chips = []
        for path in paths:
            chip = FileChip(path, self)
            chip.removed.connect(self.removed)
            self._flow.addWidget(chip)
            self.chips.append(chip)
        self.setVisible(bool(paths))
        self._flow.invalidate()
        self.updateGeometry()
