"""Safety guard implementing docs/SAFETY.md rules for write operations.

Defaults: read-only mode ON; writes require explicit enablement plus a
whitelist of writable addresses; every write must be logged (audit hook).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("a650.audit")


class WriteDenied(RuntimeError):
    pass


@dataclass
class SafetyGuard:
    read_only: bool = True
    writable_addresses: set[int] = field(default_factory=set)
    allow_broadcast_writes: bool = False  # manual does not confirm broadcast safety

    def enable_writes(self, addresses: set[int]) -> None:
        """Explicitly open writes for a known address whitelist."""
        self.read_only = False
        self.writable_addresses = set(addresses)

    def check_write(self, slave: int, address: int, value: int) -> None:
        if self.read_only:
            raise WriteDenied("read-only mode: call enable_writes() first")
        if slave == 0 and not self.allow_broadcast_writes:
            raise WriteDenied("broadcast (slave 0) writes are disabled")
        if address not in self.writable_addresses:
            raise WriteDenied(f"address {address:#06x} not in writable whitelist")
        logger.info("AUDIT write slave=%d addr=%#06x value=%d", slave, address, value)

    def check_read(self, slave: int, address: int) -> None:
        logger.info("AUDIT read slave=%d addr=%#06x", slave, address)
