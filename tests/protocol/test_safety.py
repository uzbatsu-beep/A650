"""Tests for SafetyGuard defaults (docs/SAFETY.md)."""
import pytest

from a650.a650lib.safety import SafetyGuard, WriteDenied


def test_default_is_read_only():
    g = SafetyGuard()
    with pytest.raises(WriteDenied):
        g.check_write(slave=1, address=0x2000, value=1)


def test_whitelist_required():
    g = SafetyGuard()
    g.enable_writes({0x2001})
    g.check_write(slave=1, address=0x2001, value=3000)  # ok
    with pytest.raises(WriteDenied):
        g.check_write(slave=1, address=0x2000, value=1)  # not whitelisted


def test_broadcast_write_blocked_by_default():
    g = SafetyGuard()
    g.enable_writes({0x2001})
    with pytest.raises(WriteDenied, match="broadcast"):
        g.check_write(slave=0, address=0x2001, value=3000)
