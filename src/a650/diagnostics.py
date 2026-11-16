"""Read-only, resumable, one-register-at-a-time bench discovery for ONI A650.

Only curated F/U RAM and status addresses are attempted. No write frames are built.
This is an empirical access map for ONE device/firmware, not a universal map.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import Event
import time

from .a650lib.catalog import load_catalog
from .client import A650Client
from .modbus.rtu import ReadRegistersRequest
from .transport.serial import SerialTransport

SCHEMA = "a650-register-scan/v1"
# Never probe command registers, passwords, EEPROM mirrors, unknown H groups.
EXCLUDED_ADDRESSES = frozenset((0x0000, 0x2000, 0x2005))


def read_targets(model: str) -> list[tuple[str, int]]:
    """Known, unambiguous F/U RAM addresses + documented status registers.

    Selection is NOT evidence that an address is supported by the device.
    """
    targets = [("state", 0x2100), ("status_bits", 0x2101),
               ("fault_code", 0x2102), ("warning_code", 0x2103)]
    seen = {address for _, address in targets}
    for entry in load_catalog(model):
        if (entry.ram is None or entry.duplicate or entry.conflict
                or entry.code == "F00.00" or not entry.code.startswith(("F", "U"))
                or entry.ram in EXCLUDED_ADDRESSES or entry.ram >= 0x8000):
            continue
        if entry.ram not in seen:
            targets.append((entry.code, entry.ram))
            seen.add(entry.ram)
    return targets


def _validate_targets(targets):
    if not targets or len(targets) > 4096:
        raise ValueError("scan requires 1..4096 explicitly curated targets")
    seen = set()
    for code, address in targets:
        if (not isinstance(code, str) or not code
                or not isinstance(address, int) or isinstance(address, bool)
                or address < 0 or address >= 0x8000
                or address in EXCLUDED_ADDRESSES or address in seen):
            raise ValueError(f"unsafe or duplicate scan target: {code} {address}")
        seen.add(address)


def _error_quality(exc):
    text = str(exc)
    match = re.search(r"Modbus exception 0x([0-9A-Fa-f]{2})", text)
    if match:
        return "exception_0x" + match.group(1).upper()
    if isinstance(exc, TimeoutError) or "did not answer" in text or "no response" in text:
        return "timeout"
    if "crc" in text.lower():
        return "crc_error"
    return "error"


def collect(client: A650Client, targets, *, delay_s: float = 0.1,
            stop_event: Event | None = None):
    """Yield each result after FC03 Count=1; stop between requests."""
    if delay_s < 0:
        raise ValueError("delay must not be negative")
    for code, address in targets:
        if stop_event is not None and stop_event.is_set():
            return
        request = ReadRegistersRequest(slave=getattr(client, 'slave', 1), address=address, count=1)
        started = time.monotonic()
        row = {"type": "reading", "timestamp": datetime.now(timezone.utc).isoformat(),
               "code": code, "address": f"0x{address:04X}", "function": 3,
               "count": 1, "request_hex": request.to_bytes().hex(" ").upper()}
        try:
            row["raw"] = client.read_registers(address, 1)[0]
            row["quality"] = "ok"
        except Exception as exc:
            row["quality"] = _error_quality(exc)
            row["error"] = str(exc)
        row["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
        yield row
        if delay_s:
            if stop_event is None:
                time.sleep(delay_s)
            else:
                stop_event.wait(delay_s)


def _fingerprint(targets):
    payload = json.dumps(targets, ensure_ascii=False, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _read_existing(path, *, model, slave, fingerprint, targets):
    with path.open("r", encoding="utf-8") as stream:
        lines = stream.readlines()
    if not lines or any(not line.endswith("\n") for line in lines):
        raise ValueError("incomplete scan file: cannot resume safely")
    records = [json.loads(line) for line in lines]
    head = records[0]
    if (head.get("type") != "session" or head.get("schema") != SCHEMA
            or head.get("model") != model or head.get("slave") != slave
            or head.get("targets_sha256") != fingerprint):
        raise ValueError("scan metadata does not match model, slave or register list")
    readings = records[1:]
    if len(readings) > len(targets):
        raise ValueError("scan file contains more results than targets")
    for (code, address), row in zip(targets, readings):
        if (row.get("type") != "reading" or row.get("code") != code
                or row.get("address") != f"0x{address:04X}"):
            raise ValueError("scan file contains unexpected or reordered results")
    return readings


def export_csv(path: Path):
    """Rebuild readable CSV deterministically from the canonical JSONL."""
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("type") == "reading":
                rows.append(row)
    destination = path.with_suffix(".csv")
    fields = ("timestamp", "code", "address", "function", "count",
              "raw", "quality", "elapsed_ms", "request_hex", "error")
    with destination.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return destination


def run_scan(client: A650Client, targets, output: Path | str, *,
             model: str, delay_s: float = 0.1, stop_event: Event | None = None,
             resume: bool = False, on_row=None):
    """Persist every response immediately; resume only matching immutable plans.

    One worker should own the client, with ALL other poll/read/write jobs paused.
    """
    targets = list(targets)
    _validate_targets(targets)
    if model not in ("A650", "A650M"):
        raise ValueError("unsupported model")
    if not 0.03 <= delay_s <= 2.0:
        raise ValueError("delay must be between 30 ms and 2 seconds")
    path = Path(output)
    digest = _fingerprint(targets)
    existing = _read_existing(path, model=model, slave=client.slave,
                              fingerprint=digest, targets=targets) if resume else []
    if resume and not path.exists():
        raise FileNotFoundError("no scan file to resume")
    if not resume and path.exists():
        raise FileExistsError("scan file already exists; use a new name or resume")
    header = {"type": "session", "schema": SCHEMA,
              "created_utc": datetime.now(timezone.utc).isoformat(),
              "model": model, "slave": client.slave, "read_only": True,
              "function": 3, "count": 1, "targets_sha256": digest,
              "planned": len(targets), "delay_ms": round(delay_s * 1000)}
    # Disable client timeout retries while scanning to keep each result distinct.
    previous_retries = client.retries
    client.retries = 0
    try:
        with path.open("a" if resume else "x", encoding="utf-8") as stream:
            if not resume:
                stream.write(json.dumps(header, ensure_ascii=False) + "\n")
                stream.flush()
            for row in collect(client, targets[len(existing):], delay_s=delay_s,
                               stop_event=stop_event):
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                if on_row is not None:
                    on_row(row)
    finally:
        client.retries = previous_retries
    csv_path = export_csv(path)
    n = len(existing)
    with path.open("r", encoding="utf-8") as stream:
        n = sum(json.loads(line).get("type") == "reading" for line in stream)
    return {"completed": n == len(targets), "scanned": n, "total": len(targets),
            "jsonl": str(path), "csv": str(csv_path)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="A650 read-only one-register Modbus scan")
    parser.add_argument("--port", required=True, help="Windows COM port e.g. COM3")
    parser.add_argument("--model", choices=("A650", "A650M"), required=True)
    parser.add_argument("--slave", type=int, default=1)
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--parity", choices=("N", "E", "O"), default="N")
    parser.add_argument("--stopbits", type=int, choices=(1, 2), default=1)
    parser.add_argument("--timeout", type=float, default=0.8)
    parser.add_argument("--delay-ms", type=int, default=100)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.slave <= 247:
        parser.error("slave must be 1..247")
    if not 0.1 <= args.timeout <= 10:
        parser.error("timeout must be 0.1..10 seconds")
    if not 30 <= args.delay_ms <= 2000:
        parser.error("delay-ms must be 30..2000")
    if args.output.suffix.lower() != ".jsonl":
        parser.error("output must end with .jsonl")
    if args.output.exists() and not args.resume:
        parser.error("output already exists; use --resume or a different file")
    transport = SerialTransport(args.port, baudrate=args.baud,
                                parity=args.parity, stopbits=args.stopbits)
    client = A650Client(transport, slave=args.slave, retries=0,
                        timeout_s=args.timeout)
    try:
        transport.open()
        report = run_scan(client, read_targets(args.model), args.output,
                          model=args.model, delay_s=args.delay_ms / 1000,
                          resume=args.resume,
                          on_row=lambda r: print(f'{r["code"]} {r["address"]}: '
                                                 f'{r.get("raw", r.get("error"))}'))
    finally:
        transport.close()
    print(f'{report["scanned"]}/{report["total"]} -> {report["jsonl"]} & {report["csv"]}')
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
