"""Regression tests for the bench scanner; no hardware needed."""
import csv
import json
from threading import Event

import pytest

from a650.diagnostics import collect, read_targets, run_scan
from a650.client import A650Client
from a650.modbus.rtu import build_exception
from a650.transport.fake import FakeTransport


class RecordingClient:
    def __init__(self):
        self.slave = 1
        self.retries = 2
        self.calls = []

    def read_registers(self, address, count):
        self.calls.append((address, count))
        assert count == 1
        if address == 0x2102:
            raise RuntimeError("Modbus exception 0x02 (Illegal data address)")
        return (4 if address == 0x2101 else 0,)


TARGETS = [("state", 0x2100), ("bits", 0x2101), ("fault", 0x2102)]


def test_plan_omits_unreadable_control_password_and_eeprom():
    for model in ("A650", "A650M"):
        planned = read_targets(model)
        addresses = [addr for _, addr in planned]
        assert len(addresses) == len(set(addresses))
        assert all(0 <= addr < 0x8000 for addr in addresses)
        assert not {0x0000, 0x2000, 0x2005} & set(addresses)
        assert all(not code.startswith("H") for code, _ in planned)
        assert set(range(0x2100, 0x2104)).issubset(addresses)


def test_single_register_scan_persists_quality_and_csv(tmp_path):
    path = tmp_path / "bench.jsonl"
    client = RecordingClient()
    progress = []
    report = run_scan(client, TARGETS, path, model="A650", delay_s=0.03,
                      on_row=progress.append)
    assert report["completed"] and report["scanned"] == 3
    assert client.calls == [(0x2100, 1), (0x2101, 1), (0x2102, 1)]
    assert client.retries == 2
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    assert lines[0]["type"] == "session"
    assert lines[0]["planned"] == 3 and lines[0]["read_only"]
    assert len(lines) == 4 and len(progress) == 3
    assert lines[1]["raw"] == 0 and lines[2]["raw"] == 4
    assert lines[3]["quality"] == "exception_0x02"
    assert lines[3]["function"] == 3 and lines[3]["count"] == 1
    assert lines[1]["request_hex"].startswith("01 03 21 00 00 01")
    with path.with_suffix(".csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3 and rows[-1]["quality"] == "exception_0x02"


def test_stop_then_resume_does_not_repeat_completed_reads(tmp_path):
    path = tmp_path / "resume.jsonl"
    stop = Event()
    client = RecordingClient()

    def request_stop(row):
        stop.set()

    first = run_scan(client, TARGETS, path, model="A650", delay_s=0.03,
                     stop_event=stop, on_row=request_stop)
    assert not first["completed"] and first["scanned"] == 1
    assert client.calls == [(0x2100, 1)]
    stop.clear()
    second = run_scan(client, TARGETS, path, model="A650", delay_s=0.03,
                      stop_event=stop, resume=True)
    assert second["completed"] and second["scanned"] == 3
    assert client.calls == [(0x2100, 1), (0x2101, 1), (0x2102, 1)]
    assert len(path.read_text().splitlines()) == 4


def test_reject_overwriting_or_resuming_incompatible_file(tmp_path):
    path = tmp_path / "scan.jsonl"
    client = RecordingClient()
    run_scan(client, TARGETS, path, model="A650", delay_s=0.03)
    with pytest.raises(FileExistsError):
        run_scan(client, TARGETS, path, model="A650", delay_s=0.03)
    with pytest.raises(ValueError, match="metadata"):
        run_scan(client, TARGETS, path, model="A650M", delay_s=0.03, resume=True)
    with pytest.raises(ValueError, match="metadata"):
        run_scan(client, list(reversed(TARGETS)), path, model="A650",
                 delay_s=0.03, resume=True)


@pytest.mark.parametrize("invalid", [
    [("command", 0x2000)], [("unknown_h", 0x8000)],
    [("password", 0x0000)], [("a", 0x2100), ("b", 0x2100)],
])
def test_reject_unsafe_scan_plans(tmp_path, invalid):
    with pytest.raises(ValueError):
        run_scan(RecordingClient(), invalid, tmp_path / "blocked.jsonl",
                 model="A650", delay_s=0.03)


def test_partial_line_is_not_replayed(tmp_path):
    path = tmp_path / "bad.jsonl"
    client = RecordingClient()
    run_scan(client, TARGETS, path, model="A650", delay_s=0.03)
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"type":"reading"')
    with pytest.raises(ValueError, match="incomplete"):
        run_scan(client, TARGETS, path, model="A650", delay_s=0.03, resume=True)


def test_status_client_does_not_issue_the_rejected_four_register_block():
    class RestrictiveBench(FakeTransport):
        def exchange(self, request, expected_len, timeout_s):
            if (request[1] == 3 and request[2:4] == bytes((0x21, 0x00))
                    and request[4:6] == bytes((0x00, 0x04))):
                return build_exception(request[0], 3, 3)
            return super().exchange(request, expected_len, timeout_s)

    transport = RestrictiveBench(slave=1, session="status-single-read")
    transport.open()
    try:
        client = A650Client(transport, slave=1, retries=0)
        status = client.status()
        assert status["fault_code"] == 0 and status["warning_code"] == 0
        assert all(frame[1] == 3 for frame in transport.log)
        assert all(int.from_bytes(frame[4:6], "big") == 1
                   for frame in transport.log)
    finally:
        transport.close()
