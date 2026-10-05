"""High-level A650 client: transport + RTU framing + safety + audit log.

This is the layer the CLI (and future GUI) talks to. It knows nothing about
argparse or terminals — pure library API, safe to import from tests.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .a650lib.register_map import RegisterMap, RegisterDef
from .a650lib.safety import SafetyGuard
from .modbus.rtu import (
    ExceptionResponse,
    ReadRegistersResponse,
    ReadRegistersRequest,
    WriteRegisterRequest,
    parse_response,
    expected_response_len,
)


class Transport(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def exchange(self, request: bytes, expected_len: int, timeout_s: float) -> bytes: ...


class DriveError(RuntimeError):
    pass


class A650Client:
    def __init__(self, transport: Transport, slave: int = 1,
                 guard: SafetyGuard | None = None,
                 register_map: RegisterMap | None = None,
                 timeout_s: float = 0.5, retries: int = 2,
                 audit_path: Path | str | None = None) -> None:
        self.transport = transport
        self.slave = slave
        self.guard = guard or SafetyGuard()
        self.map = register_map or RegisterMap.load()
        self.timeout_s = timeout_s
        self.retries = retries
        self.audit_path = Path(audit_path) if audit_path else None

    # -- low level ----------------------------------------------------------

    def _request(self, frame: bytes) -> bytes:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self.transport.exchange(
                    frame, expected_response_len(frame), self.timeout_s
                )
                return resp
            except TimeoutError as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(0.05)
        raise DriveError(f"drive did not answer after {self.retries + 1} attempts: {last_exc}")

    def _parse(self, resp: bytes, request: bytes) -> ReadRegistersResponse | ExceptionResponse:
        parsed = parse_response(resp, expected_slave=self.slave)
        if isinstance(parsed, ExceptionResponse):
            raise DriveError(
                f"Modbus exception 0x{parsed.code:02X} ({parsed.name}) "
                f"for request {request.hex(' ').upper()}"
            )
        return parsed

    # -- public API ---------------------------------------------------------

    def read_registers(self, address: int, count: int = 1) -> tuple[int, ...]:
        req = ReadRegistersRequest(slave=self.slave, address=address, count=count)
        frame = req.to_bytes()
        parsed = self._parse(self._request(frame), frame)
        assert isinstance(parsed, ReadRegistersResponse)
        return parsed.values

    def read_engineering(self, address: int) -> tuple[int, object]:
        """Read one mapped register, return (raw, engineering Decimal)."""
        raw = self.read_registers(address)[0]
        reg: RegisterDef = self.map.get(address)
        return raw, reg.to_engineering(raw)

    def write_register(self, address: int, value: int) -> None:
        self.guard.check_write(self.slave, address, value)
        req = WriteRegisterRequest(slave=self.slave, address=address, value=value)
        frame = req.to_bytes()
        parsed = self._parse(self._request(frame), frame)
        echo_addr, echo_val = parsed.values  # type: ignore[misc]
        if (echo_addr, echo_val) != (address, value):
            raise DriveError(
                f"write echo mismatch: sent {address:#06x}={value}, echoed {echo_addr:#06x}={echo_val}"
            )
        self._audit("write", address=address, value=value)

    def write_engineering(self, address: int, engineering) -> int:
        reg = self.map.get(address)
        raw = reg.to_raw(engineering)
        self.write_register(address, raw)
        return raw

    # -- convenience verbs ---------------------------------------------------

    def start_forward(self) -> None:
        self.write_register(0x2000, 0x0001)

    def stop(self) -> None:
        self.write_register(0x2000, 0x0005)

    def set_frequency_hz(self, hz) -> None:
        self.write_engineering(0x2001, hz)

    def output_frequency_hz(self):
        _, eng = self.read_engineering(0x3000)
        return eng

    def status(self) -> dict:
        state, fault, warn = self.read_registers(0x2100, 3)
        return {"state": state, "fault_code": fault, "warning_code": warn}

    # -- audit -----------------------------------------------------------------

    def _audit(self, op: str, **fields) -> None:
        if not self.audit_path:
            return
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "op": op,
               "slave": self.slave, **fields}
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
