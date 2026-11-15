"""Typed, offline-only editors. Enter commits locally, Escape cancels."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLineEdit, QStyledItemDelegate
from ..a650lib.offline_project import ENUMS, DECIMALS, UNITS, validate


class ProjectDelegate(QStyledItemDelegate):
    CODE_ROLE = Qt.ItemDataRole.UserRole + 1
    VALUE_ROLE = Qt.ItemDataRole.UserRole + 2

    def createEditor(self, parent, option, index):
        code = index.data(self.CODE_ROLE)
        if code in ENUMS:
            editor = QComboBox(parent)
            editor.addItem('Выберите значение…', None)
            for value, label in ENUMS[code].items():
                editor.addItem(f'{value} — {label}', value)
            return editor
        if code in DECIMALS:
            editor = QLineEdit(parent)
            low, high, step = DECIMALS[code]
            editor.setPlaceholderText(f'{low} … {high} {UNITS[code]} (шаг {step})')
            return editor
        return None

    def setEditorData(self, editor, index):
        value = index.data(self.VALUE_ROLE)
        if isinstance(editor, QComboBox):
            index = editor.findData(value)
            if value is not None and index < 0:
                editor.addItem(f'Неизвестное значение ({value})', value)
                index = editor.count() - 1
            editor.setCurrentIndex(max(0, index))
        else:
            editor.setText('' if value is None else str(value).replace('.', ','))

    def setModelData(self, editor, model, index):
        code = index.data(self.CODE_ROLE)
        value = editor.currentData() if isinstance(editor, QComboBox) else editor.text()
        try:
            value = validate(code, value)
        except ValueError as exc:
            self.parent().show_validation(str(exc))
            return
        model.setData(index, value, self.VALUE_ROLE)
        model.setData(index, f'{value} — {ENUMS[code][value]}' if code in ENUMS
                      else f'{value.replace(".", ",")} {UNITS[code]}', Qt.ItemDataRole.DisplayRole)
