"""Fault injection at the transaction boundary, without a serial device."""
import pytest

from a650.client import A650Client, DriveError, WriteOutcomeUnknown
from a650.modbus.crc import append_crc
from a650.modbus.rtu import ReadRegistersRequest, parse_response, build_read_response


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def exchange(self, request, expected_len, timeout_s):
        self.requests.append(request)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.parametrize("body", [
    "01030112",          # odd byte count
    "010300",            # empty read
    "01030212345678",    # trailing data despite a valid CRC
    "0103041234",        # missing register
    "010620010b",        # short write echo
    "010620010bb800",    # long write echo
    "01860300",          # long exception
    "0186",              # short exception
])
def test_crc_does_not_make_malformed_frame_valid(body):
    with pytest.raises(ValueError):
        parse_response(append_crc(bytes.fromhex(body)), expected_slave=1)


@pytest.mark.parametrize("slave,address,count", [
    (0, 0x3000, 1), (248, 0x3000, 1), (1, 0x3000, 0),
    (1, 0x3000, 9), (1, -1, 1), (1, 0xFFFF, 2),
])
def test_invalid_read_rejected_before_io(slave, address, count):
    with pytest.raises(ValueError):
        ReadRegistersRequest(slave, address, count)


@pytest.mark.parametrize("body", ["010620010bb8", "018602"])
def test_read_rejects_write_reply_or_write_exception(body):
    transport = ScriptedTransport([append_crc(bytes.fromhex(body))])
    client = A650Client(transport)
    with pytest.raises(DriveError, match="function mismatch"):
        client.read_registers(0x3000)


def test_read_rejects_wrong_number_of_registers():
    client = A650Client(ScriptedTransport([build_read_response(1, [10, 20])]))
    with pytest.raises(DriveError, match="requested 1 registers"):
        client.read_registers(0x3000)


def test_read_can_retry_after_timeout():
    transport = ScriptedTransport([TimeoutError(), build_read_response(1, [1234])])
    client = A650Client(transport, retries=1)
    assert client.read_registers(0x3000) == (1234,)
    assert len(transport.requests) == 2


def test_lost_write_acknowledgement_never_repeats_command():
    transport = ScriptedTransport([TimeoutError("ack lost after execution")])
    client = A650Client(transport, retries=5)
    client.guard.enable_writes({0x2000})
    with pytest.raises(WriteOutcomeUnknown, match="outcome unknown"):
        client.start_forward()
    assert len(transport.requests) == 1


def test_write_rejects_read_reply_even_when_values_look_like_echo():
    transport = ScriptedTransport([build_read_response(1, [0x2000, 1])])
    client = A650Client(transport)
    client.guard.enable_writes({0x2000})
    with pytest.raises(DriveError, match="function mismatch"):
        client.start_forward()
    assert len(transport.requests) == 1
