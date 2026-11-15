"""Offline, read-only parameter catalog."""
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPlainTextEdit, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget, QSplitter, QFrame)
from ..a650lib.catalog import load_catalog, search_catalog


def address(value):
    return 'не указан' if value is None else f'0x{value:04X}'


class CatalogView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = ()
        self.visible_entries = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(14)
        eyebrow = QLabel("ONI DRIVE STUDIO   /   БИБЛИОТЕКА")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Параметры привода")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Найдите параметр и проверьте его адрес и источник данных.")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
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
        layout.addLayout(filters)
        warning = QLabel('Исследовательские данные: адреса и свойства требуют сверки. Каталог доступен только для просмотра.')
        warning.setWordWrap(True)
        warning.setObjectName("notice")
        layout.addWidget(warning)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Код', 'Название', 'RAM по EXE', 'Проверка'])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 190)
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
        content.setStretchFactor(0, 3)
        content.setStretchFactor(1, 2)
        layout.addWidget(content, 1)
        self.model.currentTextChanged.connect(self._load)
        self.group.currentTextChanged.connect(self._render)
        self.search.textChanged.connect(self._render)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self._load(self.model.currentText())

    def _load(self, model):
        self.entries = load_catalog(model)
        self.group.blockSignals(True)
        self.group.clear()
        self.group.addItem('Все группы')
        self.group.addItems(sorted({e.group for e in self.entries}))
        self.group.blockSignals(False)
        self._render()

    def _render(self, *_):
        self.visible_entries = search_catalog(self.entries, self.search.text(), self.group.currentText())
        self.table.setRowCount(len(self.visible_entries))
        for row, entry in enumerate(self.visible_entries):
            status = 'Конфликт' if entry.conflict else 'Дубликат' if entry.duplicate else 'Не проверено на ПЧ'
            if entry.conflict and entry.duplicate:
                status = 'Конфликт, дубликат'
            for col, value in enumerate((entry.code, entry.name, address(entry.ram), status)):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.detail.clear()

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
        self.detail.setPlainText('\n'.join([
            f'{self.model.currentText()} · {entry.code} — {entry.name}',
            f'Диапазон в EXE: {entry.minimum or "не указан"} … {entry.maximum or "не указан"}; по умолчанию: {entry.default or "не указано"}',
            f'RAM в EXE: {address(entry.ram)}; EEPROM в EXE: {address(entry.eeprom)}',
            'Единицы: см. название; масштаб Modbus: не подтверждён. Доступ: не определён.',
            f'Источник: OniDriveStudio 1.2.7.0, исследовательская выгрузка; инструкция {entry.source_location}.',
            'Формула адреса F/U: руководство A650, издание 3, приложение A.4.3, стр. 158.',
            'Проверка на устройстве: не проводилась. Запись из каталога недоступна.',
            *conflicts,
        ]))
