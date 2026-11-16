"""GUI scan and partial status regression tests, Qt offscreen / no hardware."""
import os
import time
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from a650.gui.app import MainWindow
from a650.gui.controller import DriveController


def spin_until(condition, timeout_s=4.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return
        time.sleep(0.01)
    pytest.fail("asynchronous diagnostic did not finish")


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_monitor_keeps_good_registers_when_one_fails(qapp):
    window = MainWindow()
    original = window.ctrl.client

    class Partial:
        def read_registers(self, address, count):
            assert count == 1
            if address == 0x2100:
                raise RuntimeError("Modbus exception 0x03")
            return (({0x2101: 4, 0x2102: 0, 0x2103: 0})[address],)

        def output_frequency_hz(self):
            return Decimal("12.34")

    try:
        window.ctrl.client = Partial()
        # Each register is independent; one failed state must not hide frequency.
        st = window._poll_status()
        assert st["state"] is None
        assert st["status_bits"] == 4
        assert st["output_hz"] == 12.34
        window._show_status(st)
        assert window.status_card.state_lbl.text() == "НЕИЗВЕСТНО"
        assert window.status_card.freq_lbl.text() == "12.34"
        assert window.status_card.bits_lbl.text() == "0x0004"
        assert window.status_card.fault_lbl.text() == "none"
    finally:
        window.ctrl.client = original
        window.close()


def test_controller_scanner_runs_in_worker_and_reports_progress(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("a650.diagnostics.read_targets",
                        lambda model: [("state", 0x2100), ("bits", 0x2101)])
    ctrl = DriveController()
    output = tmp_path / "simulator.jsonl"
    connected, reports, progress, errors = [], [], [], []
    try:
        ctrl.connected.connect(connected.append)
        ctrl.scanProgress.connect(progress.append)
        ctrl.connect_drive(simulate=True, allow_write=False, session="bench-scan-test")
        spin_until(lambda: bool(connected))
        assert ctrl.is_connected
        ctrl.start_scan("A650", output, on_done=reports.append, on_error=errors.append)
        spin_until(lambda: bool(reports) or bool(errors))
        assert not errors
        assert reports[0]["completed"] and reports[0]["scanned"] == 2
        assert len(progress) == 2
        assert output.exists() and output.with_suffix(".csv").exists()
        assert not ctrl.scanning
        assert all(entry["function"] == 3 and entry["count"] == 1 for entry in progress)
    finally:
        ctrl.shutdown()
