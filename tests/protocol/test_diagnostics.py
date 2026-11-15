"""Safety and coverage checks for the read-only bench diagnostic."""
import json

import pytest

from a650.diagnostics import collect, read_targets


def test_targets_exclude_password_duplicates_and_undocumented_h():
    for model in ("A650", "A650M"):
        targets = read_targets(model)
        codes = [code for code, _ in targets]
        addresses = [address for _, address in targets]
        assert not {"F00.00", "F00.19", "F00.24"} & set(codes)
        assert not any(code.startswith("H") for code in codes)
        assert len(addresses) == len(set(addresses))
        assert ("state", 0x2100) in targets
        assert any(code.startswith("U") for code in codes)


def test_collect_uses_only_single_register_reads_and_keeps_errors():
    class FakeClient:
        def __init__(self):
            self.calls = []

        def read_registers(self, address, count):
            self.calls.append((address, count))
            if address == 0x3100:
                raise TimeoutError("no reply")
            return (123,)

    client = FakeClient()
    rows = list(collect(client, [("U00.00", 0x3000), ("U01.00", 0x3100)], delay_s=0))
    assert client.calls == [(0x3000, 1), (0x3100, 1)]
    assert rows[0]["raw"] == 123 and rows[0]["quality"] == "ok"
    assert rows[1]["quality"] == "error"
    assert "raw" not in rows[1]


def test_packaged_cli_diagnostics_preserves_serial_settings_and_sends_only_fc03(tmp_path, monkeypatch):
    from a650 import diagnostics
    from a650.cli import main
    from a650.transport.fake import FakeTransport

    class RecordingTransport(FakeTransport):
        def __init__(self):
            super().__init__(slave=2)
            self.requests = []

        def exchange(self, request, expected_len, timeout_s):
            self.requests.append(request)
            return super().exchange(request, expected_len, timeout_s)

    transport = RecordingTransport()
    options = []

    def serial(port, **kwargs):
        options.append((port, kwargs))
        return transport

    monkeypatch.setattr(diagnostics, 'SerialTransport', serial)
    monkeypatch.setattr(diagnostics, 'read_targets', lambda model: [('state', 0x2100), ('frequency', 0x3000)])
    path = tmp_path / 'снимок.jsonl'
    assert main(['diagnostics', '--port', 'COM17', '--model', 'A650', '--slave', '2',
                 '--baud', '19200', '--parity', 'E', '--stopbits', '2', '--output', str(path)]) == 0
    assert options == [('COM17', {'baudrate': 19200, 'parity': 'E', 'stopbits': 2})]
    assert len(transport.requests) == 2
    assert all(request[0:2] == b'\x02\x03' and request[4:6] == b'\x00\x01'
               for request in transport.requests)
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    assert [row['code'] for row in rows] == ['state', 'frequency']
    assert all(row['quality'] == 'ok' for row in rows)
    # An existing report must remain intact and no second exchange may start.
    before = path.read_bytes()
    with pytest.raises(SystemExit) as stopped:
        main(['diagnostics', '--port', 'COM17', '--model', 'A650', '--output', str(path)])
    assert stopped.value.code == 2
    assert path.read_bytes() == before and len(transport.requests) == 2 and len(options) == 1


@pytest.mark.parametrize('flag', ['--simulate', '--allow-write', '--yes'])
def test_diagnostics_rejects_unrelated_flags_before_opening_a_physical_port(tmp_path, monkeypatch, flag):
    from a650 import diagnostics
    from a650.cli import main

    def forbidden(*args, **kwargs):
        pytest.fail('Serial transport must not be constructed for rejected options')

    monkeypatch.setattr(diagnostics, 'SerialTransport', forbidden)
    with pytest.raises(SystemExit) as stopped:
        main([flag, 'diagnostics', '--port', 'COM17', '--model', 'A650', '--output', str(tmp_path / 'scan.jsonl')])
    assert stopped.value.code == 2
