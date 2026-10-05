"""Tests for the interactive console (REPL) and CLI no-subcommand routing."""
from __future__ import annotations

import io
import sys

import pytest

from a650.cli import main
from a650.repl import Session, run_repl


BASE_SETTINGS = {
    "port": "/dev/ttyUSB0", "baud": 9600, "parity": "N", "slave": 1,
    "simulate": True, "allow_write": True, "yes": True,
    "session": "repl-test", "audit": None,
}


@pytest.fixture()
def tmp_audit(tmp_path, monkeypatch):
    p = tmp_path / "audit.jsonl"
    s = dict(BASE_SETTINGS)
    s["audit"] = str(p)
    return s, p


def feed(monkeypatch, lines: list[str]):
    it = iter(lines)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))


class TestReplSession:
    def test_state_persists_across_commands(self, tmp_audit, monkeypatch, capsys):
        settings, audit = tmp_audit
        session = Session(settings)
        session.reconnect()
        from a650.repl import do_setfreq, do_start, do_status
        do_setfreq(session, ["setfreq", "30"])
        do_start(session, ["start"])
        do_status(session, ["status"])
        out = capsys.readouterr().out
        assert "wrote 0x2001 raw=3000" in out
        assert "state=1 (running fwd)" in out
        assert "output=30.00 Hz" in out
        # audit log written
        assert audit.exists() and '"address": 8193' in audit.read_text()
        session.close()

    def test_read_only_refuses_writes(self, tmp_audit, monkeypatch, capsys):
        settings, _ = tmp_audit
        settings["allow_write"] = False
        session = Session(settings)
        session.reconnect()
        from a650.repl import do_setfreq
        rc = do_setfreq(session, ["setfreq", "45"])
        assert rc == 1
        assert "refusing to write" in capsys.readouterr().out
        session.close()

    def test_connect_switches_settings(self, tmp_audit, capsys):
        settings, _ = tmp_audit
        session = Session(settings)
        session.reconnect()
        from a650.repl import do_connect
        do_connect(session, ["connect", "--baud", "19200", "--slave", "2"])
        assert session.settings["baud"] == 19200
        assert session.settings["slave"] == 2
        assert "connected:" in capsys.readouterr().out
        session.close()


class TestRunRepl:
    def test_full_scripted_session(self, tmp_audit, monkeypatch, capsys):
        settings, _ = tmp_audit
        feed(monkeypatch, ["status", "setfreq 10", "start", "status", "stop", "exit"])
        rc = run_repl(settings)
        assert rc == 0
        out = capsys.readouterr().out
        assert "interactive console" in out
        assert "state=1 (running fwd)" in out
        assert "bye." in out

    def test_unknown_command_and_eof(self, tmp_audit, monkeypatch, capsys):
        settings, _ = tmp_audit
        lines = iter(["bogus", "help"])

        def scripted_input(prompt=""):
            try:
                return next(lines)
            except StopIteration:
                raise EOFError  # loop must terminate gracefully on EOF
        monkeypatch.setattr("builtins.input", scripted_input)
        rc = run_repl(settings)
        assert rc == 0
        out = capsys.readouterr().out
        assert "unknown command 'bogus'" in out
        assert "commands:" in out  # help text printed

    def test_cli_no_subcommand_enters_repl(self, tmp_audit, monkeypatch, capsys):
        settings, _ = tmp_audit
        monkeypatch.setattr(
            "a650.repl.run_repl",
            lambda initial, stdin=None: print("REPL-ENTERED") or 0)
        argv = ["--simulate", "--allow-write"]
        if settings.get("audit"):
            argv += ["--audit", settings["audit"]]
        rc = main(argv)
        assert rc == 0
        assert "REPL-ENTERED" in capsys.readouterr().out

    def test_cli_subcommands_still_work(self, tmp_audit, capsys):
        settings, _ = tmp_audit
        rc = main(["--simulate", "--audit", settings["audit"], "read", "0x3000"])
        assert rc == 0
        assert "0" in capsys.readouterr().out
