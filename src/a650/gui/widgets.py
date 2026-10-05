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

ACCENT = "#2f81f7"          # GitHub-dark blue
BG = "#1c2128"
PANEL = "#22272e"
FG = "#e6edf3"
MUTED = "#8b949e"

STATE_NAMES = {0: "STOPPED", 1: "RUN FWD", 2: "RUN REV"}


def style_app() -> str:
    """Dark modern stylesheet applied to the whole QApplication."""
    return f"""
    QWidget {{ background: {BG}; color: {FG}; font-size: 14px; }}
    QGroupBox {{ border: 1px solid #30363d; border-radius: 8px; margin-top: 14px;
                 padding: 10px; font-weight: 600; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px;
                        color: {MUTED}; }}
    QPushButton {{ background: {PANEL}; border: 1px solid #30363d; border-radius: 6px;
                   padding: 8px 14px; font-weight: 600; }}
    QPushButton:hover {{ border-color: {ACCENT}; }}
    QPushButton:disabled {{ color: {MUTED}; }}
    QPushButton#primary {{ background: {ACCENT}; color: white; border: none; }}
    QPushButton#primary:hover {{ background: #4a8ff8; }}
    QPushButton#danger {{ background: #da3633; color: white; border: none; }}
    QPushButton#danger:hover {{ background: #e5534b; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {PANEL}; border: 1px solid #30363d; border-radius: 6px;
        padding: 6px 8px; selection-background-color: {ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid #30363d;
        selection-background-color: {ACCENT}; }}
    QPlainTextEdit, QListWidget, QTableWidget {{ background: {PANEL};
        border: 1px solid #30363d; border-radius: 6px; }}
    QTableWidget::item {{ padding: 4px; }}
    QHeaderView::section {{ background: {BG}; color: {MUTED}; border: none;
        padding: 6px; font-weight: 600; }}
    QScrollBar:vertical {{ background: {BG}; width: 10px; }}
    QScrollBar::handle:vertical {{ background: #30363d; border-radius: 5px; min-height: 24px; }}
    QCheckBox {{ spacing: 8px; }}
    QStatusBar {{ background: {PANEL}; color: {MUTED}; }}
    QLabel#big {{ font-size: 34px; font-weight: 700; }}
    QLabel#unit {{ color: {MUTED}; font-size: 15px; }}
    QLabel#stateStopped {{ color: {MUTED}; font-weight: 700; }}
    QLabel#stateRun {{ color: #3fb950; font-weight: 700; }}
    QLabel#stateFault {{ color: #e5534b; font-weight: 700; }}
    """


class ConnectionPanel(QGroupBox):
    """Port / simulate selector + connect button. Emits connectRequested."""

    connectRequested = Signal(dict)     # kwargs for DriveController.connect_drive
    disconnectRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Connection", parent)
        self._connected = False
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItems(["SIMULATED drive (no hardware)", "Serial port (RS-485)"])
        self.port = QComboBox()
        self.port.setEditable(True)
        self.refresh_ports()
        self.baud = QComboBox()
        self.baud.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.baud.setCurrentText("9600")
        self.slave = QSpinBox(minimum=1, maximum=247, value=1)
        self.allow_write = QCheckBox("Enable writes (whitelist 0x2000/0x2001)")
        self.allow_write.setToolTip(
            "Mirrors CLI --allow-write. Writes still go through SafetyGuard "
            "and are recorded in ~/.a650/audit.jsonl")
        row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh ports")
        self.btn_refresh.clicked.connect(self.refresh_ports)
        row.addWidget(self.btn_refresh)
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setObjectName("primary")
        self.btn_connect.clicked.connect(self._on_connect)
        row.addWidget(self.btn_connect)
        form.addRow("Mode:", self.mode)
        form.addRow("Port:", self.port)
        form.addRow("Baud:", self.baud)
        form.addRow("Slave:", self.slave)
        form.addRow("", self.allow_write)
        form.addRow(row)
        self.setLayout(form)
        self.mode.currentIndexChanged.connect(self._update_enabled)
        self._update_enabled()

    def refresh_ports(self) -> None:
        from .controller import list_serial_ports
        current = self.port.currentText()
        self.port.clear()
        ports = list_serial_ports()
        self.port.addItems(ports or ["(none found — type COM/tty manually)"])
        if current:
            self.port.setCurrentText(current)

    def _update_enabled(self) -> None:
        serial_mode = self.mode.currentIndex() == 1
        for w in (self.port, self.baud, self.btn_refresh):
            w.setEnabled(serial_mode and not self._connected)
        self.mode.setEnabled(not self._connected)
        self.slave.setEnabled(not self._connected)
        self.allow_write.setEnabled(not self._connected)

    def _on_connect(self) -> None:
        if self._connected:
            self.disconnectRequested.emit()
            return
        self.connectRequested.emit({
            "simulate": self.mode.currentIndex() == 0,
            "port": self.port.currentText(),
            "baud": int(self.baud.currentText()),
            "slave": self.slave.value(),
            "allow_write": self.allow_write.isChecked(),
        })

    def set_connected(self, on: bool, desc: str = "") -> None:
        self._connected = on
        self.btn_connect.setText("Disconnect" if on else "Connect")
        self.btn_connect.setObjectName("" if on else "primary")
        self.allow_write.setEnabled(not on)
        self._update_enabled()
        if on:
            self.allow_write.setChecked(self.allow_write.isChecked())

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
        fault = st.get("fault_code", 0)
        if fault:
            name = f"FAULT Err{fault:02d}"
            self.state_lbl.setObjectName("stateFault")
        elif code in (1, 2):
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
        self.count_spin = QSpinBox(minimum=1, maximum=16, value=1)
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
