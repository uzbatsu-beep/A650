"""Reusable Qt widgets for the a650 configurator GUI.

All widgets are passive: they emit intents (connect, start, write...) and the
main window wires them to DriveController. No widget talks to Modbus directly.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..a650lib.register_map import RegisterMap

ACCENT = "#0a8d80"
BG = "#f2f5f7"
PANEL = "#ffffff"
FG = "#182b3b"
MUTED = "#657789"

STATE_NAMES = {0: "Настройка параметров", 1: "Работа", 2: "Толчковый режим",
               3: "Обучение", 4: "Останов", 5: "Останов толчкового режима",
               6: "Неисправность"}


def style_app() -> str:
    """Calm, high-contrast desktop theme for field use."""
    return """
    QWidget { background: #f2f5f7; color: #182b3b; font-family: 'Segoe UI'; font-size: 13px; }
    QMainWindow, QTabWidget::pane { background: #f2f5f7; border: 0; }
    QTabBar::tab { background: transparent; color: #64778a; padding: 14px 24px; font-weight: 600; border-bottom: 3px solid transparent; }
    QTabBar::tab:selected { color: #087f75; border-bottom: 3px solid #0a8d80; }
    QGroupBox { background: white; border: 1px solid #dce5ea; border-radius: 12px; margin-top: 16px; padding: 14px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 6px; color: #4f6475; }
    QPushButton { background: white; border: 1px solid #c9d7dd; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
    QPushButton:hover { border-color: #0a8d80; color: #087f75; }
    QPushButton:disabled { color: #9cacb6; background: #f4f6f7; }
    QPushButton#primary { background: #087f75; color: white; border: 0; }
    QPushButton#primary:hover { background: #066e66; }
    QPushButton#danger { background: #b94040; color: white; border: 0; }
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: white; border: 1px solid #cad8df; border-radius: 7px; padding: 8px 10px; selection-background-color: #bce8df; }
    QComboBox::drop-down { border: 0; width: 24px; }
    QComboBox QAbstractItemView { background: white; selection-background-color: #d9f1ec; selection-color: #123b36; }
    QPlainTextEdit, QListWidget, QTableWidget { background: white; border: 1px solid #dce5ea; border-radius: 10px; selection-background-color: #ddf3ef; selection-color: #16413b; }
    QTableWidget::item { padding: 8px; border-bottom: 1px solid #eef2f4; }
    QTableWidget::item:selected { background: #ddf3ef; color: #16413b; }
    QHeaderView::section { background: #f7f9fa; color: #6c7f8d; border: 0; border-bottom: 1px solid #dce5ea; padding: 10px; font-size: 11px; font-weight: 700; }
    QScrollBar:vertical { background: transparent; width: 9px; }
    QScrollBar::handle:vertical { background: #c3d0d6; border-radius: 4px; min-height: 24px; }
    QCheckBox { spacing: 8px; }
    QStatusBar { background: #e8eef1; color: #647788; }
    QLabel#big { font-size: 34px; font-weight: 700; }
    QLabel#unit, QLabel#muted { color: #728694; }
    QLabel#pageTitle { font-size: 27px; font-weight: 700; color: #172e3e; }
    QLabel#eyebrow { color: #07877a; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
    QLabel#notice { background: #e3f3ef; color: #256759; border-radius: 8px; padding: 10px 14px; }
    QLabel#stateStopped { color: #71838d; font-weight: 700; }
    QLabel#stateRun { color: #087f75; font-weight: 700; }
    QLabel#stateFault { color: #b94040; font-weight: 700; }
    """


class ConnectionPanel(QGroupBox):
    """Connection settings; emits validated controller keyword arguments."""

    connectRequested = Signal(dict)
    disconnectRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Подключение к ПЧ", parent)
        self._connected = False
        self._busy = False
        form = QFormLayout(self)
        self.mode = QComboBox()
        self.mode.addItems(["Симулятор (без оборудования)", "Последовательный порт RS-485"])
        self.port = QComboBox()
        self.port.setEditable(True)
        self.port.lineEdit().setPlaceholderText("Выберите порт или введите COM3")
        self.baud = QComboBox()
        self.baud.addItems(["4800", "9600", "19200", "38400", "57600", "115200"])
        self.baud.setCurrentText("9600")
        self.parity = QComboBox()
        for text, value in [("Нет (N)", "N"), ("Чётная (E)", "E"), ("Нечётная (O)", "O")]:
            self.parity.addItem(text, value)
        self.stopbits = QComboBox()
        self.stopbits.addItems(["1", "2"])
        self.slave = QSpinBox(minimum=1, maximum=247, value=1)
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(0.1, 10.0)
        self.timeout.setDecimals(2)
        self.timeout.setSingleStep(0.1)
        self.timeout.setValue(0.5)
        self.timeout.setSuffix(" с")
        self.retries = QSpinBox(minimum=0, maximum=3, value=2)
        self.retries.setToolTip("Дополнительные попытки чтения. Запись автоматически не повторяется.")
        self.allow_write = QCheckBox("Разрешить запись и управление")
        self.allow_write.setToolTip("Только известные команды пуска, останова и задания частоты. По умолчанию — чтение.")
        self.btn_refresh = QPushButton("Обновить порты")
        self.btn_refresh.clicked.connect(self.refresh_ports)
        self.btn_connect = QPushButton("Подключиться")
        self.btn_connect.setObjectName("primary")
        self.btn_connect.clicked.connect(self._on_connect)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #e3b341; font-size: 12px;")
        hint = QLabel("Настройки должны совпадать с F15 на пульте ПЧ. "
                      "При подключении выполняется только чтение.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        for label, widget in [("Режим:", self.mode), ("Порт:", self.port),
                              ("Скорость, бод:", self.baud), ("Чётность:", self.parity),
                              ("Биты данных:", QLabel("8 (Modbus RTU)")),
                              ("Стоповые биты:", self.stopbits), ("Адрес ПЧ:", self.slave),
                              ("Тайм-аут ответа:", self.timeout), ("Повторы чтения:", self.retries)]:
            form.addRow(label, widget)
        form.addRow(self.allow_write)
        form.addRow(hint)
        form.addRow(self.message)
        form.addRow(self.btn_refresh)
        form.addRow(self.btn_connect)
        self.mode.currentIndexChanged.connect(self._update_enabled)
        self.refresh_ports()
        self._update_enabled()

    def refresh_ports(self) -> None:
        from .controller import list_serial_ports
        current = self.port.currentText().strip()
        self.port.clear()
        self.port.addItems(list_serial_ports())
        if current:
            self.port.setCurrentText(current)

    def _update_enabled(self) -> None:
        unlocked = not (self._connected or self._busy)
        serial_mode = self.mode.currentIndex() == 1
        for widget in (self.port, self.baud, self.parity, self.stopbits, self.btn_refresh):
            widget.setEnabled(serial_mode and unlocked)
        for widget in (self.mode, self.slave, self.timeout, self.retries, self.allow_write):
            widget.setEnabled(unlocked)
        self.btn_connect.setEnabled(not self._busy)

    def _on_connect(self) -> None:
        if self._busy:
            return
        if self._connected:
            self.disconnectRequested.emit()
            return
        simulate = self.mode.currentIndex() == 0
        port = self.port.currentText().strip()
        parity = self.parity.currentData()
        stopbits = int(self.stopbits.currentText())
        if not simulate and not port:
            self.message.setText("Укажите COM-порт. Если его нет в списке, введите имя вручную.")
            return
        if not simulate and parity != "N" and stopbits != 1:
            self.message.setText("Для чётной и нечётной чётности выберите 1 стоповый бит (F15.01).")
            return
        self.message.clear()
        self.set_busy(True)
        self.connectRequested.emit({
            "simulate": simulate, "port": port,
            "baud": int(self.baud.currentText()), "parity": parity, "stopbits": stopbits,
            "slave": self.slave.value(), "timeout_s": self.timeout.value(),
            "retries": self.retries.value(), "allow_write": self.allow_write.isChecked(),
        })

    def set_busy(self, on: bool) -> None:
        self._busy = on
        self.btn_connect.setText("Проверка связи…" if on else
                                 "Отключиться" if self._connected else "Подключиться")
        self._update_enabled()

    def set_connected(self, on: bool, desc: str = "") -> None:
        self._connected = on
        self.set_busy(False)
        self.message.clear()

    def connection_failed(self, message: str) -> None:
        self.set_connected(False)
        self.message.setText("Не удалось подключиться. Проверьте порт и настройки ПЧ. " + message)

    def set_write_checked(self, checked: bool) -> None:
        self.allow_write.setChecked(checked)


class ControlDeck(QGroupBox):
    """Big run/stop buttons + frequency setpoint. Emits user intents."""

    startRequested = Signal()
    stopRequested = Signal()
    setFreqRequested = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__("Control", parent)
        lay = QVBoxLayout()
        self.freq = QDoubleSpinBox()
        self.freq.setRange(0.0, 400.0)
        self.freq.setDecimals(2)
        self.freq.setSuffix(" Hz")
        self.freq.setSingleStep(0.5)
        self.freq.setValue(5.0)
        btns = QHBoxLayout()
        self.btn_start = QPushButton("▶  START")
        self.btn_start.setObjectName("primary")
        self.btn_stop = QPushButton("■  STOP")
        self.btn_stop.setObjectName("danger")
        self.btn_set = QPushButton("Set freq")
        self.btn_start.clicked.connect(self.startRequested)
        self.btn_stop.clicked.connect(self.stopRequested)
        self.btn_set.clicked.connect(lambda: self.setFreqRequested.emit(self.freq.value()))
        btns.addWidget(self.btn_start)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_set)
        hint = QLabel("Writes follow docs/REGISTERS.md: 0x2000←0x0001 run fwd, ←0x0005 stop;\n"
                      "0x2001←Hz×100 (setpoint). Reverse/jog bits are research TODO.")
        hint.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        lay.addWidget(self.freq)
        lay.addLayout(btns)
        lay.addWidget(hint)
        self.setLayout(lay)

    def set_enabled(self, enabled: bool) -> None:
        for w in (self.freq, self.btn_start, self.btn_stop, self.btn_set):
            w.setEnabled(enabled)


class StatusCard(QGroupBox):
    """Live readout of the status block + output frequency gauge."""

    def __init__(self, parent=None) -> None:
        super().__init__("Live status", parent)
        outer = QVBoxLayout()
        top = QHBoxLayout()
        self.state_lbl = QLabel("—")
        self.state_lbl.setObjectName("stateStopped")
        self.state_lbl.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        top.addWidget(self.state_lbl)
        top.addStretch()
        self.freq_lbl = QLabel("0.00")
        self.freq_lbl.setObjectName("big")
        unit = QLabel("Hz")
        unit.setObjectName("unit")
        top.addWidget(self.freq_lbl)
        top.addWidget(unit)
        outer.addLayout(top)
        self.gauge = _FreqGauge()
        self.gauge.setMinimumHeight(26)
        outer.addWidget(self.gauge)
        grid = QFormLayout()
        self.fault_lbl = QLabel("none")
        self.warn_lbl = QLabel("none")
        self.bits_lbl = QLabel("0x0000")
        self.ts_lbl = QLabel("—")
        grid.addRow("Fault (0x2102):", self.fault_lbl)
        grid.addRow("Warning (0x2103):", self.warn_lbl)
        grid.addRow("Status bits (0x2101):", self.bits_lbl)
        grid.addRow("Updated:", self.ts_lbl)
        outer.addLayout(grid)
        self.setLayout(outer)
        self.show_state(None)

    def show_state(self, st: dict | None) -> None:
        if st is None:
            self.state_lbl.setText("OFFLINE")
            self.state_lbl.setObjectName("stateStopped")
            return
        code = st.get("state", 0)
        name = STATE_NAMES.get(code, f"CODE {code}")
        if code in (1, 2):
            name += " · назад" if st.get("status_bits", 0) & 2 else " · вперёд"
        fault = st.get("fault_code", 0)
        if fault:
            name = f"FAULT Err{fault:02d}"
            self.state_lbl.setObjectName("stateFault")
        elif code in (1, 2, 3):
            self.state_lbl.setObjectName("stateRun")
        else:
            self.state_lbl.setObjectName("stateStopped")
        self.state_lbl.setText(name)
        self.fault_lbl.setText("none" if not fault else f"Err{fault:02d} (raw {fault})")
        warn = st.get("warning_code", 0)
        self.warn_lbl.setText("none" if not warn else f"Warn{warn:02d} (raw {warn})")
        self.bits_lbl.setText(f"0x{st.get('status_bits', 0):04X}")
        self.freq_lbl.setText(f"{st.get('output_hz', 0.0):.2f}")
        self.gauge.set_value(st.get("output_hz", 0.0))
        from datetime import datetime
        self.ts_lbl.setText(datetime.now().strftime("%H:%M:%S"))
        # re-polish objectName styling
        for w in (self.state_lbl,):
            w.style().unpolish(w)
            w.style().polish(w)


class _FreqGauge(QWidget):
    """Slim horizontal bar 0..60 Hz with an accent gradient."""

    def __init__(self, parent=None, full_scale: float = 60.0) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._full = full_scale

    def set_value(self, hz: float) -> None:
        self._value = max(0.0, float(hz))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor("#30363d")))
        p.setBrush(QColor(PANEL))
        p.drawRoundedRect(rect, 6, 6)
        frac = min(1.0, self._value / self._full)
        if frac > 0:
            grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
            grad.setColorAt(0.0, QColor(ACCENT))
            grad.setColorAt(1.0, QColor("#3fb950"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            inner = rect.adjusted(2, 2, -2, -2)
            inner.setWidth(int(inner.width() * frac))
            p.drawRoundedRect(inner, 4, 4)
        p.setPen(QColor(MUTED))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                   f"{self._value:.1f} / {self._full:.0f} Hz")


class RegisterInspector(QWidget):
    """Table of known registers with live raw/engineering values + manual read."""

    readRequested = Signal(int, int)      # address, count

    def __init__(self, register_map: RegisterMap, parent=None) -> None:
        super().__init__(parent)
        self.map = register_map
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.addr_edit = QLineEdit("0x3000")
        self.count_spin = QSpinBox(minimum=1, maximum=8, value=1)
        btn_read = QPushButton("Read")
        btn_read.clicked.connect(self._read_clicked)
        top.addWidget(QLabel("Address:"))
        top.addWidget(self.addr_edit)
        top.addWidget(QLabel("Count:"))
        top.addWidget(self.count_spin)
        top.addWidget(btn_read)
        lay.addLayout(top)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Addr", "Name", "Access", "Raw", "Engineering", "Conf."])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.table)
        self.reload_rows()

    def reload_rows(self) -> None:
        rows = [self.map.get(a) for a in self.map.addresses()]
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [f"{r.address:#06x}", r.name, r.access, "", "", r.confidence]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if j == 2 and r.access.startswith("RW"):
                    item.setForeground(QColor("#3fb950"))
                self.table.setItem(i, j, item)

    def update_values(self, raw_by_addr: dict[int, tuple[int, str]]) -> None:
        for i in range(self.table.rowCount()):
            addr_txt = self.table.item(i, 0).text()
            addr = int(addr_txt, 16)
            if addr in raw_by_addr:
                raw, eng = raw_by_addr[addr]
                self.table.item(i, 3).setText(str(raw))
                self.table.item(i, 4).setText(eng)

    def _read_clicked(self) -> None:
        try:
            addr = int(self.addr_edit.text(), 0)
        except ValueError:
            return
        self.readRequested.emit(addr, self.count_spin.value())


class EventLog(QGroupBox):
    """Append-only journal of operations and errors."""

    def __init__(self, parent=None) -> None:
        super().__init__("Event log", parent)
        lay = QVBoxLayout()
        lay.setContentsMargins(8, 4, 8, 8)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(500)
        self.view.setFont(QFont("Consolas", 10))
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.view.clear)
        lay.addWidget(self.view)
        lay.addWidget(btn_clear)
        self.setLayout(lay)

    def append(self, line: str) -> None:
        from datetime import datetime
        self.view.appendPlainText(f"[{datetime.now():%H:%M:%S}] {line}")
