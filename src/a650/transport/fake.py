"""In-memory fake drive for tests and --simulate runs.

Implements just enough A650 behaviour to exercise the full stack without
hardware: registers 0x2000 (command), 0x2001 (freq setpoint), 0x3000
(output frequency mirrors setpoint when running forward/reverse).

The fake drive is STATEFUL across instances sharing a session name so that
multi-invocation CLI flows (setfreq; start; status) behave like a real drive
on the bus. Default session "cli" persists for the process lifetime; tests
that need isolation pass their own session and reset it explicitly.

State model is intentionally simplified; command-word semantics are only
partially known (docs/REGISTERS.md):
  * any command value with bit0 set (e.g. 0x0001) means "run forward";
  * stop commands (e.g. 0x0005) have bit0 CLEAR — that is why we test b0
    rather than "cmd != 0".
"""
from __future__ import annotations

from ..modbus import rtu

# Shared register banks keyed by session name (simulates a persistent drive).
_SESSIONS: dict[str, dict[int, int]] = {}


def _default_bank() -> dict[int, int]:
    # 0x2100 defaults to 0 ("parameter setting mode") per manual enum.
    return {0x2000: 0x0000, 0x2001: 0x0000, 0x2100: 0x0000}


class FakeTransport:
    def __init__(self, slave: int = 1, session: str = "cli") -> None:
        self.slave = slave
        self.session = session
        self.registers: dict[int, int] = _SESSIONS.setdefault(session, _default_bank())
        self.log: list[bytes] = []          # every request frame seen
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def exchange(self, request: bytes, expected_len: int, timeout_s: float) -> bytes:
        if not self._open:
            raise RuntimeError("transport not opened")
        self.log.append(request)
        if not rtu.crc_ok(request):
            return b""  # corrupt request -> bus silence (timeout upstream)
        resp = self._handle(request)
        if resp and len(resp) != expected_len:
            raise AssertionError(
                f"fake drive length mismatch: built {len(resp)} bytes, "
                f"client expects {expected_len} for request {request.hex(' ')}"
            )
        return resp

    def _handle(self, req: bytes) -> bytes:
        slave, fc = req[0], req[1]
        if slave != self.slave:
            return b""
        if fc == rtu.FC_READ:
            addr, count = req[2] << 8 | req[3], req[4] << 8 | req[5]
            values = [self._read(addr + i) for i in range(count)]
            return rtu.build_read_response(slave, values)
        if fc == rtu.FC_WRITE:
            addr, value = req[2] << 8 | req[3], req[4] << 8 | req[5]
            self.registers[addr] = value
            self._apply_side_effects()
            return rtu.build_write_echo(slave, addr, value)
        return rtu.build_exception(slave, fc, 0x01)

    def _read(self, addr: int) -> int:
        if addr == 0x3000:  # output frequency: mirror setpoint when running fwd/rev
            cmd = self.registers.get(0x2000, 0)
            return self.registers.get(0x2001, 0) if cmd & 0x0003 else 0
        if addr in (0x2100, 0x2101, 0x2102, 0x2103):  # status block
            return self._status_word(addr)
        return self.registers.get(addr, 0)

    def _status_word(self, addr: int) -> int:
        cmd = self.registers.get(0x2000, 0)
        running_fwd = bool(cmd & 0x0001)   # manual example: start forward = 0x0001
        running_rev = bool(cmd & 0x0002)   # reverse bit is a research TODO (unverified)
        if addr == 0x2100:                 # drive state enum: 0 param, 1 run fwd, 2 run rev
            return 1 if running_fwd else 2 if running_rev else 0
        if addr == 0x2101:   # status bits: b0 = forward direction (simplified)
            return 1 if running_fwd else 0
        return 0             # no faults/warnings simulated

    def _apply_side_effects(self) -> None:
        pass
