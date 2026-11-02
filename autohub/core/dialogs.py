"""User-interaction ports (file pick, messages) so workflows run in tests without a visible window."""
from __future__ import annotations

from typing import Mapping, Protocol, Sequence

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from autohub.core.file_fields import FileField
from autohub.core.file_form_dialog import FileFormDialog
from autohub.core.progress import ProgressWindow
from autohub.core.progress_dialog import ProgressDialog


class Dialogs(Protocol):
    def pick_files(self, title: str, file_filter: str) -> list[str]:
        """Selected paths, or an empty list when cancelled."""
        ...

    def pick_file(self, title: str, file_filter: str) -> str:
        """Selected path, or "" when the user cancels."""
        ...

    def save_file(self, title: str, default_name: str, file_filter: str) -> str:
        """Chosen destination path, or "" when the user cancels."""
        ...

    def info(self, title: str, text: str) -> None: ...

    def error(self, title: str, text: str) -> None: ...

    def confirm(self, title: str, text: str) -> bool:
        """True when the user agrees, False otherwise."""
        ...

    def ask_yes_no_cancel(
        self, title: str, text: str, yes_text: str | None = None, no_text: str | None = None
    ) -> bool | None:
        """True for Yes, False for No, None for Cancel; the optional texts relabel the Yes / No buttons."""
        ...

    def open_progress(self, title: str) -> ProgressWindow: ...

    def ask_files(self, title: str, fields: Sequence[FileField], initial: Mapping[str, str]) -> dict[str, str] | None:
        """Field name -> chosen path ("" for an optional field left empty), or None when cancelled."""
        ...


class QtDialogs:
    def __init__(self, parent: QWidget | None = None):
        self._parent = parent

    def pick_file(self, title: str, file_filter: str) -> str:
        path, _ = QFileDialog.getOpenFileName(self._parent, title, filter=file_filter)
        return path

    def pick_files(self, title: str, file_filter: str) -> list[str]:
        paths, _ = QFileDialog.getOpenFileNames(self._parent, title, filter=file_filter)
        return paths

    def save_file(self, title: str, default_name: str, file_filter: str) -> str:
        path, _ = QFileDialog.getSaveFileName(self._parent, title, default_name, file_filter)
        return path

    def info(self, title: str, text: str) -> None:
        QMessageBox.information(self._parent, title, text)

    def error(self, title: str, text: str) -> None:
        QMessageBox.critical(self._parent, title, text)

    def confirm(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(
            self._parent, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        return answer == QMessageBox.Yes

    def ask_yes_no_cancel(
        self, title: str, text: str, yes_text: str | None = None, no_text: str | None = None
    ) -> bool | None:
        box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, self._parent)
        box.setDefaultButton(QMessageBox.No)
        if yes_text:
            box.button(QMessageBox.Yes).setText(yes_text)
        if no_text:
            box.button(QMessageBox.No).setText(no_text)
        answer = box.exec()
        if answer == QMessageBox.Cancel:
            return None
        return answer == QMessageBox.Yes

    def open_progress(self, title: str) -> ProgressWindow:
        return ProgressDialog(title, self._parent)

    def ask_files(self, title: str, fields: Sequence[FileField], initial: Mapping[str, str]) -> dict[str, str] | None:
        dialog = FileFormDialog(title, fields, initial, self._parent)
        return dialog.values() if dialog.exec() == FileFormDialog.Accepted else None
