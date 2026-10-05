"""Interactive console (REPL) for a650 — the human-friendly interface.

Run with:  a650            (no subcommand -> interactive mode)
           a650 --simulate (fake drive, no hardware)
           a650 --port COM3 --allow-write

Design notes
------------
* One transport/client instance is created at startup and reused for every
  command, so drive state persists across commands (like a real bus session).
* Commands use the same grammar as the CLI verbs, e.g.:
      read 0x3000
      status
      setfreq 30
      start / stop
      write 0x2000 raw 1 | write 0x2001 eng 45.5
      map [filter]
      connect --port COM3 --baud 19200 [--simulate] [--allow-write]
      audit            (tail of the audit log)
      help / ?         commands overview
      exit / quit
* Safety model unchanged: writes require --allow-write (or `connect ...
  --allow-write`) plus confirmation unless started with --yes.
"""
from __future__ import annotations

import shlex
import sys
from decimal import Decimal, InvalidOperation

from .a650lib.register_map import RegisterMap
from .a650lib.safety import SafetyGuard, WriteDenied
from .client import A650Client, DriveError
from .transport.fake import FakeTransport

BANNER = "a650 configurator v{version} — interactive console. Type 'help'."


class Session:
    """Holds connection settings + one live client."""

    def __init__(self, args_defaults: dict):
        self.settings = dict(args_defaults)   # port/baud/parity/slave/simulate/allow_write/yes/session/audit
        self.client: A650Client | None = None
        self.map = RegisterMap.load()

    # ------------------------------------------------------------------ conn
    def reconnect(self, **overrides) -> None:
        if self.client is not None:
            try:
                self.client.transport.close()
            except Exception:
                pass
        self.settings.update({k: v for k, v in overrides.items() if v is not None})
        from .cli import build_transport, resolve_audit_path  # reuse single source of truth
        import argparse
        ns = argparse.Namespace(**self.settings)
        guard = SafetyGuard()
        if self.settings.get("allow_write"):
            from .cli import KNOWN_WRITABLE
            guard.enable_writes(set(KNOWN_WRITABLE))
        transport = build_transport(ns)
        transport.open()
        self.client = A650Client(
            transport=transport, slave=self.settings["slave"], guard=guard,
            register_map=self.map, audit_path=resolve_audit_path(ns))
        mode = "SIMULATED drive" if self.settings.get("simulate") else \
            f"{self.settings['port']} @{self.settings['baud']},{self.settings['parity']}" \
            f", slave {self.settings['slave']}"
        w = "writes ENABLED" if self.settings.get("allow_write") else "read-only"
        print(f"connected: {mode} ({w})")

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.transport.close()
            finally:
                self.client = None


def _fmt_value(session: Session, addr: int, values: list[int]) -> str:
    try:
        reg = session.map.get(addr)
        return "  ".join(f"{v} ({reg.to_engineering(v)} {reg.unit})" for v in values)
    except KeyError:
        return "  ".join(str(v) for v in values)


# --------------------------------------------------------------------- verbs
def do_read(session: Session, toks: list[str]) -> int:
    if len(toks) not in (2, 3):
        print("usage: read <addr> [count]   e.g. read 0x3000 2")
        return 2
    addr = int(toks[1], 0)
    count = int(toks[2]) if len(toks) == 3 else 1
    vals = session.client.read_registers(addr, count)
    print(_fmt_value(session, addr, vals))
    return 0


def do_status(session: Session, toks: list[str]) -> int:
    st = session.client.status()
    freq = session.client.output_frequency_hz()
    state_names = {0: "stopped", 1: "running fwd", 2: "running rev"}
    sname = state_names.get(st["state"], f"code {st['state']}")
    fault = f"FAULT Err{st['fault_code']:02d}" if st["fault_code"] else "no fault"
    warn = f"warning={st['warning_code']}" if st["warning_code"] else ""
    print(f"state={st['state']} ({sname})  {fault}  {warn}  output={freq:.2f} Hz")
    return 0


def _write_gate(session: Session, what: str) -> bool:
    if not session.settings.get("allow_write"):
        print("refusing to write without --allow-write (start with it, or: connect --allow-write)")
        return False
    if session.settings.get("yes") or session.settings.get("simulate"):
        return True
    ans = input(f"About to WRITE to drive: {what}. Type 'yes' to confirm: ")
    return ans.strip() == "yes"


def do_setfreq(session: Session, toks: list[str]) -> int:
    if len(toks) != 2:
        print("usage: setfreq <Hz>   e.g. setfreq 30")
        return 2
    try:
        hz = Decimal(toks[1])
    except InvalidOperation:
        print("not a number"); return 2
    if not _write_gate(session, f"frequency setpoint = {hz} Hz"):
        return 1
    written = session.client.write_engineering(0x2001, hz)
    print(f"wrote 0x2001 raw={written}  ({hz} Hz)")
    return 0


def do_start(session: Session, toks: list[str]) -> int:
    if not _write_gate(session, "command word 0x2000 = 0x0001 (run forward)"):
        return 1
    session.client.write_register(0x2000, 0x0001)
    print("started (forward)")
    return 0


def do_stop(session: Session, toks: list[str]) -> int:
    if not _write_gate(session, "command word 0x2000 = 0x0005 (stop)"):
        return 1
    session.client.write_register(0x2000, 0x0005)
    print("stopped")
    return 0


def do_write(session: Session, toks: list[str]) -> int:
    if len(toks) != 4 or toks[2] not in ("raw", "eng"):
        print("usage: write <addr> raw <uint16> | write <addr> eng <value>")
        return 2
    addr = int(toks[1], 0)
    if not _write_gate(session, f"register {addr:#06x} {toks[2]} {toks[3]}"):
        return 1
    if toks[2] == "raw":
        raw = int(toks[3], 0)
        session.client.write_register(addr, raw)
        print(f"wrote {addr:#06x} raw={raw}")
    else:
        written = session.client.write_engineering(addr, Decimal(toks[3]))
        print(f"wrote {addr:#06x} raw={written}")
    return 0


def do_map(session: Session, toks: list[str]) -> int:
    filt = toks[1] if len(toks) > 1 else None
    rows = session.map.by_name(filt) if filt else \
        [session.map.get(a) for a in session.map.addresses()]
    for r in rows:
        print(f"{r.address:#06x}  {r.name:<28} {r.access:<3} scale={r.scale} "
              f"{r.unit:<6} confidence={r.confidence}")
    return 0


def do_connect(session: Session, toks: list[str]) -> int:
    flags = {"--port": "port", "--baud": "baud", "--parity": "parity",
             "--slave": "slave", "--session": "session", "--audit": "audit"}
    overrides: dict = {}
    i = 1
    while i < len(toks):
        t = toks[i]
        if t in flags:
            if i + 1 >= len(toks):
                print(f"missing value for {t}"); return 2
            v = toks[i + 1]
            overrides[flags[t]] = int(v) if flags[t] in ("baud", "slave") else v
            i += 2
        elif t == "--simulate":
            overrides["simulate"] = True; i += 1
        elif t == "--real":
            overrides["simulate"] = False; i += 1
        elif t == "--allow-write":
            overrides["allow_write"] = True; i += 1
        elif t == "--read-only":
            overrides["allow_write"] = False; i += 1
        elif t == "--yes":
            overrides["yes"] = True; i += 1
        else:
            print(f"unknown option {t}"); return 2
    session.reconnect(**overrides)
    return 0


def do_audit(session: Session, toks: list[str]) -> int:
    from .cli import default_audit_path, resolve_audit_path
    import argparse
    path = resolve_audit_path(argparse.Namespace(audit=session.settings.get("audit")))
    if not path.exists():
        print(f"audit log empty ({path})"); return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    n = int(toks[1]) if len(toks) > 1 and toks[1].isdigit() else 10
    for line in lines[-n:]:
        print(line)
    return 0


HELP_TEXT = """\
commands:
  read <addr> [count]     read holding register(s), show raw + engineering
  status                  drive state / fault / warning / output frequency
  setfreq <Hz>            write frequency setpoint (0x2001)
  start | stop            run forward / deceleration stop (0x2000)
  write <addr> raw|eng X  generic register write
  map [substring]         known register catalog with confidence flags
  connect [opts]          (re)connect: --port COM3 --baud 9600 --parity N
                          --slave 1 --simulate --real --allow-write --yes
  audit [N]               last N entries of the write audit log
  help | ?                this text
  exit | quit             leave the console
safety: writes need --allow-write; real drives ask for typed confirmation."""


COMMANDS = {
    "read": do_read, "status": do_status, "setfreq": do_setfreq,
    "start": do_start, "stop": do_stop, "write": do_write,
    "map": do_map, "connect": do_connect, "audit": do_audit,
}


def run_repl(initial_settings: dict, stdin=sys.stdin) -> int:
    from .cli import __version__
    print(BANNER.format(version=__version__))
    session = Session(initial_settings)
    session.reconnect()          # opens simulate or serial per initial settings
    print("drive state persists between commands; type 'help' for commands.\n")
    while True:
        try:
            line = input("a650> ").strip()
        except EOFError:
            print(); break
        except KeyboardInterrupt:
            print("^C"); continue
        if not line:
            continue
        try:
            toks = shlex.split(line)
        except ValueError as exc:
            print(f"parse error: {exc}"); continue
        cmd, rest = toks[0].lower(), toks[1:]
        if cmd in ("exit", "quit"):
            break
        elif cmd in ("help", "?"):
            print(HELP_TEXT)
        elif cmd in COMMANDS:
            try:
                COMMANDS[cmd](session, [cmd] + rest)
            except (DriveError, WriteDenied) as exc:
                print(f"error: {exc}")
            except ValueError as exc:
                print(f"bad argument: {exc}")
        else:
            print(f"unknown command '{cmd}' — type 'help'")
    session.close()
    print("bye.")
    return 0
