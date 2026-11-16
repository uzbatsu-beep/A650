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
from threading import Event
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
    connectionFailed = Signal(str)
    disconnected = Signal()
    error = Signal(str)
    scanProgress = Signal(object)  # each persisted JSONL record

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: "Queue[Optional[Job]]" = Queue()
        self._keys = itertools.count(1)          # mutated on GUI thread only
        self._callbacks: dict[int, tuple] = {}   # mutated on GUI thread only
        self.client: A650Client | None = None
        self.allow_write = False
        self.simulate = False
        self.connecting = False
        self._scan_stop: Event | None = None
        self._scan_running = False
        self._closing = False
        self._shutdown_wait_ms = 3000
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
        self._closing = True
        self.stop_scan()
        for pid in list(self._timers):
            self.stop_poll(pid)
        # Drop queued work; allow only the in-flight exchange to finish.
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                break
        if self.client is not None:
            try:
                self.client.transport.close()
            except Exception:
                pass
            self.client = None
        self._queue.put(None)      # poison pill ends the worker pump loop
        self._thread.quit()
        self._thread.wait(self._shutdown_wait_ms)

    @property
    def is_connected(self) -> bool:
        return self.client is not None

    # -- connect/disconnect ------------------------------------------------------

    def connect_drive(self, *, simulate: bool, port: str = "", slave: int = 1,
                      baud: int = 9600, parity: str = "N",
                      stopbits: int = 1, timeout_s: float = 0.5, retries: int = 2,
                      allow_write: bool = False, session: str = "gui") -> None:
        """Open the bus on the worker thread. Emits connected(desc)/error(msg)."""
        if self._closing or self.connecting or self.is_connected:
            return
        self.connecting = True
        desc = "Симулятор ПЧ" if simulate else f"{port.strip()} · {baud} · 8{parity}{stopbits} · адрес {slave}"

        def establish():
            if self._closing:
                return
            if not 1 <= slave <= 247 or not 0.1 <= timeout_s <= 10 or not 0 <= retries <= 3:
                raise ValueError("Проверьте адрес (1–247), тайм-аут (0,1–10 с) и повторы (0–3)")
            if not simulate and (not port.strip() or baud not in (4800, 9600, 19200, 38400, 57600, 115200)
                                 or (parity, stopbits) not in (("N", 1), ("N", 2), ("E", 1), ("O", 1))):
                raise ValueError("Проверьте порт, скорость и формат данных F15.01")
            self._shutdown_wait_ms = int(((timeout_s + 2.1) * (retries + 1) + 1) * 1000)
            if simulate:
                from ..transport.fake import FakeTransport
                transport = FakeTransport(slave=slave, session=session)
            else:
                from ..transport.serial import SerialTransport
                transport = SerialTransport(port=port.strip(), baudrate=baud, parity=parity,
                                            bytesize=8, stopbits=stopbits)
            guard = SafetyGuard()
            if allow_write:
                guard.enable_writes(set(KNOWN_WRITABLE))
            try:
                transport.open()
                client = A650Client(transport=transport, slave=slave, guard=guard,
                                    register_map=RegisterMap.load(), timeout_s=timeout_s,
                                    retries=retries, audit_path=self.audit_path)
                # Opening a COM port alone does not prove communication with the drive.
                client.read_registers(0x3000)
                if self._closing:
                    transport.close()
                    return
            except Exception:
                transport.close()
                raise
            self.client = client
            return desc

        def connected(desc):
            self.connecting = False
            if self._closing:
                return
            self.allow_write = allow_write
            self.simulate = simulate
            self.connected.emit(desc)

        def failed(message):
            self.connecting = False
            self.allow_write = False
            self.connectionFailed.emit(message)

        self._post(establish,
                   on_success=connected, on_error=failed)

    def disconnect_drive(self) -> None:
        self.stop_scan()
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

    # -- read-only diagnostic scan -------------------------------------------------

    @property
    def scanning(self) -> bool:
        return self._scan_running

    def start_scan(self, model: str, output, *, resume: bool = False,
                   on_done=None, on_error=None) -> None:
        """One queued worker job owns the bus for the entire scan.

        Caller MUST stop the status poll first. No writes are issued.
        """
        if self._closing or not self.is_connected or self._scan_running:
            raise RuntimeError("scan requires an idle, connected drive")
        if self.allow_write:
            raise RuntimeError("reconnect in read-only mode before scanning")
        from ..diagnostics import read_targets, run_scan
        targets = read_targets(model)
        client = self.client
        stop = Event()
        self._scan_stop = stop
        self._scan_running = True

        def worker():
            if self._closing or self.client is not client:
                raise RuntimeError("device connection changed")
            return run_scan(client, targets, output, model=model, stop_event=stop,
                            resume=resume, on_row=self.scanProgress.emit)

        def done(report):
            self._scan_running = False
            self._scan_stop = None
            if on_done is not None:
                on_done(report)

        def failed(message):
            self._scan_running = False
            self._scan_stop = None
            if on_error is not None:
                on_error(message)

        self._post(worker, on_success=done, on_error=failed)

    def stop_scan(self) -> None:
        """Cancellation takes effect between registers, not mid-frame."""
        if self._scan_stop is not None:
            self._scan_stop.set()

    # -- high-level verbs --------------------------------------------------------------

    def read(self, address: int, count: int, cb: Callable[[tuple], None],
             ecb: Optional[Callable[[str], None]] = None) -> None:
        self._post(lambda: self.client.read_registers(address, count), cb, ecb)

    def read_simulated_parameters(self, codes, cb, ecb, *, model="A650"):
        """Read the supported enum subset; never use guessed numeric scaling."""
        from ..a650lib.addresses import parameter_addresses
        from ..a650lib.editor_profile import load_editor_profile
        enums = load_editor_profile(model).enums
        client = self.client
        if client is None or not self.simulate:
            ecb('Чтение каталога пока доступно только в симуляторе')
            return
        codes = tuple(codes)
        if not codes or any(code not in enums for code in codes):
            ecb('В запросе есть параметры без проверенного кодека')
            return

        def read_values():
            if self._closing or self.client is not client or not self.simulate:
                raise RuntimeError('Соединение изменилось до начала чтения')
            return {code: client.read_registers(parameter_addresses(code)[0])[0]
                    for code in codes}

        self._post(read_values, cb, ecb)

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
