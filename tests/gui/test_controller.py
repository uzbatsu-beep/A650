"""Headless GUI tests (Qt offscreen platform).

Cover: controller threading round-trips, polling lifecycle, error surfacing.
Widget-level wiring is exercised in test_window.py.
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from a650.gui.controller import DriveController  # noqa: E402


def wait_until(cond, timeout_ms=4000):
    """Spin the Qt event loop until cond() becomes true."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if cond():
            return
        QApplication.processEvents()
        time.sleep(0.005)
    raise AssertionError("condition not met in time")


def pump(ms):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.005)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def ctrl(qapp):
    c = DriveController()
    yield c
    c.shutdown()


def make_status_fn(c):
    def get():
        st = c.client.status()
        st["output_hz"] = float(c.client.output_frequency_hz())
        return st
    return get


def test_connect_simulated_emits_connected(ctrl):
    got = []
    ctrl.connected.connect(got.append)
    ctrl.connect_drive(simulate=True, allow_write=True)
    wait_until(lambda: bool(got))
    assert got[0] == "SIMULATED drive"
    assert ctrl.is_connected


def test_start_stop_setfreq_roundtrip(ctrl, tmp_path):
    ctrl.audit_path = tmp_path / "audit.jsonl"
    done, errs = [], []
    ctrl.error.connect(errs.append)
    ctrl.connect_drive(simulate=True, allow_write=True)
    wait_until(lambda: ctrl.is_connected)
    ctrl.set_frequency(30.0, lambda raw: done.append(("freq", raw)),
                       lambda m: errs.append(m))
    ctrl.start_forward(lambda r: done.append(("start", r)),
                       lambda m: errs.append(m))
    ctrl.status(lambda st: done.append(("status", st)),
                lambda m: errs.append(m))
    ctrl.stop(lambda r: done.append(("stop", r)), lambda m: errs.append(m))
    wait_until(lambda: len(done) >= 4)
    kinds = [d[0] for d in done]
    assert kinds == ["freq", "start", "status", "stop"]
    assert next(d[1] for d in done if d[0] == "freq") == 3000
    st = next(d[1] for d in done if d[0] == "status")
    assert st["state"] == 1 and st["output_hz"] == pytest.approx(30.0)
    assert not errs
    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert '"write"' in text and "8193" in text  # 0x2001 == 8193


def test_write_denied_without_allow_write(ctrl):
    results, errors = [], []
    ctrl.connect_drive(simulate=True, allow_write=False)
    wait_until(lambda: ctrl.is_connected)
    ctrl.start_forward(lambda r: results.append(r), lambda m: errors.append(m))
    wait_until(lambda: bool(errors))
    assert not results
    assert any("read-only" in e.lower() or "denied" in e.lower() for e in errors)


def test_read_returns_raw_values(ctrl):
    vals, errs = [], []
    # dedicated session: the shared "gui" bank is stateful across tests
    ctrl.connect_drive(simulate=True, session="read-test")
    wait_until(lambda: ctrl.is_connected)
    ctrl.read(0x3000, 1, lambda v: vals.append(v), lambda m: errs.append(m))
    wait_until(lambda: bool(vals))
    assert vals[0] == (0,)  # stopped -> output 0.00 Hz
    assert not errs


def test_status_poll_updates_and_stops(ctrl):
    seen = []
    ctrl.connect_drive(simulate=True, allow_write=True)
    wait_until(lambda: ctrl.is_connected)
    ctrl.start_poll("status", 30, make_status_fn(ctrl), seen.append)
    wait_until(lambda: len(seen) >= 2)
    ctrl.stop_poll("status")
    n = len(seen)
    pump(250)
    assert len(seen) == n


def test_disconnect_emits(ctrl):
    gone = []
    ctrl.disconnected.connect(lambda: gone.append(True))
    ctrl.connect_drive(simulate=True)
    wait_until(lambda: ctrl.is_connected)
    ctrl.disconnect_drive()
    wait_until(lambda: bool(gone))
    assert not ctrl.is_connected


def test_connect_error_on_bad_port(ctrl):
    errs = []
    ctrl.error.connect(errs.append)
    ctrl.connect_drive(simulate=False, port="/dev/ttyDOES_NOT_EXIST_9")
    wait_until(lambda: bool(errs))
    assert any("connect failed" in e for e in errs)
    assert not ctrl.is_connected
