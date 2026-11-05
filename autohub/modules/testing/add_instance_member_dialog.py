"""Dialog that runs the Add User to Instance Members test on a background thread."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from autohub.core.dialogs import Dialogs
from autohub.core.workers import FunctionWorker
from autohub.modules.testing.service import InstanceMemberTestService, validate_job_number

_TITLE = "Add User to Instance Members"


class AddInstanceMemberDialog(QDialog):
    def __init__(self, service: InstanceMemberTestService, dialogs: Dialogs, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._dialogs = dialogs
        self._worker: FunctionWorker | None = None
        self.setWindowTitle(_TITLE)
        self.setModal(True)

        self._job = QLineEdit()
        self._job.setPlaceholderText("Required, e.g. 12345")
        self._user = QLineEdit()
        self._user.setPlaceholderText("Blank uses Change Engineer from Settings")
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setAlignment(Qt.AlignmentFlag.AlignLeft)

        form = QFormLayout()
        form.addRow("WebFlow Job:", self._job)
        form.addRow("User:", self._user)

        self._add = QPushButton("Add")
        self._add.setDefault(True)
        self._add.clicked.connect(self._on_add)
        self._cancel = QPushButton("Cancel")
        self._cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self._add)
        buttons.addWidget(self._cancel)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addLayout(buttons)
        self.setMinimumWidth(420)

    def _on_add(self) -> None:
        try:
            validate_job_number(self._job.text())
        except ValueError as exc:
            self._dialogs.error(_TITLE, str(exc))
            self._job.setFocus()
            return
        job, user = self._job.text().strip(), self._user.text()
        self._set_busy(True, "Adding user to Instance Members...")
        self._worker = FunctionWorker(lambda: self._service.add_user(job, user), self)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.finished_error.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, added_name: str) -> None:
        self._worker = None
        self._set_busy(False, "")
        self._dialogs.info(_TITLE, f"{added_name} was added to Instance Members of job {self._job.text().strip()}.")
        self.accept()

    def _on_failed(self, message: str) -> None:
        self._worker = None
        self._set_busy(False, "")
        self._dialogs.error(_TITLE, message)

    def _set_busy(self, busy: bool, message: str) -> None:
        self._job.setEnabled(not busy)
        self._user.setEnabled(not busy)
        self._add.setEnabled(not busy)
        self._cancel.setEnabled(not busy)
        self._status.setText(message)

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
