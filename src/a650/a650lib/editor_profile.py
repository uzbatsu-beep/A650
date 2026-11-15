"""Validated, immutable display metadata. Never grants hardware permissions."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib.resources import files
import json
import re
from types import MappingProxyType
from typing import Mapping
from .addresses import parameter_addresses


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class EditorProfile:
    model: str
    revision: str
    enums: Mapping
    decimals: Mapping
    units: Mapping
    sources: Mapping
    notes: Mapping


def parse_profile(data, expected_model):
    """Reject malformed metadata before it can configure any editor."""
    def require(condition, message):
        if not condition:
            raise ProfileError(message)

    require(expected_model in ('A650', 'A650M'), 'Неизвестная модель профиля')
    require(isinstance(data, dict), 'Профиль должен быть объектом')
    require(data.get('format') == 'a650-editor-profile' and type(data.get('schema_version')) is int
            and data['schema_version'] == 1, 'Неподдерживаемая схема редакторов')
    require(data.get('model') == expected_model, 'Модель профиля не совпадает')
    require(isinstance(data.get('revision'), str) and bool(data['revision'].strip()), 'Нет ревизии профиля')
    require(data.get('hardware_write_allowed') is False, 'Профиль редакторов не может разрешать запись в ПЧ')
    require(isinstance(data.get('parameters'), list) and bool(data['parameters']), 'Нет параметров профиля')
    enums, decimals, units, sources, notes = {}, {}, {}, {}, {}
    for item in data['parameters']:
        require(isinstance(item, dict), 'Некорректное описание параметра')
        code = item.get('code')
        require(isinstance(code, str) and re.fullmatch(r'[FHU][0-9]{2}\.[0-9]{2}', code), 'Некорректный код параметра')
        if code.startswith('H'):
            require(code.startswith('H00.'), 'Неизвестная группа H')
        else:
            parameter_addresses(code)
        require(code not in sources, f'{code}: код повторяется')
        source = item.get('source')
        require(isinstance(source, dict) and all(isinstance(source.get(k), str) and source[k].strip()
                for k in ('document', 'title')), f'{code}: нет источника')
        require(type(source.get('edition')) is int and source['edition'] > 0, f'{code}: нет редакции источника')
        pages = source.get('pages')
        require(isinstance(pages, list) and bool(pages) and all(type(p) is int and p > 0 for p in pages), f'{code}: некорректные страницы')
        sources[code] = MappingProxyType({k: source[k] for k in ('document', 'title', 'edition')} | {'pages': tuple(pages)})
        note = item.get('notes', [])
        require(isinstance(note, list) and all(isinstance(n, str) for n in note), f'{code}: некорректные примечания')
        notes[code] = tuple(note)
        if item.get('kind') == 'enum':
            options = item.get('options')
            require(isinstance(options, list) and bool(options), f'{code}: нет вариантов enum')
            values = {}
            for option in options:
                require(isinstance(option, dict), f'{code}: некорректный вариант')
                value, label = option.get('code'), option.get('label')
                require(type(value) is int and 0 <= value <= 65535 and value not in values, f'{code}: некорректный/повторный код enum')
                require(isinstance(label, str) and bool(label.strip()), f'{code}: пустое название enum')
                values[value] = label
            enums[code] = MappingProxyType(values)
        elif item.get('kind') == 'decimal':
            try:
                require(all(isinstance(item.get(k), str) for k in ('minimum', 'maximum', 'step')), f'{code}: числа должны быть десятичными строками')
                low, high, step = (Decimal(item[k]) for k in ('minimum', 'maximum', 'step'))
                require(all(n.is_finite() for n in (low, high, step)), f'{code}: нечисловой диапазон')
                require(low <= high and step > 0 and step.normalize().as_tuple().digits == (1,)
                        and -9 <= step.as_tuple().exponent <= 0 and low % step == 0 and high % step == 0,
                        f'{code}: некорректный диапазон или шаг')
            except InvalidOperation as exc:
                raise ProfileError(f'{code}: некорректное десятичное число') from exc
            require(isinstance(item.get('unit'), str) and bool(item['unit'].strip()), f'{code}: нет единицы')
            decimals[code] = (low, high, step)
            units[code] = item['unit']
        else:
            raise ProfileError(f'{code}: неизвестный тип редактора')
    return EditorProfile(expected_model, data['revision'], *(MappingProxyType(d)
                         for d in (enums, decimals, units, sources, notes)))


@lru_cache(maxsize=2)
def load_editor_profile(model):
    if model not in ('A650', 'A650M'):
        raise ProfileError('Неизвестная модель')
    resource = files('a650').joinpath('data', f'editors-{model.lower()}.json')
    try:
        data = json.loads(resource.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ProfileError('Не удалось загрузить профиль редакторов') from exc
    return parse_profile(data, model)
