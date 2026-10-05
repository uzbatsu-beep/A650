"""A650 register map loaded from data/registers.csv.

Design rule (docs/ARCHITECTURE.md): no hard-coded magic addresses in business
logic — everything comes from the CSV, including confidence flags.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_DATA = REPO_ROOT / "data"

# Data shipped inside the package (used when running as a frozen binary or an
# installed wheel, where the repo-level data/ directory is not present).
import sys as _sys
_MEIPASS = getattr(_sys, "_MEIPASS", None)
if _MEIPASS:
    # Frozen single-file build: datas are unpacked to <_MEIPASS>/a650/data.
    PKG_DATA = Path(_MEIPASS) / "a650" / "data"
else:
    PKG_DATA = Path(__file__).resolve().parent.parent / "data"


def default_data_path(name: str) -> Path:
    """Resolve a bundled data file: repo data/ first, then packaged copy."""
    for base in (REPO_DATA, PKG_DATA):
        p = base / name
        if p.exists():
            return p
    raise FileNotFoundError(f"{name} not found in {REPO_DATA} or {PKG_DATA}")


@dataclass(frozen=True)
class RegisterDef:
    address: int
    name: str
    access: str            # R | RW | R? (unconfirmed)
    data_type: str
    scale: Decimal
    unit: str
    min_raw: int | None
    max_raw: int | None
    enum_or_bits: str
    source: str
    confidence: str        # low | medium | high
    verified_on_device: bool
    notes: str

    def to_engineering(self, raw: int) -> Decimal:
        return Decimal(raw) * self.scale

    def to_raw(self, engineering: Decimal | float | int) -> int:
        value = int((Decimal(str(engineering)) / self.scale).to_integral_value())
        if self.min_raw is not None and value < self.min_raw:
            raise ValueError(f"{value} below min for {self.name}")
        if self.max_raw is not None and value > self.max_raw:
            raise ValueError(f"{value} above max for {self.name}")
        return value


class RegisterMap:
    def __init__(self, registers: dict[int, RegisterDef]):
        self._by_address = registers

    @classmethod
    def empty(cls) -> "RegisterMap":
        """A map with no entries (used by GUI/tests that tolerate missing data)."""
        return cls({})

    @classmethod
    def load(cls, path: Path | str | None = None) -> "RegisterMap":
        p = Path(path) if path else default_data_path("registers.csv")
        regs: dict[int, RegisterDef] = {}
        with p.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                addr = int(row["address_dec"])
                if addr in regs:
                    raise ValueError(f"duplicate register address {addr}")
                regs[addr] = RegisterDef(
                    address=addr,
                    name=row["name"],
                    access=row["access"],
                    data_type=row["data_type"],
                    scale=Decimal(row["scale"]),
                    unit=row["unit"],
                    min_raw=int(row["min_raw"]) if row["min_raw"] else None,
                    max_raw=int(row["max_raw"]) if row["max_raw"] else None,
                    enum_or_bits=row["enum_or_bits"],
                    source=row["source"],
                    confidence=row["confidence"],
                    verified_on_device=row["verified_on_device"].strip().lower() == "yes",
                    notes=row["notes"],
                )
        return cls(regs)

    def get(self, address: int) -> RegisterDef:
        try:
            return self._by_address[address]
        except KeyError:
            raise KeyError(f"register {address:#06x} not in map") from None

    def by_name(self, name_substr: str) -> list[RegisterDef]:
        needle = name_substr.lower()
        return [r for a, r in sorted(self._by_address.items()) if needle in r.name.lower()]

    def addresses(self) -> list[int]:
        return sorted(self._by_address)
