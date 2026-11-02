"""Qt dialog with one file or folder row per `FileField`; OK needs every required path to exist."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from autohub.core.file_fields import FileField


class FileFormDialog(QDialog):
    def __init__(
        self,
        title: str,
        fields: Sequence[FileField],
        initial: Mapping[str, str],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(640)
        self._fields = list(fields)
        self._edits: dict[str, QLineEdit] = {}

        grid = QGridLayout()
        for row, field in enumerate(self._fields):
            label = QLabel(f"{field.name}{' *' if field.required else ' (optional)'}")
            edit = QLineEdit(initial.get(field.name, ""))
            edit.setPlaceholderText(field.hint)
            edit.textChanged.connect(self._refresh)
            browse = QPushButton("Browse...")
            browse.clicked.connect(lambda _checked=False, f=field: self._browse(f))
            for column, widget in enumerate((label, edit, browse)):
                grid.addWidget(widget, row, column)
            self._edits[field.name] = edit
        grid.setColumnStretch(1, 1)

        self._message = QLabel()
        self._message.setStyleSheet("color: #c0392b;")
        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(self._message)
        layout.addWidget(self._buttons)
        self._refresh()

    def values(self) -> dict[str, str]:
        return {name: edit.text().strip() for name, edit in self._edits.items()}

    def _browse(self, field: FileField) -> None:
        edit = self._edits[field.name]
        if field.directory:
            path = QFileDialog.getExistingDirectory(self, f"Select {field.name}", edit.text().strip())
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, f"Select {field.name}", edit.text().strip(), field.file_filter
            )
        if path:
            edit.setText(path)

    def _problem(self) -> str:
        for field in self._fields:
            path = self.values()[field.name]
            if not path and field.required:
                return f"Select the {field.name} {'folder' if field.directory else 'file'}."
            if path and not (Path(path).is_dir() if field.directory else Path(path).is_file()):
                return f"{field.name}: {'folder' if field.directory else 'file'} not found."
        return ""

    def _refresh(self) -> None:
        problem = self._problem()
        self._message.setText(problem)
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(not problem)
