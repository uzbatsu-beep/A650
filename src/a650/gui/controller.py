"""Thread-safe bridge between the Qt GUI and the A650 Modbus client.

Design: one QThread owns the transport + A650Client. The GUI posts jobs to it
via _post(); results come back as jobDone/jobError signals (auto-connect =
queued delivery on the GUI thread). Polling is a repeating job started/stopped
by id, driven by a QTimer that lives on the GUI thread but only *enqueues*
work. This module imports no QWidget classes, so it is testable headless.
"""
from __future__ import annotations

import itertools
import traceback
from queue import Empty, Queue
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from ..a650lib.register_map import RegisterMap
from ..a650lib.safety import SafetyGuard
from ..client import A650Client, DriveError
from ..cli import KNOWN_WRITABLE, default_audit_path


def list_serial_ports() -> list[str]:
    """Best-effort COM/tty enumeration; empty list if pyserial is absent."""
    try:
        from serial.tools import list_ports
    except Exception:
        return []
    return [p.device for p in list_ports.comports()]


def _friendly(exc: Exception) -> str:
    """Short human message for the log panel (no stack traces in the UI)."""
    if isinstance(exc, (DriveError, TimeoutError)):
        return f"drive error: {exc}"
    # pyserial raises SerialException with a very long, machine-oriented
    # message; trim it to the first sentence so "connect failed: ..." reads OK.
    name = type(exc).__name__
    text = str(exc) or name
    if name == "SerialException":
        text = text.split(": ", 1)[-1].split("\n")[0]
        return f"connect failed: {text[:120]}"
    return f"{name}: {text}"


class Job:
    def __init__(self, key: int, fn: Callable[[], object]) -> None:
        self.key = key
        self.fn = fn


class DriveController(QObject):
    """Owns connection lifecycle; marshals all Modbus calls to the worker."""

    connected = Signal(str)
    disconnected = Signal()
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: "Queue[Optional[Job]]" = Queue()
        self._keys = itertools.count(1)          # mutated on GUI thread only
        self._callbacks: dict[int, tuple] = {}   # mutated on GUI thread only
        self.client: A650Client | None = None
        self.allow_write = False
        self.audit_path = default_audit_path()
        self._timers: dict[str, QTimer] = {}
        self._polls: dict[str, tuple] = {}
        self._thread = QThread(self)
        self._thread.setObjectName("a650-bus")
        self._worker = _Worker(self._queue)
        self._worker.moveToThread(self._thread)
        self._worker.jobDone.connect(self._on_done)
        self._worker.jobError.connect(self._on_error)
        # the worker's event loop runs pump(): a blocking loop over the queue,
        # started via a queued call so it begins inside the thread context.
        self._thread.started.connect(self._worker.pump)
        self._thread.start()

    # -- lifecycle -------------------------------------------------------------

    def shutdown(self) -> None:
        for pid in list(self._timers):
            self.stop_poll(pid)
        if self.client is not None:
            try:
                self.client.transport.close()
            except Exception:
                pass
            self.client = None
        self._queue.put(None)      # poison pill ends the worker pump loop
        self._thread.quit()
        self._thread.wait(3000)

    @property
    def is_connected(self) -> bool:
        return self.client is not None

    # -- connect/disconnect ------------------------------------------------------

    def connect_drive(self, *, simulate: bool, port: str = "", slave: int = 1,
                      baud: int = 9600, parity: str = "N",
                      allow_write: bool = False, session: str = "gui") -> None:
        """Open the bus on the worker thread. Emits connected(desc)/error(msg)."""
        self.allow_write = allow_write
        desc = "SIMULATED drive" if simulate else f"{port} {baud}-{parity}-8-1 slave={slave}"

        def establish():
            if simulate:
                from ..transport.fake import FakeTransport
                transport = FakeTransport(slave=slave, session=session)
            else:
                from ..transport.serial import SerialTransport
                transport = SerialTransport(port=port, baudrate=baud, parity=parity)
            transport.open()
            guard = SafetyGuard()
            if allow_write:
                guard.enable_writes(set(KNOWN_WRITABLE))
            self.client = A650Client(transport=transport, slave=slave, guard=guard,
                                     register_map=RegisterMap.load(),
                                     audit_path=self.audit_path)
            return desc

        self._post(establish,
                   on_success=lambda d: self.connected.emit(d),
                   on_error=None)  # generic error signal fires anyway

    def disconnect_drive(self) -> None:
        for pid in list(self._timers):
            self.stop_poll(pid)

        def close_transport():
            if self.client is not None:
                try:
                    self.client.transport.close()
                finally:
                    self.client = None
            return True
        self._post(close_transport, on_success=lambda _: self.disconnected.emit())

    # -- generic call ------------------------------------------------------------

    def _post(self, fn: Callable[[], object],
              on_success: Optional[Callable[[object], None]] = None,
              on_error: Optional[Callable[[str], None]] = None) -> None:
        key = next(self._keys)
        self._callbacks[key] = (on_success, on_error)
        self._queue.put(Job(key, fn))

    # -- polling -------------------------------------------------------------------

    def start_poll(self, poll_id: str, interval_ms: int, fn: Callable[[], object],
                   callback: Callable[[object], None]) -> None:
        if poll_id in self._timers:
            return
        self._polls[poll_id] = (fn, callback)
        t = QTimer(self)
        t.setInterval(interval_ms)
        t.timeout.connect(lambda pid=poll_id: self._fire_poll(pid))
        t.start()
        self._timers[poll_id] = t

    def stop_poll(self, poll_id: str) -> None:
        self._polls.pop(poll_id, None)
        t = self._timers.pop(poll_id, None)
        if t is not None:
            t.stop()

    def _fire_poll(self, poll_id: str) -> None:
        entry = self._polls.get(poll_id)
        if entry is None or not self.is_connected:
            return
        fn, callback = entry
        self._post(fn, on_success=callback)

    # -- high-level verbs --------------------------------------------------------------

    def read(self, address: int, count: int, cb: Callable[[tuple], None],
             ecb: Optional[Callable[[str], None]] = None) -> None:
        self._post(lambda: self.client.read_registers(address, count), cb, ecb)

    def status(self, cb: Callable[[dict], None],
               ecb: Optional[Callable[[str], None]] = None) -> None:
        def get():
            st = self.client.status()
            st["output_hz"] = float(self.client.output_frequency_hz())
            return st
        self._post(get, cb, ecb)

    def set_frequency(self, hz: float, cb: Callable[[int], None],
                      ecb: Callable[[str], None]) -> None:
        self._post(lambda: self.client.write_engineering(0x2001, hz), cb, ecb)

    def start_forward(self, cb: Callable[[object], None], ecb: Callable[[str], None]) -> None:
        self._post(lambda: self.client.write_register(0x2000, 0x0001), cb, ecb)

    def stop(self, cb: Callable[[object], None], ecb: Callable[[str], None]) -> None:
        self._post(lambda: self.client.write_register(0x2000, 0x0005), cb, ecb)

    def write_raw(self, address: int, value: int, cb: Callable[[object], None],
                  ecb: Callable[[str], None]) -> None:
        self._post(lambda: self.client.write_register(address, value), cb, ecb)

    # -- signal plumbing (runs on the GUI thread via queued connections) ------------------

    def _on_done(self, key: int, result: object) -> None:
        ok, _err = self._callbacks.pop(key, (None, None))
        if ok:
            ok(result)

    def _on_error(self, key: int, message: str) -> None:
        _ok, err = self._callbacks.pop(key, (None, None))
        self.error.emit(message)
        if err:
            err(message)


class _Worker(QObject):
    """Executes queued Jobs sequentially inside the worker thread."""

    jobDone = Signal(int, object)
    jobError = Signal(int, str)

    def __init__(self, queue: "Queue[Optional[Job]]", parent=None) -> None:
        super().__init__(parent)
        self._queue = queue

    def pump(self) -> None:
        """Runs in the worker thread until the poison pill arrives."""
        while True:
            try:
                item = self._queue.get(timeout=0.05)
            except Empty:
                continue
            if item is None:               # poison pill: stop
                break
            try:
                result = item.fn()
            except Exception as exc:
                traceback.print_exc()
                self.jobError.emit(item.key, _friendly(exc))
                continue
            self.jobDone.emit(item.key, result)
