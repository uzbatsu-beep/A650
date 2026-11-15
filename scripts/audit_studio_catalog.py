"""Read-only audit of extracted OniDriveStudio F/U address records.

Usage: python scripts/audit_studio_catalog.py docs/research/oni-studio-a650m-extracted.json
Exit 1 means findings; exit 2 means invalid input. No corrections are applied.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from a650.a650lib.addresses import parameter_addresses


def audit(records):
    codes = defaultdict(list)
    findings = []
    for index, record in enumerate(records):
        code = record['code']
        codes[code].append(index)
        if code.startswith('H'):
            continue  # H addressing is not specified in the supplied appendix.
        ram, eeprom = parameter_addresses(code)
        # The extractor uses None for absence; don't treat a sentinel as an address.
        expected = {'ram': ram, 'eeprom': eeprom}
        actual = {field: record.get(field) for field in expected}
        if actual != expected:
            findings.append({'kind': 'address_mismatch', 'code': code,
                             'record_index': index, 'code_va': record.get('code_va'),
                             'actual': actual, 'expected': expected})
    for code, indices in codes.items():
        if len(indices) > 1:
            findings.append({'kind': 'duplicate_code', 'code': code,
                             'record_indices': indices})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog', type=Path)
    args = parser.parse_args()
    try:
        records = json.loads(args.catalog.read_text(encoding='utf-8'))
        if not isinstance(records, list):
            raise ValueError('catalog must be a list')
        findings = audit(records)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.error(str(exc))
    print(json.dumps({'catalog': args.catalog.name, 'records': len(records),
                      'unique_codes': len({r['code'] for r in records}),
                      'findings': findings}, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
