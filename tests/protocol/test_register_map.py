"""Tests for the CSV-driven register map and scaling."""
from decimal import Decimal

import pytest

from a650.a650lib.register_map import RegisterMap


@pytest.fixture(scope="module")
def rmap() -> RegisterMap:
    return RegisterMap.load()


def test_loads_all_rows(rmap):
    assert len(rmap.addresses()) == 8
    assert 0x3000 in rmap.addresses()


def test_frequency_scaling(rmap):
    reg = rmap.get(0x3000)
    assert reg.to_engineering(5000) == Decimal("50.00")
    assert reg.to_raw(Decimal("30.00")) == 3000


def test_setpoint_limits(rmap):
    reg = rmap.get(0x2001)
    assert reg.to_raw(Decimal("100.00")) == 10000
    with pytest.raises(ValueError):
        reg.to_raw(Decimal("101.00"))


def test_confidence_flags_present(rmap):
    # Flags must match data/registers.csv: 0x2001 comes from a CRC-verified
    # manual example (high); 0x2000 has an incomplete bit map (medium);
    # 0x2005 has unconfirmed access direction (low).
    assert rmap.get(0x2001).confidence == "high"
    assert rmap.get(0x2000).confidence == "medium"
    assert rmap.get(0x2005).confidence == "low"


def test_unknown_address(rmap):
    with pytest.raises(KeyError):
        rmap.get(0x9999)
