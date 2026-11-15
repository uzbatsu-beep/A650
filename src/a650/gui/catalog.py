"""Typed offline projects, history and comparisons; no hardware writes."""
from pathlib import Path
from datetime import datetime
import time
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPlainTextEdit, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget, QSplitter, QFrame, QPushButton,
                               QFileDialog, QMessageBox, QCheckBox)
from ..a650lib.catalog import load_catalog, search_catalog
from ..a650lib.offline_project import OfflineProject, ENUMS, DECIMALS, UNITS
from .project_delegate import ProjectDelegate


def address(value):
    return 'не указан' if value is None else f'0x{value:04X}'


class CatalogView(QWidget):
    readRequested = Signal(object, int)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = ()
        self.visible_entries = ()
        self.projects = {name: OfflineProject(name) for name in ("A650", "A650M")}
        self.unsaved = set()
        self.comparison = None
        self._rendering = False
        self.observed = {}
        self._read_token = 0
        self._reading = False
        self._simulated_connection = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(14)
        eyebrow = QLabel("ONI DRIVE STUDIO   /   БИБЛИОТЕКА")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Параметры привода")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Найдите параметр. Дважды нажмите значение в колонке «Проект», чтобы изменить его.")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        actions = QHBoxLayout()
        self.open_button = QPushButton("Открыть проект…")
        self.save_button = QPushButton("Сохранить проект…")
        self.compare_button = QPushButton("Сравнить с проектом…")
        self.clear_compare_button = QPushButton("Закрыть сравнение")
        self.clear_compare_button.setEnabled(False)
        self.undo_button = QPushButton("Отменить")
        self.redo_button = QPushButton("Повторить")
        self.undo_button.setToolTip("Отменить изменение · Ctrl+Z")
        self.redo_button.setToolTip("Повторить изменение · Ctrl+Shift+Z")
        self.project_status = QLabel("Офлайн-проект · нет несохранённых изменений")
        self.project_status.setObjectName("muted")
        actions.addWidget(self.open_button)
        actions.addWidget(self.save_button)
        actions.addWidget(self.compare_button)
        actions.addWidget(self.clear_compare_button)
        actions.addWidget(self.undo_button)
        actions.addWidget(self.redo_button)
        self.read_button = QPushButton("Считать из симулятора")
        self.read_button.setEnabled(False)
        self.read_button.clicked.connect(self._request_read)
        actions.addWidget(self.read_button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(self.project_status)
        self.open_button.clicked.connect(self._open_project)
        self.save_button.clicked.connect(self._save_project)
        self.compare_button.clicked.connect(self._compare_project)
        self.clear_compare_button.clicked.connect(self._clear_comparison)
        self.undo_button.clicked.connect(lambda: self._history(False))
        self.redo_button.clicked.connect(lambda: self._history(True))
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=lambda: self._history(False))
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=lambda: self._history(True))
        filters = QHBoxLayout()
        self.model = QComboBox()
        self.model.addItems(['A650', 'A650M'])
        self.group = QComboBox()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Поиск по коду или названию')
        for label, widget in [('Модель:', self.model), ('Группа:', self.group), ('', self.search)]:
            if label:
                filters.addWidget(QLabel(label))
            filters.addWidget(widget)
        self.editable_only = QCheckBox('Можно изменить офлайн')
        filters.addWidget(self.editable_only)
        self.differences_only = QCheckBox('Только отличия')
        self.differences_only.setEnabled(False)
        filters.addWidget(self.differences_only)
        layout.addLayout(filters)
        warning = QLabel('Офлайн-проект: доступные поля можно изменить. Запись в ПЧ из таблицы отключена.')
        warning.setWordWrap(True)
        warning.setObjectName("notice")
        layout.addWidget(warning)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Код', 'Название', 'Образец', 'Проверка', 'Проект', 'Сравнение', 'ПЧ · симулятор'])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.setItemDelegateForColumn(4, ProjectDelegate(self))

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setColumnWidth(0, 78)
        self.table.setColumnWidth(2, 155)
        self.table.setColumnWidth(3, 135)
        self.table.setColumnWidth(4, 155)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 240)
        content = QSplitter()
        content.addWidget(self.table)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setStyleSheet("padding: 14px; line-height: 1.5;")
        self.detail.setPlaceholderText('Выберите параметр для просмотра сведений и источника')
        detail_panel = QFrame()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(12, 0, 0, 0)
        heading = QLabel("Сведения о параметре")
        heading.setStyleSheet("font-size: 16px; font-weight: 700; padding: 4px;")
        detail_layout.addWidget(heading)
        detail_layout.addWidget(self.detail)
        content.addWidget(detail_panel)
        content.setSizes([830, 300])
        content.setStretchFactor(0, 3)
        content.setStretchFactor(1, 2)
        layout.addWidget(content, 1)
        self.model.currentTextChanged.connect(self._load)
        self.group.currentTextChanged.connect(self._render)
        self.search.textChanged.connect(self._render)
        self.editable_only.toggled.connect(self._render)
        self.differences_only.toggled.connect(self._render)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self._load(self.model.currentText())
        self._freshness_timer = QTimer(self)
        self._freshness_timer.setInterval(1000)
        self._freshness_timer.timeout.connect(self._expire_observations)
        self._freshness_timer.start()

    def _load(self, model):
        self._read_token += 1
        self._reading = False
        self.observed.clear()
        self.read_button.setEnabled(self._simulated_connection)
        self.entries = load_catalog(model)
        if self.comparison is not None and self.comparison.model != model:
            self.comparison = None
        self.group.blockSignals(True)
        self.group.clear()
        self.group.addItem('Все группы')
        self.group.addItems(sorted({e.group for e in self.entries}))
        self.group.blockSignals(False)
        self.differences_only.setEnabled(self.comparison is not None)
        self.clear_compare_button.setEnabled(self.comparison is not None)
        if self.comparison is None:
            self.differences_only.setChecked(False)
        self._update_project_status()
        self._render()

    def set_connection(self, simulated):
        self._read_token += 1
        self._reading = False
        self._simulated_connection = simulated
        self.read_button.setEnabled(simulated)
        for item in self.observed.values():
            item['stale'] = True
        self._render()

    def _request_read(self):
        if self._reading or not self._simulated_connection:
            return
        codes = [e.code for e in self.visible_entries if e.code in ENUMS
                 and not e.conflict and not e.duplicate]
        if not codes:
            self.show_validation('В текущем фильтре нет параметров с поддержанным кодеком чтения')
            return
        self._reading = True
        self._read_token += 1
        self.read_button.setEnabled(False)
        self.project_status.setText('Чтение перечислений из симулятора…')
        self.readRequested.emit(codes, self._read_token)

    def receive_values(self, token, values):
        if token != self._read_token:
            return
        now = time.monotonic()
        stamp = datetime.now().strftime('%H:%M:%S')
        for code, value in values.items():
            self.observed[code] = {'value': value, 'time': now, 'stamp': stamp, 'stale': False}
        self._reading = False
        self.read_button.setEnabled(self._simulated_connection)
        self._update_project_status()
        self._render()

    def read_failed(self, token, message):
        if token != self._read_token:
            return
        for observation in self.observed.values():
            observation['stale'] = True
        self._reading = False
        self.read_button.setEnabled(self._simulated_connection)
        self._render()
        self.show_validation('Ошибка чтения: ' + message)

    def _expire_observations(self):
        if self.table.state() == QAbstractItemView.State.EditingState:
            return
        changed = False
        for observation in self.observed.values():
            if not observation['stale'] and time.monotonic() - observation['time'] > 5:
                observation['stale'] = True
                changed = True
        if changed:
            self._render()

    def show_validation(self, message):
        self.project_status.setText(message)

    def _update_project_status(self):
        model = self.model.currentText()
        project = self.projects[model]
        if project.dirty:
            self.unsaved.add(model)
        else:
            self.unsaved.discard(model)
        self.undo_button.setEnabled(project.can_undo)
        self.redo_button.setEnabled(project.can_redo)
        count = len(project.values)
        state = "есть несохранённые изменения" if model in self.unsaved else "сохранено"
        self.project_status.setText(f"Офлайн-проект {model} · {count} знач. · {state}")

    def _save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить офлайн-проект", "", "Проект A650 (*.a650.json)")
        if not path:
            return
        try:
            self.projects[self.model.currentText()].save(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Не удалось сохранить проект", str(exc))
            return
        self.unsaved.discard(self.model.currentText())
        self._update_project_status()

    def _compare_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Сравнить с проектом", "", "Проект A650 (*.a650.json *.json)")
        if not path:
            return
        try:
            project = OfflineProject.load(path)
            if project.model != self.model.currentText():
                raise ValueError("Модели проектов не совпадают")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Не удалось сравнить", str(exc))
            return
        self.comparison = project
        self.clear_compare_button.setEnabled(True)
        self.differences_only.setEnabled(True)
        self._render()
        self.compare_button.setToolTip(f'Образец: {Path(path).name}')

    def _clear_comparison(self):
        self.comparison = None
        self.clear_compare_button.setEnabled(False)
        self.differences_only.setEnabled(False)
        self.differences_only.setChecked(False)
        self._render()
        self._update_project_status()

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть офлайн-проект", "", "Проект A650 (*.a650.json *.json)")
        if not path:
            return
        try:
            project = OfflineProject.load(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Не удалось открыть проект", str(exc))
            return
        if project.model in self.unsaved:
            answer = QMessageBox.question(self, "Несохранённые изменения",
                f"Заменить несохранённый проект {project.model}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.projects[project.model] = project
        self.unsaved.discard(project.model)
        if self.model.currentText() != project.model:
            self.model.setCurrentText(project.model)
        else:
            self._render()
            self._update_project_status()

    def _render(self, *_):
        self.table.setColumnHidden(2, self.comparison is None)
        self.table.setColumnHidden(5, self.comparison is None)
        selected = self.table.currentRow()
        selected_key = None
        if 0 <= selected < len(self.visible_entries):
            entry = self.visible_entries[selected]
            selected_key = (entry.code, entry.source_location)
        self._rendering = True
        self.visible_entries = search_catalog(self.entries, self.search.text(), self.group.currentText())
        if self.editable_only.isChecked():
            self.visible_entries = tuple(entry for entry in self.visible_entries
                if (entry.code in ENUMS or entry.code in DECIMALS)
                and not entry.duplicate and not entry.conflict)
        project = self.projects[self.model.currentText()]
        if self.differences_only.isChecked() and self.comparison is not None:
            self.visible_entries = tuple(e for e in self.visible_entries
                if project.values.get(e.code) != self.comparison.values.get(e.code))
        self.table.setRowCount(len(self.visible_entries))
        for row, entry in enumerate(self.visible_entries):
            status = 'Конфликт' if entry.conflict else 'Дубликат' if entry.duplicate else 'Не проверено на ПЧ'
            if entry.conflict and entry.duplicate:
                status = 'Конфликт, дубликат'
            editable = entry.code in ENUMS or entry.code in DECIMALS
            value = project.values.get(entry.code)
            if value is None:
                display = 'Выбрать…' if editable else 'Не определено'
            elif entry.code in ENUMS:
                label = ENUMS[entry.code].get(value)
                display = f'{value} — {label}' if label is not None else f'Неизвестное значение ({value})'
            else:
                display = f'{value.replace(".", ",")} {UNITS[entry.code]}'
            other = self.comparison.values.get(entry.code) if self.comparison else None
            if self.comparison is None:
                comparison = 'Не выбрано'
            elif value is None and other is None:
                comparison = 'Нет в обоих'
            elif value is None:
                comparison = 'Только в образце'
            elif other is None:
                comparison = 'Только в проекте'
            elif other == value:
                comparison = 'Совпадает'
            else:
                comparison = 'Отличается'
            sample = self._display_value(entry.code, other) if self.comparison else '—'
            observation = self.observed.get(entry.code)
            if observation:
                quality = 'Устарело' if observation['stale'] else 'Считано'
                device = self._display_value(entry.code, observation['value'])
                if not observation['stale'] and value is not None:
                    device += ' · совпадает' if value == observation['value'] else ' · отличается'
                device += f" · {quality} {observation['stamp']}"
            else:
                device = 'Не прочитано' if entry.code in ENUMS else 'Нет подтверждённого кодека'
            for col, text in enumerate((entry.code, entry.name, sample, status, display, comparison, device)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 4 and editable and not entry.duplicate and not entry.conflict:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    item.setData(ProjectDelegate.CODE_ROLE, entry.code)
                    item.setData(ProjectDelegate.VALUE_ROLE, value)
                if col == 5 and self.comparison is not None:
                    item.setToolTip(f'Образец: {self._display_value(entry.code, other)}\nПроект: {self._display_value(entry.code, value)}')
                self.table.setItem(row, col, item)
        self._rendering = False
        self.detail.clear()
        if selected_key:
            for row, entry in enumerate(self.visible_entries):
                if (entry.code, entry.source_location) == selected_key:
                    self.table.selectRow(row)
                    self._show_detail()
                    break

    @staticmethod
    def _display_value(code, value):
        if value is None:
            return 'Не задано'
        if code in ENUMS:
            return f'{value} — {ENUMS[code].get(value, "Неизвестное значение")}'
        return f'{str(value).replace(".", ",")} {UNITS.get(code, "")}'.strip()

    def commit_edit(self, code, value):
        self.projects[self.model.currentText()].set(code, value)
        self._update_project_status()
        self._render()

    def _history(self, redo):
        project = self.projects[self.model.currentText()]
        if redo:
            project.redo()
        else:
            project.undo()
        self._update_project_status()
        self._render()

    def _show_detail(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.visible_entries):
            self.detail.clear()
            return
        entry = self.visible_entries[row]
        project_value = self.projects[self.model.currentText()].values.get(entry.code)
        conflicts = [f'Проект: {self._display_value(entry.code, project_value)}']
        observation = self.observed.get(entry.code)
        if observation:
            raw = observation['value']
            conflicts.append(f"ПЧ · симулятор: {self._display_value(entry.code, raw)}; последнее чтение {observation['stamp']}")
            if observation['stale']:
                conflicts.append('Данные устарели: повторите чтение перед сравнением.')
            elif project_value is not None:
                conflicts.append('Проект совпадает с симулятором.' if project_value == raw else 'Проект отличается от симулятора.')
        if self.comparison is not None:
            other = self.comparison.values.get(entry.code)
            conflicts.append(f'Образец: {self._display_value(entry.code, other)}')
        if entry.duplicate:
            conflicts.append('Код повторяется в исходном каталоге EXE.')
        if entry.conflict:
            conflicts.append(f'Конфликт с формулой PDF: RAM {address(entry.expected_ram)}, EEPROM {address(entry.expected_eeprom)}.')
        if entry.code.startswith('H'):
            conflicts.append('Адреса H00 отсутствуют в приложении Modbus PDF; значения EXE требуют проверки.')
        if entry.code == 'F15.01':
            conflicts.append('Варианты приведены по PDF, стр. 133. Для варианта 8E1 текст EXE расходится с PDF; формат по умолчанию также требует проверки.')
        if entry.code == 'F13.01':
            conflicts.append('Офлайн-ввод 0,0–100,0 %, шаг 0,1; формат передачи в ПЧ не подтверждён.')
        if entry.code in ENUMS and entry.code != 'F15.01':
            conflicts.append('Варианты для офлайн-проекта сверены с руководством A650, издание 3, таблица 5.2. Применимость к конкретной модели и прошивке требует проверки.')
        if entry.code in DECIMALS and entry.code != 'F13.01':
            conflicts.append('Пределы офлайн-ввода взяты из руководства A650, издание 3, таблица 5.2. Масштаб передачи и условия записи не подтверждены.')
        self.detail.setPlainText('\n'.join([
            f'{self.model.currentText()} · {entry.code} — {entry.name}',
            f'Диапазон в EXE: {entry.minimum or "не указан"} … {entry.maximum or "не указан"}; по умолчанию: {entry.default or "не указано"}',
            f'RAM в EXE: {address(entry.ram)}; EEPROM в EXE: {address(entry.eeprom)}',
            'Единицы: см. название; масштаб Modbus: не подтверждён. Доступ: не определён.',
            f'Источник: OniDriveStudio 1.2.7.0, исследовательская выгрузка; инструкция {entry.source_location}.',
            'Формула адреса F/U: руководство A650, издание 3, приложение A.4.3, стр. 158.',
            'Проверка на устройстве: не проводилась. Запись из каталога недоступна.',
            'Показания симулятора не являются проверкой реального ПЧ.',
            *conflicts,
        ]))
