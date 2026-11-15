"""Read-only research catalog, with source conflicts retained for inspection."""
from collections import Counter
from dataclasses import dataclass
from importlib.resources import files
import json

from .addresses import parameter_addresses


@dataclass(frozen=True)
class CatalogEntry:
    code: str
    group: str
    name: str
    default: str | None
    minimum: str | None
    maximum: str | None
    ram: int | None
    eeprom: int | None
    source_location: str
    duplicate: bool
    expected_ram: int | None
    expected_eeprom: int | None
    conflict: bool

    @property
    def writable(self) -> bool:
        # This research catalog does not grant write permissions.
        return False


def load_catalog(model: str) -> tuple[CatalogEntry, ...]:
    names = {'A650': 'catalog-a650.json', 'A650M': 'catalog-a650m.json'}
    if model not in names:
        raise ValueError('unsupported model')
    raw = json.loads(files('a650').joinpath('data', names[model]).read_text(encoding='utf-8'))
    counts = Counter(item['code'] for item in raw)
    result = []
    for item in raw:
        code = item['code']
        expected_ram = expected_eeprom = None
        conflict = False
        if not code.startswith('H'):
            expected_ram, expected_eeprom = parameter_addresses(code)
            conflict = (item.get('ram'), item.get('eeprom')) != (expected_ram, expected_eeprom)
        result.append(CatalogEntry(code, item['group'], item['name'], item.get('default'),
                                   item.get('minimum'), item.get('maximum'), item.get('ram'),
                                   item.get('eeprom'), item.get('code_va', ''), counts[code] > 1,
                                   expected_ram, expected_eeprom, conflict))
    return tuple(result)


def search_catalog(entries, query='', group='Все группы'):
    query = query.strip().casefold()
    return tuple(entry for entry in entries if (group == 'Все группы' or entry.group == group)
                 and (not query or query in entry.code.casefold() or query in entry.name.casefold()))
