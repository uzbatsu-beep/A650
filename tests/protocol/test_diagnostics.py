"""Safety and coverage checks for the read-only bench diagnostic."""
from a650.diagnostics import collect, read_targets


def test_targets_exclude_password_duplicates_and_undocumented_h():
    for model in ("A650", "A650M"):
        targets = read_targets(model)
        codes = [code for code, _ in targets]
        addresses = [address for _, address in targets]
        assert "F00.00" not in codes
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
