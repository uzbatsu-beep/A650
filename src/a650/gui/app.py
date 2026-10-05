"""Main window of the a650 configurator GUI.

Wires passive widgets (gui.widgets) to the thread-safe DriveController
(gui.controller). Safety model mirrors the CLI:
  * reads + 500 ms status polling are always available once connected;
  * control buttons are enabled only when writes were allowed at connect time;
  * every write asks for confirmation unless it's the simulated drive;
  * all events land in the on-screen journal, writes also go to the audit log.
"""
from __future__ import annotations

import sys
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QTimer

from ..a650lib.register_map import RegisterMap
from .controller import DriveController
from .widgets import (
    ConnectionPanel, ControlDeck, EventLog, RegisterInspector, StatusCard,
    style_app,
)


def _load_map() -> RegisterMap:
    try:
        return RegisterMap.load()
    except FileNotFoundError:
        return RegisterMap.empty()


class MainWindow(QMainWindow):
    def __init__(self, controller: DriveController | None = None) -> None:
        super().__init__()
        self.setWindowTitle("ONI A650 Configurator — prototype")
        self.resize(1000, 680)
        self.ctrl = controller or DriveController(self)
        self.map = _load_map()

        left = QVBoxLayout()
        self.conn_panel = ConnectionPanel()
        self.control = ControlDeck()
        self.control.set_enabled(False)
        left.addWidget(self.conn_panel)
        left.addWidget(self.control)
        left.addStretch()

        right = QVBoxLayout()
        self.status_card = StatusCard()
        self.inspector = RegisterInspector(self.map)
        self.log = EventLog()
        right.addWidget(self.status_card)
        right.addWidget(self.inspector, stretch=1)
        right.addWidget(self.log, stretch=1)

        splitter_row = QHBoxLayout()
        left_wrap = QVBoxLayout()
        left_wrap.addLayout(left)
        left_widget = QWidget()
        left_widget.setLayout(left_wrap)
        left_widget.setMaximumWidth(360)
        right_widget = QWidget()
        right_widget.setLayout(right)
        splitter_row.addWidget(left_widget)
        splitter_row.addWidget(right_widget, stretch=1)
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.addLayout(splitter_row)
        self.setCentralWidget(central)

        bar = self.statusBar()
        self.lbl_bus = QLabel("offline")
        bar.addPermanentWidget(self.lbl_bus)

        # -- wiring -----------------------------------------------------------
        self.conn_panel.connectRequested.connect(self._on_connect)
        self.conn_panel.disconnectRequested.connect(self._on_disconnect)
        self.ctrl.connected.connect(self._on_connected)
        self.ctrl.disconnected.connect(self._on_disconnected)
        self.ctrl.error.connect(lambda m: self.log.append(f"ERROR {m}"))

        self.control.startRequested.connect(self._on_start)
        self.control.stopRequested.connect(self._on_stop)
        self.control.setFreqRequested.connect(self._on_setfreq)
        self.inspector.readRequested.connect(self._on_read)

    # -- connection --------------------------------------------------------------

    def _on_connect(self, kwargs: dict) -> None:
        self.lbl_bus.setText("connecting…")
        self.ctrl.connect_drive(**kwargs)

    def _on_connected(self, desc: str) -> None:
        self.conn_panel.set_connected(True)
        self.lbl_bus.setText(desc)
        self.log.append(f"connected: {desc}"
                       + (" [writes ENABLED]" if self.ctrl.allow_write else " [read-only]"))
        self.control.set_enabled(self.ctrl.allow_write)
        # live polling: status block + output frequency every 500 ms
        self.ctrl.start_poll("status", 500, self._poll_status, self._show_status)

    def _poll_status(self):
        st = self.ctrl.client.status()
        st["output_hz"] = float(self.ctrl.client.output_frequency_hz())
        return st

    def _show_status(self, st: dict) -> None:
        self.status_card.show_state(st)
        eng = f"{st['output_hz']:.2f} Hz"
        rows = {
            0x2100: (st["state"], str(st["state"])),
            0x2101: (st["status_bits"], f"0x{st['status_bits']:04X}"),
            0x2102: (st["fault_code"],
                     "none" if not st["fault_code"] else f"Err{st['fault_code']:02d}"),
            0x2103: (st["warning_code"],
                     "none" if not st["warning_code"] else f"Warn{st['warning_code']:02d}"),
            0x3000: (int(round(st["output_hz"] * 100)), eng),
        }
        self.inspector.update_values(rows)

    def _on_disconnect(self) -> None:
        self.ctrl.disconnect_drive()

    def _on_disconnected(self) -> None:
        self.conn_panel.set_connected(False)
        self.control.set_enabled(False)
        self.status_card.show_state(None)
        self.lbl_bus.setText("offline")
        self.log.append("disconnected")

    # -- safety gate -----------------------------------------------------------------

    def _confirm_write(self, what: str) -> bool:
        """Simulated drive needs no dialog; real hardware always asks."""
        simulate = "SIMULATED" in self.lbl_bus.text()
        if simulate:
            return True
        resp = QMessageBox.question(
            self, "Write to drive",
            f"About to WRITE to the physical device:\n\n{what}\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return resp == QMessageBox.StandardButton.Yes

    # -- control verbs ------------------------------------------------------------------

    def _on_start(self) -> None:
        if not self._confirm_write("0x2000 ← 0x0001 (run forward)"):
            self.log.append("start aborted by user")
            return
        self.ctrl.start_forward(
            lambda _: self.log.append("wrote 0x2000 raw=1 (run forward)"),
            lambda m: self.log.append(f"start failed: {m}"))

    def _on_stop(self) -> None:
        if not self._confirm_write("0x2000 ← 0x0005 (stop)"):
            self.log.append("stop aborted by user")
            return
        self.ctrl.stop(
            lambda _: self.log.append("wrote 0x2000 raw=5 (stop)"),
            lambda m: self.log.append(f"stop failed: {m}"))

    def _on_setfreq(self, hz: float) -> None:
        raw = int(Decimal(str(hz)) / Decimal("0.01"))
        if not self._confirm_write(f"0x2001 ← {raw} ({hz:.2f} Hz setpoint)"):
            self.log.append("setfreq aborted by user")
            return
        self.ctrl.set_frequency(
            hz,
            lambda written: self.log.append(f"wrote 0x2001 raw={written} ({hz:.2f} Hz)"),
            lambda m: self.log.append(f"setfreq failed: {m}"))

    def _on_read(self, address: int, count: int) -> None:
        def ok(values: tuple) -> None:
            try:
                reg = self.map.get(address)
                text = ", ".join(f"{v} ({reg.to_engineering(v)} {reg.unit})" for v in values)
            except KeyError:
                text = ", ".join(str(v) for v in values)
            self.log.append(f"read {address:#06x} x{count}: {text}")
            rows = {}
            try:
                reg = self.map.get(address)
                rows[address] = (values[0], f"{reg.to_engineering(values[0])} {reg.unit}")
            except KeyError:
                pass
            if rows:
                self.inspector.update_values(rows)
        self.ctrl.read(address, count, ok)

    # -- teardown -------------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        self.ctrl.shutdown()
        super().closeEvent(event)


def run_gui(argv: list[str] | None = None, start_simulated: bool = False,
            auto_quit_ms: int = 0) -> int:
    app = QApplication.instance()
    if app is None:
        # PySide6 rejects argv=None here; always pass a real list.
        app = QApplication(list(sys.argv) if argv is None else list(argv))
    app.setStyleSheet(style_app())
    win = MainWindow()
    win.show()
    if start_simulated:
        # auto-connect to the built-in fake drive so the GUI is immediately usable
        QTimer.singleShot(100, lambda: win.ctrl.connect_drive(simulate=True,
                                                              allow_write=True))
    if auto_quit_ms > 0:
        # CI smoke test: verify the window + event loop come up, then exit cleanly
        QTimer.singleShot(auto_quit_ms, win.close)
    return app.exec()
