"""End-to-end tests: CLI verbs against the in-memory FakeTransport.

No hardware, no pyserial — these exercise transport -> RTU -> client -> CLI.
"""
from __future__ import annotations

import json

import pytest

from a650.cli import main
from a650.client import A650Client, DriveError
from a650.transport import fake as fake_mod
from a650.transport.fake import FakeTransport


@pytest.fixture(autouse=True)
def fresh_sessions():
    """Isolate tests from the process-wide shared fake-drive state."""
    fake_mod._SESSIONS.clear()
    yield
    fake_mod._SESSIONS.clear()


@pytest.fixture()
def audit(tmp_path):
    return tmp_path / "audit.jsonl"


def run_cli(*argv, audit_path=None, session=None):
    base = ["--simulate", "--audit", str(audit_path)] if audit_path else ["--simulate"]
    if session:
        base += ["--session", session]
    return main(base + list(argv))


# -- client level -------------------------------------------------------------

def test_client_read_write_roundtrip(audit):
    t = FakeTransport(slave=1)
    t.open()
    c = A650Client(transport=t, slave=1, audit_path=audit)
    # read-only by default: write must be denied
    from a650.a650lib.safety import WriteDenied
    with pytest.raises(WriteDenied):
        c.write_register(0x2000, 1)
    c.guard.enable_writes({0x2000, 0x2001})
    c.set_frequency_hz(30)
    assert t.registers[0x2001] == 3000
    c.start_forward()
    assert t.registers[0x2000] == 1
    assert c.output_frequency_hz() == pytest.approx(30.0)
    st = c.status()
    assert st["state"] == 1 and st["fault_code"] == 0
    # audit log written for both writes
    lines = [json.loads(l) for l in audit.read_text().splitlines()]
    assert [(r["address"], r["value"]) for r in lines] == [(8193, 3000), (8192, 1)]


def test_client_timeout_becomes_drive_error():
    class Deaf(FakeTransport):
        def exchange(self, request, expected_len, timeout_s):
            raise TimeoutError("nothing on the bus")
    t = Deaf(slave=1)
    t.open()
    c = A650Client(transport=t, slave=1, retries=1)
    with pytest.raises(DriveError):
        c.read_registers(0x3000)


def test_fake_rejects_bad_crc():
    t = FakeTransport()
    t.open()
    assert t.exchange(b"\x01\x030\x00\x00\x01\xff\xff", 7, 0.5) == b""


# -- CLI level ------------------------------------------------------------------

def test_cli_map_lists_registers(capsys):
    assert run_cli("map") == 0
    out = capsys.readouterr().out
    assert "0x2000" in out and "confidence=medium" in out


def test_cli_read_engineering_units(capsys):
    assert run_cli("read", "0x3000") == 0
    assert "Hz" in capsys.readouterr().out


def test_cli_write_requires_allow_write(capsys):
    rc = main(["--simulate", "write", "0x2001", "--raw", "3000"])
    assert rc == 2
    assert "--allow-write" in capsys.readouterr().err


def test_cli_full_flow_with_audit(capsys, audit):
    assert run_cli("--allow-write", "setfreq", "30", audit_path=audit) == 0
    assert run_cli("--allow-write", "start", audit_path=audit) == 0
    assert run_cli("status", audit_path=audit) == 0
    out = capsys.readouterr().out
    assert "output_freq=30.00 Hz" in out
    records = [json.loads(l) for l in audit.read_text().splitlines()]
    assert len(records) == 2


def test_cli_whitelist_blocks_unknown_address(capsys, audit):
    rc = run_cli("--allow-write", "--yes", "write", "0x2005", "--raw", "100",
                 audit_path=audit)
    assert rc == 3
    assert "not in writable whitelist" in capsys.readouterr().err
