"""Read-only bench diagnostic for ONI A650/A650M.

Run: python -m a650.diagnostics --port COM3 --model A650
No Modbus write requests are constructed by this module.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from .a650lib.catalog import load_catalog
from .client import A650Client
from .transport.serial import SerialTransport


def read_targets(model: str) -> list[tuple[str, int]]:
    """Documented F/U RAM addresses only; exclude passwords and ambiguous entries."""
    targets = [("state", 0x2100), ("status_bits", 0x2101)]
    seen = {0x2100, 0x2101}
    for entry in load_catalog(model):
        if (entry.ram is None or entry.duplicate or entry.conflict
                or entry.code in {"F00.00", "F00.19", "F00.24"}
                or "парол" in entry.name.casefold() or "password" in entry.name.casefold()
                or not entry.code.startswith(("F", "U"))):
            continue
        if entry.ram not in seen:
            targets.append((entry.code, entry.ram))
            seen.add(entry.ram)
    return targets


def collect(client: A650Client, targets, *, delay_s: float = 0.03):
    """Read one register at a time, retain failures and raw unsigned values."""
    for code, address in targets:
        row = {"timestamp": datetime.now(timezone.utc).isoformat(),
               "code": code, "address": f"0x{address:04X}"}
        try:
            row["raw"] = client.read_registers(address, 1)[0]
            row["quality"] = "ok"
        except Exception as exc:
            row["quality"] = "error"
            row["error"] = str(exc)
        yield row
        if delay_s:
            time.sleep(delay_s)


def add_arguments(parser):
    """Share the same explicit connection options with the packaged CLI."""
    parser.add_argument("--port", required=True, help="Windows COM port, e.g. COM3")
    parser.add_argument("--model", choices=("A650", "A650M"), required=True)
    parser.add_argument("--slave", type=int, default=1)
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--parity", choices=("N", "E", "O"), default="N")
    parser.add_argument("--stopbits", type=int, choices=(1, 2), default=1)
    parser.add_argument("--timeout", type=float, default=0.8)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_diagnostic(args, parser) -> int:
    if any(getattr(args, flag, False) for flag in ('simulate', 'allow_write', 'yes')):
        parser.error('diagnostics is a physical read-only scan; omit --simulate, --allow-write and --yes')
    if not 1 <= args.slave <= 247:
        parser.error("slave must be 1..247")
    if not 0.1 <= args.timeout <= 10:
        parser.error("timeout must be 0.1..10 seconds")
    if args.output.exists():
        parser.error("output already exists; choose a new filename")
    transport = SerialTransport(args.port, baudrate=args.baud,
                                parity=args.parity, stopbits=args.stopbits)
    client = A650Client(transport, slave=args.slave, retries=0,
                        timeout_s=args.timeout)
    try:
        transport.open()
        with args.output.open("x", encoding="utf-8") as stream:
            for row in collect(client, read_targets(args.model)):
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f'{row["code"]} {row["address"]}: {row.get("raw", row.get("error"))}')
    finally:
        transport.close()
    return 0


def main(argv=None) -> int:
    parser = add_arguments(argparse.ArgumentParser(description="A650 bench read-only Modbus RTU scan"))
    return run_diagnostic(parser.parse_args(argv), parser)


if __name__ == "__main__":
    raise SystemExit(main())
