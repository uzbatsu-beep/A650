"""Transport abstraction: how raw bytes reach the RS-485 bus.

Keeping this as a Protocol lets the CLI run against:
  * a real serial port (SerialTransport, needs pyserial),
  * a fake in-memory bus (FakeTransport, used in tests and --simulate mode).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    def open(self) -> None: ...

    def close(self) -> None: ...

    def exchange(self, request: bytes, expected_len: int, timeout_s: float) -> bytes:
        """Send *request*, return response of up to *expected_len* bytes.

        Implementations must strip nothing — CRC is validated by the RTU layer.
        Raise TimeoutError if no complete reply arrives within timeout_s.
        """
        ...
