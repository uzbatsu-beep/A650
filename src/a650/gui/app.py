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
from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)
from PySide6.QtCore import QTimer

from .. import __version__
from ..a650lib.register_map import RegisterMap
from .controller import DriveController
from .catalog import CatalogView
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
        self.setWindowTitle(f"Конфигуратор ONI A650 · {__version__} — прототип")
        self.resize(1180, 850)
        self.ctrl = controller or DriveController(self)
        self.map = _load_map()
        self._last_poll_errors = {}
        self._scan_count = 0
        self._scan_ok = 0
        self._scan_disconnect = False

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
        scan_panel = QGroupBox("Диагностика карты регистров · только чтение")
        scan_layout = QVBoxLayout(scan_panel)
        scan_buttons = QHBoxLayout()
        self.scan_start = QPushButton("Сканировать каталог…")
        self.scan_resume = QPushButton("Продолжить скан…")
        self.scan_stop = QPushButton("Остановить")
        self.scan_start.setEnabled(False)
        self.scan_resume.setEnabled(False)
        self.scan_stop.setEnabled(False)
        for button in (self.scan_start, self.scan_resume, self.scan_stop):
            scan_buttons.addWidget(button)
        scan_layout.addLayout(scan_buttons)
        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 100)
        self.scan_progress.setValue(0)
        self.scan_status = QLabel("FC03 / Count=1 · JSONL + CSV · без записи в ПЧ")
        scan_layout.addWidget(self.scan_progress)
        scan_layout.addWidget(self.scan_status)
        right.addWidget(scan_panel)
        right.addWidget(self.inspector, stretch=1)
        right.addWidget(self.log, stretch=1)

        splitter_row = QHBoxLayout()
        left_wrap = QVBoxLayout()
        left_wrap.addLayout(left)
        left_widget = QWidget()
        left_widget.setLayout(left_wrap)
        left_widget.setMaximumWidth(460)
        right_widget = QWidget()
        right_widget.setLayout(right)
        splitter_row.addWidget(left_widget)
        splitter_row.addWidget(right_widget, stretch=1)
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.addLayout(splitter_row)
        self.tabs = QTabWidget()
        self.tabs.addTab(central, "Подключение и мониторинг")
        self.catalog = CatalogView()
        self.tabs.addTab(self.catalog, "Каталог параметров")
        self.catalog.editable_only.setChecked(True)
        self.tabs.setCurrentWidget(self.catalog)
        self.setCentralWidget(self.tabs)

        bar = self.statusBar()
        self.lbl_bus = QLabel("Нет подключения")
        bar.addPermanentWidget(self.lbl_bus)

        # -- wiring -----------------------------------------------------------
        self.conn_panel.connectRequested.connect(self._on_connect)
        self.conn_panel.disconnectRequested.connect(self._on_disconnect)
        self.ctrl.connected.connect(self._on_connected)
        self.ctrl.connectionFailed.connect(self._on_connection_failed)
        self.ctrl.disconnected.connect(self._on_disconnected)
        self.ctrl.error.connect(lambda m: self.log.append(f"ERROR {m}"))

        self.control.startRequested.connect(self._on_start)
        self.control.stopRequested.connect(self._on_stop)
        self.control.setFreqRequested.connect(self._on_setfreq)
        self.inspector.readRequested.connect(self._on_read)
        self.catalog.readRequested.connect(self._read_catalog)
        self.scan_start.clicked.connect(lambda: self._start_scan(False))
        self.scan_resume.clicked.connect(lambda: self._start_scan(True))
        self.scan_stop.clicked.connect(self.ctrl.stop_scan)
        self.ctrl.scanProgress.connect(self._on_scan_row)

    # -- connection --------------------------------------------------------------

    def _on_connect(self, kwargs: dict) -> None:
        self.lbl_bus.setText("Проверка связи…")
        self.ctrl.connect_drive(**kwargs)

    def _on_connection_failed(self, message: str) -> None:
        self.conn_panel.connection_failed(message)
        self.lbl_bus.setText("Нет подключения")

    def _read_catalog(self, codes, token):
        self.ctrl.read_simulated_parameters(codes,
            lambda values: self.catalog.receive_values(token, values),
            lambda message: self.catalog.read_failed(token, message), model=self.catalog.model.currentText())

    def _on_connected(self, desc: str) -> None:
        self.catalog.set_connection(self.ctrl.simulate)
        self.conn_panel.set_connected(True)
        self.lbl_bus.setText(desc)
        self.log.append(f"Подключено: {desc}"
                       + (" [запись разрешена]" if self.ctrl.allow_write else " [только чтение]"))
        self.control.set_enabled(self.ctrl.allow_write)
        self._scan_disconnect = False
        self.scan_start.setEnabled(not self.ctrl.allow_write)
        self.scan_resume.setEnabled(not self.ctrl.allow_write)
        # live polling: status block + output frequency every 500 ms
        self.ctrl.start_poll("status", 500, self._poll_status, self._show_status)

    def _poll_status(self):
        """Read each register independently: a rejected block must not blank status."""
        client = self.ctrl.client
        st, errors = {}, {}
        for name, address in (("state", 0x2100), ("status_bits", 0x2101),
                              ("fault_code", 0x2102), ("warning_code", 0x2103)):
            try:
                st[name] = client.read_registers(address, 1)[0]
            except Exception as exc:
                st[name] = None
                errors[name] = str(exc)
        try:
            st["output_hz"] = float(client.output_frequency_hz())
        except Exception as exc:
            st["output_hz"] = None
            errors["output_hz"] = str(exc)
        st["errors"] = errors
        return st

    def _show_status(self, st: dict) -> None:
        self.status_card.show_state(st)
        errors = st.get("errors", {})
        if errors != self._last_poll_errors:
            for name, message in errors.items():
                if self._last_poll_errors.get(name) != message:
                    self.log.append(f"READ {name}: {message}")
            for name in set(self._last_poll_errors) - set(errors):
                self.log.append(f"READ {name}: восстановлено")
            self._last_poll_errors = errors.copy()
        rows = {}
        for address, name in ((0x2100, "state"), (0x2101, "status_bits"),
                              (0x2102, "fault_code"), (0x2103, "warning_code")):
            value = st.get(name)
            if value is not None:
                rows[address] = (value, f"0x{value:04X}" if address == 0x2101 else str(value))
        if st.get("output_hz") is not None:
            hz = st["output_hz"]
            rows[0x3000] = (int(round(hz * 100)), f"{hz:.2f} Hz")
        self.inspector.update_values(rows)

    def _on_disconnect(self) -> None:
        self._scan_disconnect = True
        self.ctrl.disconnect_drive()

    def _on_disconnected(self) -> None:
        self.catalog.set_connection(False)
        self.conn_panel.set_connected(False)
        self.control.set_enabled(False)
        self.scan_start.setEnabled(False)
        self.scan_resume.setEnabled(False)
        self.scan_stop.setEnabled(False)
        self.status_card.show_state(None)
        self.lbl_bus.setText("Нет подключения")
        self.log.append("Отключено")

    # -- bench discovery ---------------------------------------------------------------

    def _start_scan(self, resume: bool) -> None:
        if not self.ctrl.is_connected or self.ctrl.scanning or self.ctrl.allow_write:
            return
        model = self.catalog.model.currentText()
        from ..diagnostics import read_targets
        count = len(read_targets(model))
        title = "Продолжить диагностику" if resume else "Сохранить отчёт диагностики"
        if resume:
            path, _ = QFileDialog.getOpenFileName(self, title, "", "JSONL (*.jsonl)")
        else:
            filename = f"a650-{model.lower()}-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
            path, _ = QFileDialog.getSaveFileName(self, title, filename, "JSONL (*.jsonl)")
        if not path:
            return
        if not path.lower().endswith(".jsonl"):
            path += ".jsonl"
        if not resume:
            answer = QMessageBox.question(
                self, "Подтверждение безопасного сканирования",
                f"Модель: {model}. План: {count} одиночных чтений FC03.\n"
                "Обычный мониторинг будет приостановлен.\n"
                "Запись и команды управления ПЧ не выполняются.\n"
                "На время проверки оставьте ПЧ в безопасном состоянии. Начать?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.ctrl.stop_poll("status")
        self._scan_disconnect = False
        self._scan_count = 0
        self._scan_ok = 0
        self.scan_progress.setRange(0, count)
        self.scan_progress.setValue(0)
        self.scan_start.setEnabled(False)
        self.scan_resume.setEnabled(False)
        self.scan_stop.setEnabled(True)
        self.inspector.setEnabled(False)
        self.scan_status.setText(f"Диагностика {model}: 0 / {count} · FC03 x1")
        try:
            self.ctrl.start_scan(model, path, resume=resume,
                                 on_done=self._scan_finished, on_error=self._scan_failed)
        except Exception as exc:
            self._scan_failed(str(exc))

    def _on_scan_row(self, row: dict) -> None:
        self._scan_count += 1
        if row.get("quality") == "ok":
            self._scan_ok += 1
        self.scan_progress.setValue(self._scan_count)
        self.scan_status.setText(
            f'Проверено новых: {self._scan_count}, успешно: {self._scan_ok}, '
            f'последний: {row["address"]} ({row["quality"]})')

    def _restore_after_scan(self) -> None:
        self.scan_stop.setEnabled(False)
        self.inspector.setEnabled(True)
        allowed = self.ctrl.is_connected and not self.ctrl.allow_write and not self._scan_disconnect
        self.scan_start.setEnabled(allowed)
        self.scan_resume.setEnabled(allowed)
        if self.ctrl.is_connected and not self._scan_disconnect:
            self.ctrl.start_poll("status", 500, self._poll_status, self._show_status)

    def _scan_finished(self, report: dict) -> None:
        self.scan_progress.setValue(report["scanned"])
        state = "Завершено" if report["completed"] else "Остановлено"
        self.scan_status.setText(f'{state}: {report["scanned"]}/{report["total"]} · {report["jsonl"]}')
        self.log.append(f'{state}: сканирование {report["scanned"]}/{report["total"]}; '
                        f'JSONL {report["jsonl"]}; CSV {report["csv"]}')
        self._restore_after_scan()

    def _scan_failed(self, message: str) -> None:
        self.scan_status.setText("Ошибка диагностики: " + message)
        self.log.append("SCAN ERROR: " + message)
        self._restore_after_scan()

    # -- safety gate -----------------------------------------------------------------

    def _confirm_write(self, what: str) -> bool:
        """Simulated drive needs no dialog; real hardware always asks."""
        if self.ctrl.simulate:
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
        if self.catalog.unsaved:
            models = ', '.join(sorted(self.catalog.unsaved))
            answer = QMessageBox.question(
                self, 'Несохранённые изменения',
                f'Есть несохранённые изменения проекта: {models}. Закрыть без сохранения?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.ctrl.shutdown()
        super().closeEvent(event)


def run_gui(argv: list[str] | None = None, start_simulated: bool = False,
            auto_quit_ms: int = 0) -> int:
    app = QApplication.instance()
    if app is None:
        # PySide6 rejects argv=None here; always pass a real list.
        app = QApplication(list(sys.argv) if argv is None else list(argv))
    app.setStyleSheet(style_app())
    app.setApplicationName("ONI A650 Configurator")
    app.setApplicationVersion(__version__)
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
