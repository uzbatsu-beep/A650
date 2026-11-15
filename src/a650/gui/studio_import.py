"""ODS preview dialog; raw Read data never becomes a live device observation."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
                              QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
                              QVBoxLayout)
from ..a650lib.editor_profile import load_editor_profile


class StudioImportDialog(QDialog):
    def __init__(self, rows, model, parent=None, *, project_values=None):
        super().__init__(parent)
        self.rows = tuple(rows)
        self.project_values = dict(project_values or {})
        self.profile = load_editor_profile(model)
        self.setWindowTitle(f'Предпросмотр OniDriveStudio ODS · {model}')
        self.resize(1280, 650)
        layout = QVBoxLayout(self)
        note = QLabel('Формат восстановлен по EXE; совместимость с реальным экспортом ещё не подтверждена.\n'
                      'Set / Read — целые числа из файла, а не актуальные показания ПЧ.\n'
                      'Отметьте значения перечислений для переноса в проект. Настройки соединения не применяются.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(len(self.rows), 8)
        self.table.setHorizontalHeaderLabels(['Выбрать', 'Код', 'Параметр', 'Проект сейчас', 'Set · целое',
                                               'Read · целое', 'Check в файле', 'Результат проверки'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(65)
        for column, width in ((0, 70), (1, 80), (3, 190), (4, 100), (5, 105), (6, 110)):
            self.table.setColumnWidth(column, width)
        for i, row in enumerate(self.rows):
            raw = lambda value: 'Скрыто' if row.sensitive else 'Нет в файле' if value is None else str(value)
            current = 'Скрыто' if row.sensitive else self._display_value(row.code, self.project_values.get(row.code))
            result = row.reason
            if row.importable:
                change = ('Без изменения' if self.project_values.get(row.code) == row.import_value else
                          'Заменит значение' if row.code in self.project_values else 'Добавит значение')
                result = f'{self._display_value(row.code, row.import_value)} · {change}'
            for j, text in enumerate(('', row.code, row.name, current, raw(row.set_value), raw(row.read_value),
                                      'Да' if row.checked_in_source else 'Нет', result)):
                item = QTableWidgetItem(text)
                item.setToolTip(f'{text}\n{row.reason}' if j == 7 else text)
                if j == 0:
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                                  (Qt.ItemFlag.ItemIsUserCheckable if row.importable else Qt.ItemFlag.NoItemFlags))
                    if row.importable:
                        item.setCheckState(Qt.CheckState.Unchecked)
                self.table.setItem(i, j, item)
        layout.addWidget(self.table)
        self.details = QLabel('Выберите строку, чтобы прочитать результат проверки полностью.')
        self.details.setWordWrap(True)
        self.details.setMinimumHeight(42)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.details)
        self.table.currentCellChanged.connect(self._show_details)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Перенести выбранные в проект')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Закрыть без переноса')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.table.itemChanged.connect(self._update)
        self._update()

    def _display_value(self, code, value):
        if value is None:
            return 'Не задано'
        if code in self.profile.enums:
            return f'{self.profile.enums[code].get(value, "Неизвестный код")} ({value})'
        return f'{value} {self.profile.units.get(code, "")}'.strip()

    def selected_changes(self):
        return {row.code: row.import_value for i, row in enumerate(self.rows)
                if row.importable and self.table.item(i, 0).checkState() == Qt.CheckState.Checked}

    def _show_details(self, index, *_):
        if 0 <= index < len(self.rows):
            row = self.rows[index]
            self.details.setText(f'{row.code} · {row.name}\n{row.reason}')

    def _update(self, *_):
        changes = self.selected_changes()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(changes))
        replaced = sum(code in self.project_values and self.project_values[code] != value
                       for code, value in changes.items())
        self.summary.setText(f'Выбрано: {len(changes)} · Заменят значения проекта: {replaced}. '
                             'Перенос — одно действие отмены. Записи в ПЧ не будет.')
