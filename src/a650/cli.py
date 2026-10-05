"""a650 — command-line configurator for ONI A650 (Modbus RTU over RS-485).

Safety model (docs/SAFETY.md):
  * reads are always allowed;
  * writes require --allow-write AND an explicit confirmation unless --yes;
  * every write is appended to an audit log (--audit, default ./a650-audit.jsonl);
  * --simulate runs against an in-memory fake drive (no hardware needed) and
    never touches a serial port.
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from .a650lib.register_map import RegisterMap
from .a650lib.safety import SafetyGuard, WriteDenied
from .client import A650Client, DriveError
from .transport.fake import FakeTransport

__version__ = "0.0.1"

# Addresses we know are writable from the manual examples only.
KNOWN_WRITABLE = {0x2000, 0x2001}


def build_transport(args: argparse.Namespace):
    if args.simulate:
        return FakeTransport(slave=args.slave)
    from .transport.serial import SerialTransport  # lazy: needs pyserial
    return SerialTransport(port=args.port, baudrate=args.baud, parity=args.parity)


def parse_addr(text: str) -> int:
    return int(text, 0)  # accepts 0x3000 and 12288


def make_client(args: argparse.Namespace) -> A650Client:
    guard = SafetyGuard()
    if args.allow_write:
        guard.enable_writes(set(KNOWN_WRITABLE))
    transport = build_transport(args)
    transport.open()
    return A650Client(transport=transport, slave=args.slave, guard=guard,
                      register_map=RegisterMap.load(),
                      audit_path=args.audit)


def cmd_read(args: argparse.Namespace) -> int:
    client = make_client(args)
    try:
        addr = parse_addr(args.address)
        values = client.read_registers(addr, args.count)
        try:
            reg = client.map.get(addr)
            engs = [str(reg.to_engineering(v)) for v in values]
            print(" ".join(f"{v} ({e} {reg.unit})" for v, e in zip(values, engs)))
        except KeyError:
            print(" ".join(str(v) for v in values))
        return 0
    finally:
        client.transport.close()


def cmd_status(args: argparse.Namespace) -> int:
    client = make_client(args)
    try:
        st = client.status()
        freq = client.output_frequency_hz()
        print(f"state={st['state']} fault={st['fault_code']} "
              f"warning={st['warning_code']} output_freq={freq} Hz")
        return 0
    finally:
        client.transport.close()


def _confirm(args: argparse.Namespace, what: str) -> bool:
    if args.yes or args.simulate:
        return True
    answer = input(f"About to WRITE to drive: {what}. Type 'yes' to confirm: ")
    return answer.strip() == "yes"


def cmd_write(args: argparse.Namespace) -> int:
    if not args.allow_write:
        print("refusing to write without --allow-write (read-only default, see docs/SAFETY.md)",
              file=sys.stderr)
        return 2
    addr = parse_addr(args.address)
    raw = None if args.engineering is not None else int(args.value, 0)
    what = f"register {addr:#06x} = {args.value if raw is not None else args.engineering}"
    if not _confirm(args, what):
        print("aborted", file=sys.stderr)
        return 1
    client = make_client(args)
    try:
        if args.engineering is not None:
            written = client.write_engineering(addr, Decimal(args.engineering))
            print(f"wrote {addr:#06x} raw={written}")
        else:
            client.write_register(addr, raw)
            print(f"wrote {addr:#06x} raw={raw}")
        return 0
    except (WriteDenied, DriveError) as exc:
        print(f"write refused/failed: {exc}", file=sys.stderr)
        return 3
    finally:
        client.transport.close()


def cmd_start(args: argparse.Namespace) -> int:
    ns = argparse.Namespace(**vars(args))
    ns.address, ns.value, ns.engineering = "0x2000", "1", None
    return cmd_write(ns)


def cmd_stop(args: argparse.Namespace) -> int:
    ns = argparse.Namespace(**vars(args))
    ns.address, ns.value, ns.engineering = "0x2000", "5", None
    return cmd_write(ns)


def cmd_setfreq(args: argparse.Namespace) -> int:
    ns = argparse.Namespace(**vars(args))
    ns.address, ns.value, ns.engineering = "0x2001", None, args.hz
    return cmd_write(ns)


def cmd_map(args: argparse.Namespace) -> int:
    rmap = RegisterMap.load()
    rows = rmap.by_name(args.filter) if args.filter else \
        [rmap.get(a) for a in rmap.addresses()]
    for r in rows:
        print(f"{r.address:#06x}  {r.name:<28} {r.access:<3} scale={r.scale} {r.unit:<6} "
              f"confidence={r.confidence} verified={r.verified_on_device}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="a650", description=__doc__.splitlines()[0])
    ap.add_argument("--version", action="version", version=f"a650 {__version__}")
    ap.add_argument("--port", default="/dev/ttyUSB0", help="serial port (default %(default)s)")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--parity", default="N", choices=["N", "E", "O"])
    ap.add_argument("--slave", type=int, default=1)
    ap.add_argument("--simulate", action="store_true",
                    help="use built-in fake drive (no hardware, no pyserial)")
    ap.add_argument("--allow-write", action="store_true",
                    help="enable writes to the known-writable whitelist (0x2000, 0x2001)")
    ap.add_argument("--yes", action="store_true", help="skip interactive write confirmation")
    ap.add_argument("--audit", default="a650-audit.jsonl", help="audit log path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("read", help="read register(s)")
    p.add_argument("address")
    p.add_argument("--count", type=int, default=1)
    p.set_defaults(fn=cmd_read)

    p = sub.add_parser("status", help="read state/fault/warning/output frequency")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("write", help="write one register (raw or engineering value)")
    p.add_argument("address")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--raw", dest="value", help="raw uint16, e.g. 0x0B B8 / 3000")
    g.add_argument("--eng", dest="engineering", help="engineering value via map scale")
    p.set_defaults(fn=cmd_write)

    p = sub.add_parser("start", help="start forward (0x2000 <- 0x0001)")
    p.set_defaults(fn=cmd_start)
    p = sub.add_parser("stop", help="decel stop (0x2000 <- 0x0005)")
    p.set_defaults(fn=cmd_stop)
    p = sub.add_parser("setfreq", help="set frequency setpoint in Hz")
    p.add_argument("hz")
    p.set_defaults(fn=cmd_setfreq)

    p = sub.add_parser("map", help="list known registers with confidence flags")
    p.add_argument("--filter", default=None)
    p.set_defaults(fn=cmd_map)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except DriveError as exc:
        print(f"drive error: {exc}", file=sys.stderr)
        return 4
    except FileNotFoundError as exc:
        print(f"not found: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
