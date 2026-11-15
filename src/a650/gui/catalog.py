"""Offline, read-only parameter catalog."""
from PySide6.QtCore import Qt
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = ()
        self.visible_entries = ()
        self.projects = {name: OfflineProject(name) for name in ("A650", "A650M")}
        self.unsaved = set()
        self.comparison = None
        self._rendering = False
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
        self.project_status = QLabel("Офлайн-проект · нет несохранённых изменений")
        self.project_status.setObjectName("muted")
        actions.addWidget(self.open_button)
        actions.addWidget(self.save_button)
        actions.addWidget(self.compare_button)
        actions.addStretch()
        actions.addWidget(self.project_status)
        layout.addLayout(actions)
        self.open_button.clicked.connect(self._open_project)
        self.save_button.clicked.connect(self._save_project)
        self.compare_button.clicked.connect(self._compare_project)
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
        layout.addLayout(filters)
        warning = QLabel('Офлайн-проект: доступные поля можно изменить. Запись в ПЧ из таблицы отключена.')
        warning.setWordWrap(True)
        warning.setObjectName("notice")
        layout.addWidget(warning)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Код', 'Название', 'RAM по EXE', 'Проверка', 'Проект', 'Сравнение'])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.setItemDelegateForColumn(4, ProjectDelegate(self))
        self.table.itemChanged.connect(self._item_changed)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setColumnWidth(0, 78)
        self.table.setColumnWidth(2, 88)
        self.table.setColumnWidth(3, 135)
        self.table.setColumnWidth(4, 155)
        self.table.setColumnWidth(5, 100)
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
        self.table.itemSelectionChanged.connect(self._show_detail)
        self._load(self.model.currentText())

    def _load(self, model):
        self.entries = load_catalog(model)
        if self.comparison is not None and self.comparison.model != model:
            self.comparison = None
        self.group.blockSignals(True)
        self.group.clear()
        self.group.addItem('Все группы')
        self.group.addItems(sorted({e.group for e in self.entries}))
        self.group.blockSignals(False)
        self._update_project_status()
        self._render()

    def show_validation(self, message):
        self.project_status.setText(message)

    def _update_project_status(self):
        model = self.model.currentText()
        count = len(self.projects[model].values)
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
        self._render()
        self.project_status.setText("Сравнение с другим офлайн-проектом · значения ПЧ не считаны")

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
        self._rendering = True
        self.visible_entries = search_catalog(self.entries, self.search.text(), self.group.currentText())
        if self.editable_only.isChecked():
            self.visible_entries = tuple(entry for entry in self.visible_entries
                if (entry.code in ENUMS or entry.code in DECIMALS)
                and not entry.duplicate and not entry.conflict)
        self.table.setRowCount(len(self.visible_entries))
        project = self.projects[self.model.currentText()]
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
            if other is None or value is None:
                comparison = 'Не задано' if self.comparison else 'Не выбрано'
            elif other == value:
                comparison = 'Совпадает'
            else:
                comparison = f'Было: {other}'
            for col, text in enumerate((entry.code, entry.name, address(entry.ram), status, display, comparison)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 4 and editable and not entry.duplicate and not entry.conflict:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    item.setData(ProjectDelegate.CODE_ROLE, entry.code)
                    item.setData(ProjectDelegate.VALUE_ROLE, value)
                self.table.setItem(row, col, item)
        self._rendering = False
        self.detail.clear()

    def _item_changed(self, item):
        if self._rendering or item.column() != 4:
            return
        code, value = item.data(ProjectDelegate.CODE_ROLE), item.data(ProjectDelegate.VALUE_ROLE)
        if code is not None and value is not None:
            self.projects[self.model.currentText()].set(code, value)
            self.unsaved.add(self.model.currentText())
            self._update_project_status()
            if self.comparison is not None:
                self._render()

    def _show_detail(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.visible_entries):
            self.detail.clear()
            return
        entry = self.visible_entries[row]
        conflicts = []
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
            'Значение ПЧ: не прочитано; сравнение недоступно до чтения.',
            *conflicts,
        ]))
