"""Modal comparison progress without a nested event loop or browser work."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton,
    QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout,
)


class ComparisonProgressDialog(QDialog):
    cancel_requested = Signal()

    def __init__(self, identities: list[str], parent=None, *, identity_header: str = "Variant"):
        super().__init__(parent)
        self.setWindowTitle("Comparison Progress")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.setMinimumSize(640, 380)
        self._active = True
        self._statuses = ["Pending"] * len(identities)
        self._overall = QLabel()
        self._bar = QProgressBar()
        self._bar.setRange(0, len(identities))
        self._current = QLabel("Current: Waiting to start")
        self._operation = QLabel("Pending")
        self._operation.setWordWrap(True)
        self._items = QTableWidget(len(identities), 3)
        self._items.setHorizontalHeaderLabels((identity_header, "Status", "Error"))
        self._items.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._items.verticalHeader().hide()
        self._items.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._items.setColumnWidth(0, 270)
        self._items.setColumnWidth(1, 160)
        self._items.horizontalHeader().setStretchLastSection(True)
        for row, variant in enumerate(identities):
            for column, text in enumerate((variant, "Pending", "")):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self._items.setItem(row, column, item)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._button = QPushButton("Cancel")
        self._button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._button.setAutoDefault(False)
        self._button.clicked.connect(self._clicked)
        self._cancel_message = (
            "Stopping XML comparison safely." if identity_header != "Variant"
            else "Finishing the active variant safely; remaining variants will be skipped."
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        for widget in (
            self._overall, self._bar, self._current, self._operation,
            self._items, self._summary,
        ):
            layout.addWidget(widget)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 6, 0, 0)
        footer.addStretch(1)
        footer.addWidget(self._button)
        layout.addLayout(footer)
        self._update_overall()

    def _update_overall(self) -> None:
        processed = sum(status in ("Completed", "Failed") for status in self._statuses)
        total = len(self._statuses)
        percentage = processed * 100 // total if total else 0
        self._bar.setValue(processed)
        self._overall.setText(f"Overall: {processed} / {total} ({percentage}%)")

    def update_status(self, index: int, status: str, error: str) -> None:
        if not 0 <= index < len(self._statuses):
            return
        self._statuses[index] = status
        for column, text in ((1, status), (2, error)):
            self._items.item(index, column).setText(text)
            self._items.item(index, column).setToolTip(text)
        if status not in ("Pending", "Cancelled"):
            self._current.setText(f"Current: {self._items.item(index, 0).text()}")
            self._operation.setText(status + (f": {error}" if error else ""))
        self._update_overall()

    def _clicked(self) -> None:
        if self._active:
            self._button.setEnabled(False)
            self._button.setText("Cancelling...")
            self._summary.setText(self._cancel_message)
            self.cancel_requested.emit()
        else:
            self.accept()

    def finish(self, error: str = "") -> None:
        if error:
            for index, status in enumerate(self._statuses):
                if status not in ("Completed", "Failed", "Cancelled"):
                    self.update_status(index, "Failed", error)
        self._active = False
        completed = self._statuses.count("Completed")
        failed = self._statuses.count("Failed")
        cancelled = self._statuses.count("Cancelled")
        self._summary.setText(
            f"Completed: {completed}\nFailed: {failed}\nTotal: {len(self._statuses)}"
            + (f"\nCancelled: {cancelled}" if cancelled else "")
        )
        self._operation.setText("Cancelled" if cancelled else "Finished")
        self._button.setText("Close")
        self._button.setEnabled(True)

    def reject(self) -> None:
        if not self._active:
            super().reject()

    def accept(self) -> None:
        if not self._active:
            super().accept()

    def done(self, result: int) -> None:
        if not self._active:
            super().done(result)

    def closeEvent(self, event) -> None:
        if self._active:
            event.ignore()
        else:
            super().closeEvent(event)
