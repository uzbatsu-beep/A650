"""Connection UI through controller and pyserial boundary, without hardware."""
import time

import pytest
from PySide6.QtWidgets import QApplication

from a650.gui.app import MainWindow
from a650.gui.widgets import ConnectionPanel
from a650.modbus.rtu import build_read_response


def wait_until(condition):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return
        time.sleep(0.005)
    pytest.fail("connection did not complete")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, monkeypatch):
    monkeypatch.setattr("a650.gui.controller.list_serial_ports", lambda: [])
    widget = ConnectionPanel()
    yield widget
    widget.close()


def test_empty_port_is_not_a_fake_list_entry(panel):
    panel.mode.setCurrentIndex(1)
    calls = []
    panel.connectRequested.connect(calls.append)
    panel.btn_connect.click()
    assert panel.port.currentText() == ""
    assert not calls
    assert "Укажите COM-порт" in panel.message.text()


def test_refresh_preserves_manually_entered_port(panel):
    panel.port.setCurrentText("COM17")
    panel.refresh_ports()
    assert panel.port.currentText() == "COM17"


def test_invalid_parity_stopbits_does_not_connect(panel):
    panel.mode.setCurrentIndex(1)
    panel.port.setCurrentText("COM17")
    panel.parity.setCurrentIndex(1)
    panel.stopbits.setCurrentText("2")
    calls = []
    panel.connectRequested.connect(calls.append)
    panel.btn_connect.click()
    assert not calls
    assert "1 стоповый бит" in panel.message.text()


@pytest.mark.parametrize("parity,stopbits", [("N", 1), ("N", 2), ("E", 1), ("O", 1)])
def test_settings_reach_serial_and_client(qapp, monkeypatch, parity, stopbits):
    import serial
    opened = []

    class Port:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.is_open = False
            self.port = None
            self.requests = []
            opened.append(self)

        def open(self):
            self.is_open = True

        def close(self):
            self.is_open = False

        def reset_input_buffer(self):
            pass

        def write(self, data):
            self.requests.append(data)

        def flush(self):
            pass

        def read(self, size):
            return build_read_response(17, [0])

    monkeypatch.setattr(serial, "Serial", Port)
    win = MainWindow()
    try:
        panel = win.conn_panel
        panel.mode.setCurrentIndex(1)
        panel.port.setCurrentText("COM17")
        panel.baud.setCurrentText("4800")
        panel.parity.setCurrentIndex(panel.parity.findData(parity))
        panel.stopbits.setCurrentText(str(stopbits))
        panel.slave.setValue(17)
        panel.timeout.setValue(1.25)
        panel.retries.setValue(0)
        panel.btn_connect.click()
        assert not panel.btn_connect.isEnabled()
        panel.btn_connect.click()  # cannot enqueue another connection
        wait_until(lambda: panel._connected)
        assert len(opened) == 1
        port = opened[0]
        assert port.port == "COM17"
        assert port.options["baudrate"] == 4800
        assert port.options["bytesize"] == 8
        assert port.options["parity"] == parity
        assert port.options["stopbits"] == stopbits
        assert win.ctrl.client.timeout_s == 1.25
        assert win.ctrl.client.retries == 0
        assert win.ctrl.client.slave == 17
        assert port.requests[0][:6] == bytes.fromhex("110330000001")
        assert not win.ctrl.allow_write
        assert not panel.baud.isEnabled()
        panel.btn_connect.click()
        wait_until(lambda: not panel._connected)
        assert not port.is_open
        assert panel.baud.isEnabled()
    finally:
        win.close()


def test_failed_probe_closes_port_and_restores_ui(qapp, monkeypatch):
    from a650.transport import serial as serial_transport
    ports = []

    class NoAnswer:
        def __init__(self, **kwargs):
            self.closed = False
            ports.append(self)

        def open(self):
            pass

        def close(self):
            self.closed = True

        def exchange(self, *args):
            raise TimeoutError("нет ответа")

    monkeypatch.setattr(serial_transport, "SerialTransport", NoAnswer)
    win = MainWindow()
    try:
        panel = win.conn_panel
        panel.mode.setCurrentIndex(1)
        panel.port.setCurrentText("COM17")
        panel.retries.setValue(0)
        panel.btn_connect.click()
        wait_until(lambda: bool(panel.message.text()))
        assert not win.ctrl.is_connected
        assert ports[0].closed
        assert panel.btn_connect.isEnabled()
        assert panel.port.isEnabled()
        assert win.lbl_bus.text() == "Нет подключения"
    finally:
        win.close()
