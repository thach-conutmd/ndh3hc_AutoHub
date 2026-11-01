"""Qt progress window with a compact result heading and full details in a scrollable log."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class ProgressDialog(QDialog):
    _step = Signal(str)
    _done = Signal(str, bool)

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMinimumWidth(460)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self._finished = False

        self._status = QLabel("Starting...")
        self._status.setWordWrap(True)
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # busy indicator until the action ends
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(120)
        self._buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self._buttons.rejected.connect(self.close)
        self._buttons.setEnabled(False)

        layout = QVBoxLayout(self)
        for widget in (self._status, self._bar, self._log, self._buttons):
            layout.addWidget(widget)

        # Signals marshal calls from the worker thread onto the UI thread.
        self._step.connect(self._show_step)
        self._done.connect(self._show_result)
        self.show()

    def step(self, text: str) -> None:
        self._step.emit(text)

    def succeed(self, text: str) -> None:
        self._done.emit(text, True)

    def fail(self, text: str) -> None:
        self._done.emit(text, False)

    def _show_step(self, text: str) -> None:
        self._status.setText(text.partition("\n")[0])
        self._log.appendPlainText(text)

    def _show_result(self, text: str, ok: bool) -> None:
        self._finished = True
        self._bar.setRange(0, 1)
        self._bar.setValue(1 if ok else 0)
        self._status.setText(text.partition("\n")[0])
        self._status.setStyleSheet("" if ok else "color: #c0392b; font-weight: bold;")
        self._log.appendPlainText(("Done: " if ok else "Error: ") + text)
        self._buttons.setEnabled(True)
        self.setWindowFlag(Qt.WindowCloseButtonHint, True)
        self.show()  # re-applies the window flags

    def reject(self) -> None:
        if self._finished:
            super().reject()

    def closeEvent(self, event) -> None:
        if self._finished:
            super().closeEvent(event)
        else:
            event.ignore()
