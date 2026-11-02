"""Drop-down editor for table columns that webFLOW fills from a fixed list."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QStyledItemDelegate


class ChoiceDelegate(QStyledItemDelegate):
    def __init__(self, choices: tuple[str, ...], parent=None):
        super().__init__(parent)
        self._choices = choices

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItem("")  # lets the user clear the cell
        editor.addItems(self._choices)
        editor.activated.connect(lambda _i, e=editor: self.commitData.emit(e))
        return editor

    def setEditorData(self, editor, index) -> None:
        text = str(index.data() or "")
        if text and editor.findText(text) < 0:
            editor.addItem(text)  # keep a value that is not in the list instead of losing it
        editor.setCurrentIndex(max(editor.findText(text), 0))

    def setModelData(self, editor, model, index) -> None:
        model.setData(index, editor.currentText())

    def updateEditorGeometry(self, editor, option, index) -> None:
        editor.setGeometry(option.rect)


class MultiChoiceComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self._selection_order: list[str] = []
        self.view().clicked.connect(self._toggle_choice)

    def add_choice(self, choice: str) -> None:
        self.addItem(choice)
        item = self.model().item(self.count() - 1)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setCheckState(Qt.Unchecked)

    def selected_values(self) -> list[str]:
        checked = [
            self.itemText(index)
            for index in range(self.count())
            if self.model().item(index).checkState() == Qt.Checked
        ]
        checked_set = set(checked)
        ordered = [value for value in self._selection_order if value in checked_set]
        ordered.extend(value for value in checked if value not in ordered)
        return ordered

    def set_selected_values(self, values: list[str]) -> None:
        selected = set(values)
        self._selection_order = list(dict.fromkeys(values))
        for value in values:
            if self.findText(value) < 0:
                self.add_choice(value)
        for index in range(self.count()):
            self.model().item(index).setCheckState(
                Qt.Checked if self.itemText(index) in selected else Qt.Unchecked
            )
        self._update_text()

    def _toggle_choice(self, index) -> None:
        item = self.model().itemFromIndex(index)
        if item.checkState() == Qt.Checked:
            item.setCheckState(Qt.Unchecked)
            self._selection_order = [value for value in self._selection_order if value != item.text()]
        else:
            item.setCheckState(Qt.Checked)
            if item.text() not in self._selection_order:
                self._selection_order.append(item.text())
        self._update_text()
        QTimer.singleShot(0, self.showPopup)

    def _update_text(self) -> None:
        self.setEditText("|".join(self.selected_values()))


class MultiChoiceDelegate(QStyledItemDelegate):
    def __init__(self, choices: tuple[str, ...], parent=None):
        super().__init__(parent)
        self._choices = choices

    def createEditor(self, parent, option, index):
        editor = MultiChoiceComboBox(parent)
        for choice in self._choices:
            editor.add_choice(choice)
        return editor

    def setEditorData(self, editor, index) -> None:
        editor.set_selected_values([value for value in str(index.data() or "").split("|") if value])

    def setModelData(self, editor, model, index) -> None:
        model.setData(index, "|".join(editor.selected_values()))

    def updateEditorGeometry(self, editor, option, index) -> None:
        editor.setGeometry(option.rect)
