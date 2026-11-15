"""Pure Modbus RTU frame building/parsing (no I/O).

Only function codes known to be used by the A650 are implemented:
0x03 (read), 0x06 (write single register). 0x08 is TODO (no documented frames yet).

Address convention on A650: registers are addressed by their plain number
(e.g. U00.00 monitor lives at 0x3000 and is read with start address 0x3000 —
confirmed by the CRC-verified manual frame; no holding/input offset applied).
"""
from __future__ import annotations

from dataclasses import dataclass

from .crc import append_crc, check_crc

FC_READ = 0x03
FC_WRITE = 0x06
EXC_BIT = 0x80

# Standard Modbus exception names; device-specific behavior needs verification.
EXCEPTION_NAMES = {
    0x01: "Illegal function",
    0x02: "Illegal data address",
    0x03: "Illegal data value",
    0x04: "Operation not executed",
    # 0x11 "read-only parameter" is mentioned in the manual; how it is exposed
    # (raw exception code? different mechanism?) is UNVERIFIED.
}


@dataclass(frozen=True)
class ReadRegistersRequest:
    slave: int
    address: int
    count: int

    def __post_init__(self):
        if not 1 <= self.slave <= 247:
            raise ValueError(f"slave out of unicast range: {self.slave}")
        if not 1 <= self.count <= 8:
            raise ValueError("A650 reads require 1 to 8 registers per request")
        if not 0 <= self.address <= 0xFFFF or self.address + self.count > 0x10000:
            raise ValueError("read range outside uint16 register space")

    def to_bytes(self) -> bytes:
        return append_crc(
            bytes([self.slave, FC_READ, self.address >> 8, self.address & 0xFF,
                   self.count >> 8, self.count & 0xFF])
        )


@dataclass(frozen=True)
class WriteRegisterRequest:
    slave: int
    address: int
    value: int

    def __post_init__(self):
        # Frozen dataclass: plain assignment is fine here; validation must run
        # at construction time so callers can never build an invalid frame.
        if not 0 <= self.slave <= 0xFF:
            raise ValueError(f"slave out of range: {self.slave}")
        if not 0 <= self.address <= 0xFFFF:
            raise ValueError(f"address out of range: {self.address}")
        if not 0 <= self.value <= 0xFFFF:
            raise ValueError(f"value out of uint16 range: {self.value}")

    def to_bytes(self) -> bytes:
        return append_crc(
            bytes([self.slave, FC_WRITE,
                   self.address >> 8, self.address & 0xFF,
                   self.value >> 8, self.value & 0xFF])
        )


@dataclass(frozen=True)
class ReadRegistersResponse:
    values: tuple[int, ...]


@dataclass(frozen=True)
class ExceptionResponse:
    function: int          # original function code (without 0x80)
    code: int

    @property
    def name(self) -> str:
        return EXCEPTION_NAMES.get(self.code, f"Unknown exception 0x{self.code:02X}")


def parse_response(frame: bytes, expected_slave: int | None = None,
                   expected_function: int | None = None) -> ReadRegistersResponse | ExceptionResponse:
    """Parse a complete RTU response frame (with CRC)."""
    if len(frame) < 5:
        raise ValueError("truncated response")
    if not check_crc(frame):
        raise ValueError("bad CRC")
    slave, fc = frame[0], frame[1]
    if expected_slave is not None and slave != expected_slave:
        raise ValueError(f"slave mismatch: got {slave:#02x}, expected {expected_slave:#02x}")
    if expected_function is not None and (fc & ~EXC_BIT) != expected_function:
        raise ValueError("function mismatch between request and response")
    if fc & EXC_BIT:
        if len(frame) != 5:
            raise ValueError("invalid exception response length")
        return ExceptionResponse(function=fc & ~EXC_BIT, code=frame[2])
    if fc == FC_READ:
        byte_count = frame[2]
        if byte_count == 0 or byte_count % 2:
            raise ValueError("invalid read byte count")
        if len(frame) != byte_count + 5:
            raise ValueError("invalid read response length")
        data = frame[3:3 + byte_count]
        if len(data) != byte_count:
            raise ValueError("truncated read response")
        values = tuple(int.from_bytes(data[i:i + 2], "big") for i in range(0, byte_count, 2))
        return ReadRegistersResponse(values=values)
    if fc == FC_WRITE:
        if len(frame) != 8:
            raise ValueError("invalid write response length")
        # FC06 echoes the request; validated by callers against the sent request.
        address = int.from_bytes(frame[2:4], "big")
        value = int.from_bytes(frame[4:6], "big")
        return ReadRegistersResponse(values=(address, value))
    raise ValueError(f"unsupported function code {fc:#02x}")


# --- frame builders (used by client and fake drive) -------------------------

def build_read_response(slave: int, values: list[int] | tuple[int, ...]) -> bytes:
    byte_count = 2 * len(values)
    body = bytes([slave, FC_READ, byte_count]) + b"".join(
        v.to_bytes(2, "big") for v in values
    )
    return append_crc(body)


def build_write_echo(slave: int, address: int, value: int) -> bytes:
    return WriteRegisterRequest(slave=slave, address=address, value=value).to_bytes()


def build_exception(slave: int, function: int, code: int) -> bytes:
    return append_crc(bytes([slave, function | EXC_BIT, code]))


def crc_ok(frame: bytes) -> bool:
    """Alias kept for readability in transport implementations."""
    return check_crc(frame)


def expected_response_len(request: bytes) -> int:
    """Compute the exact RTU response length for a given request frame."""
    fc = request[1]
    if fc == FC_READ:
        count = int.from_bytes(request[4:6], "big")
        return 3 + 2 * count + 2          # slave+fc+bc + data + crc
    if fc == FC_WRITE:
        return 8                           # echo of the 8-byte request
    return 5                               # exception: slave+fc+code+crc
