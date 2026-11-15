"""Versioned, offline-only project values; no transport or hardware operations."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import os
import tempfile


# Panel semantics for the initial vertical slice; not Modbus write metadata.
ENUMS = {'F15.01': {0: 'Нет чётности · 8N2', 1: 'Чётная · 8E1',
                    2: 'Нечётная · 8O1', 3: 'Нет чётности · 8N1'}}
DECIMALS = {'F13.01': (Decimal('0'), Decimal('100'), Decimal('0.1'))}


def validate(code, value):
    if code in ENUMS:
        if type(value) is not int or value not in ENUMS[code]:
            raise ValueError('Выберите допустимый вариант из списка')
        return value
    if code in DECIMALS:
        try:
            n = Decimal(str(value).strip().replace(',', '.'))
            low, high, step = DECIMALS[code]
            if not n.is_finite() or n < low or n > high or n % step:
                raise ValueError('Введите значение от 0,0 до 100,0 с шагом 0,1')
            return str(n.quantize(step))
        except InvalidOperation as exc:
            raise ValueError('Введите корректное число') from exc
    raise ValueError('Для параметра нет проверенного редактора')


@dataclass
class OfflineProject:
    model: str
    values: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.model not in ('A650', 'A650M'):
            raise ValueError('Неизвестная модель')
        if not isinstance(self.values, dict):
            raise ValueError('Некорректные параметры проекта')
        self.values = {code: validate(code, value) for code, value in self.values.items()}

    def set(self, code, value):
        self.values[code] = validate(code, value)

    def save(self, path):
        path = Path(path)
        payload = {'format': 'a650-offline-project', 'version': 1,
                   'model': self.model, 'values': self.values}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             delete=False, newline='\n') as output:
                temporary = output.name
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.write('\n')
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path):
        with Path(path).open('r', encoding='utf-8') as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or data.get('format') != 'a650-offline-project' or data.get('version') != 1:
            raise ValueError('Неподдерживаемый формат проекта')
        if not isinstance(data.get('values'), dict):
            raise ValueError('В проекте нет корректного списка параметров')
        return cls(data.get('model'), data['values'])
