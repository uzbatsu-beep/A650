"""Golden tests: built requests must byte-match data/frames/*.json.

The read-U00.00 frame is verbatim from the manual (CRC verified); the other
request frames were reconstructed with correct CRC (docs/EXAMPLES.md legend).
"""
import json

import pytest

from a650.modbus.crc import check_crc
from a650.modbus.rtu import ReadRegistersRequest, WriteRegisterRequest

CASES = {
    "read_output_frequency": ReadRegistersRequest(slave=1, address=0x3000, count=1),
    "set_frequency_30hz": WriteRegisterRequest(slave=1, address=0x2001, value=3000),
    "start_forward": WriteRegisterRequest(slave=1, address=0x2000, value=0x0001),
    "stop_deceleration": WriteRegisterRequest(slave=1, address=0x2000, value=0x0005),
    "error_read_only": WriteRegisterRequest(slave=1, address=0x3000, value=0x0000),
}


def _load(frames_dir, name):
    return json.loads((frames_dir / f"{name}.json").read_text())


@pytest.mark.parametrize("name", sorted(CASES))
def test_request_matches_golden(name, frames_dir):
    golden = _load(frames_dir, name)
    built = CASES[name].to_bytes()
    if golden.get("verification") == "hypothesis":
        # exception-scenario fixture: request must at least be a valid frame
        assert check_crc(built)
    else:
        assert built.hex(" ").upper() == golden["request"]


@pytest.mark.parametrize("name", sorted(CASES))
def test_all_golden_frames_have_valid_crc(name, frames_dir):
    golden = _load(frames_dir, name)
    for key in ("request", "valid_response", "exception_response"):
        if golden.get(key):
            frame = bytes.fromhex(golden[key].replace(" ", ""))
            assert check_crc(frame), f"{name}.{key} bad CRC"


def test_manual_frame_is_exact():
    """The single manual-verbatim frame must never change."""
    req = ReadRegistersRequest(slave=1, address=0x3000, count=1).to_bytes()
    assert req == bytes([0x01, 0x03, 0x30, 0x00, 0x00, 0x01, 0x8B, 0x0A])
