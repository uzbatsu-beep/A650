"""Modbus RTU CRC16 (standard polynomial 0xA001, init 0xFFFF, low byte first).

Verified against the manual example frame for reading U00.00:
``01 03 30 00 00 01 -> 8B 0A`` (see docs/EXAMPLES.md, golden test).
"""
from __future__ import annotations


def crc16(data: bytes) -> int:
    """Return Modbus CRC16 as an integer (lo byte first when appended)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def append_crc(pdu_and_address: bytes) -> bytes:
    """Append CRC16 (low byte first) to a frame body."""
    crc = crc16(pdu_and_address)
    return pdu_and_address + bytes([crc & 0xFF, crc >> 8])


def check_crc(frame: bytes) -> bool:
    """Validate a complete RTU frame (CRC over all bytes except the last two)."""
    if len(frame) < 4:
        return False
    body, want = frame[:-2], frame[-2:]
    crc = crc16(body)
    return bytes([crc & 0xFF, crc >> 8]) == want
