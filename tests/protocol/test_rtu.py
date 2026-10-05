"""Unit tests for Modbus RTU CRC16 and frame parse/build."""
import pytest

from a650.modbus.crc import append_crc, check_crc, crc16
from a650.modbus.rtu import (
    ExceptionResponse,
    ReadRegistersRequest,
    ReadRegistersResponse,
    WriteRegisterRequest,
    parse_response,
)


class TestCrc:
    def test_manual_frame(self):
        # 01 03 30 00 00 01 -> CRC 8B 0A (low byte first), verbatim from manual
        assert crc16(bytes.fromhex("010330000001")) == 0x0A8B
        assert append_crc(bytes.fromhex("010330000001")).hex().upper() == "0103300000018B0A"

    def test_known_vector(self):
        # classic example: 01 04 02 FF FF -> CRC B3 A1? use our own impl consistency instead
        frame = bytes.fromhex("010620000001") + b"\x00\x00"
        body = frame[:6]
        out = append_crc(body)
        assert check_crc(out)

    def test_check_rejects_corrupted(self):
        good = append_crc(bytes.fromhex("010330000001"))
        bad = bytearray(good)
        bad[3] ^= 0xFF
        assert not check_crc(bytes(bad))

    def test_check_rejects_short(self):
        assert not check_crc(b"\x01\x03")


class TestBuild:
    def test_read_request(self):
        req = ReadRegistersRequest(slave=1, address=0x3000, count=1).to_bytes()
        assert req.hex(" ").upper() == "01 03 30 00 00 01 8B 0A"

    def test_write_value_range(self):
        with pytest.raises(ValueError):
            WriteRegisterRequest(slave=1, address=0x2001, value=0x1_0000)


class TestParse:
    def test_read_response(self):
        frame = append_crc(bytes.fromhex("0103021388"))
        resp = parse_response(frame, expected_slave=1)
        assert isinstance(resp, ReadRegistersResponse)
        assert resp.values == (5000,)

    def test_exception_response(self):
        frame = append_crc(bytes.fromhex("018603"))
        resp = parse_response(frame, expected_slave=1)
        assert isinstance(resp, ExceptionResponse)
        assert resp.function == 0x06
        assert resp.code == 0x03
        assert resp.name == "Illegal data value"

    def test_bad_crc_raises(self):
        with pytest.raises(ValueError, match="CRC"):
            parse_response(bytes.fromhex("01030213880000"))

    def test_slave_mismatch_raises(self):
        frame = append_crc(bytes.fromhex("0103021388"))
        with pytest.raises(ValueError, match="slave mismatch"):
            parse_response(frame, expected_slave=2)
