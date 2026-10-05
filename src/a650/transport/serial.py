"""pyserial-based transport for real RS-485 hardware.

Modbus RTU framing note: inter-frame gap is 3.5 chars; at 9600 8-N-1 that is
~4 ms. We read until expected_len bytes or silence > 50 ms (t3.5 fallback),
whichever comes first.
"""
from __future__ import annotations

import time


class SerialTransport:
    def __init__(self, port: str, baudrate: int = 9600, parity: str = "N",
                 bytesize: int = 8, stopbits: int = 1) -> None:
        try:
            import serial  # noqa: PLC0415  (optional dependency)
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "pyserial is required for real hardware access: "
                "pip install 'a650[serial]'"
            ) from exc
        self._serial_mod = serial
        parity_const = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN,
                        "O": serial.PARITY_ODD}[parity.upper()]
        self._ser = serial.Serial(
            port=port, baudrate=baudrate, bytesize=bytesize,
            parity=parity_const, stopbits=stopbits,
            timeout=0.05, write_timeout=2.0,
        )

    def open(self) -> None:
        if not self._ser.is_open:
            self._ser.open()

    def close(self) -> None:
        self._ser.close()

    def exchange(self, request: bytes, expected_len: int, timeout_s: float) -> bytes:
        self._ser.reset_input_buffer()
        self._ser.write(request)
        self._ser.flush()
        deadline = time.monotonic() + timeout_s
        buf = bytearray()
        while time.monotonic() < deadline:
            chunk = self._ser.read(expected_len - len(buf))
            if chunk:
                buf += chunk
                if len(buf) >= expected_len:
                    break
            elif len(buf) > 0:
                # silence after partial reply -> frame ended early
                break
        if not buf:
            raise TimeoutError(f"no response within {timeout_s:.2f}s")
        return bytes(buf)
