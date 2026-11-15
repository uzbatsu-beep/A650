"""Audit must flag manufacturer mistakes without modifying source records."""
import copy
from pathlib import Path
import runpy

import pytest

_audit = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/audit_studio_catalog.py'))['audit']


def test_detects_f18_shift_and_preserves_evidence():
    rows = [{'code': 'F18.08', 'ram': 0x1206, 'eeprom': 0x9206}]
    original = copy.deepcopy(rows)
    findings = _audit(rows)
    assert findings[0]['expected'] == {'ram': 0x1208, 'eeprom': 0x9208}
    assert findings[0]['actual'] == {'ram': 0x1206, 'eeprom': 0x9206}
    assert rows == original


def test_duplicate_code_is_not_silently_overwritten():
    rows = [{'code': 'F17.28', 'ram': 0x111C, 'eeprom': 0x911C},
            {'code': 'F17.28', 'ram': 0x111D, 'eeprom': 0x911D}]
    findings = _audit(rows)
    duplicate = next(x for x in findings if x['kind'] == 'duplicate_code')
    assert duplicate['record_indices'] == [0, 1]
    assert len(findings) == 2


@pytest.mark.parametrize('row', [
    {'code': 'F15.02', 'ram': 0x0F02, 'eeprom': 0x8F02},
    {'code': 'U00.00', 'ram': 0x3000, 'eeprom': None},
    {'code': 'H00.13', 'ram': 0x400D, 'eeprom': 0xC00D},
])
def test_matching_addresses_and_h_not_guessed(row):
    assert _audit([row]) == []
