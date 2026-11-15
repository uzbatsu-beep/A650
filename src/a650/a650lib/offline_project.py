"""Versioned, offline-only project values; no transport or hardware operations."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import os
import tempfile


# Display choices transcribed from A650 edition 3; offline semantics only.
ENUMS = {
    'F01.01': {0: 'Цифровая уставка', 1: 'Потенциометр пульта', 2: 'Аналоговый вход AI1',
               3: 'Канал связи', 4: 'Ступенчатые скорости', 5: 'ПЛК', 6: 'Выход ПИД',
               7: 'Импульсный вход DI7/HI', 8: 'Аналоговый вход AI2', 9: 'Аналоговый вход AI3'},
    'F02.00': {0: 'Пульт управления', 1: 'Цифровые входы', 2: 'Канал связи'},
    'F02.12': {0: 'Останов с торможением', 1: 'Останов выбегом'},
    'F13.00': {0: 'Цифровая уставка F13.01', 1: 'Потенциометр пульта', 2: 'AI1',
               3: 'Канал связи', 4: 'Ступенчатые скорости', 5: 'Импульсный вход DI7/HI',
               6: 'AI2', 7: 'AI3'},
    'F15.00': {0: '4800 бод', 1: '9600 бод', 2: '19200 бод', 3: '38400 бод',
               4: '57600 бод', 5: '115200 бод'},
    'F15.01': {0: 'Нет чётности · 8N2', 1: 'Чётная · 8E1',
               2: 'Нечётная · 8O1', 3: 'Нет чётности · 8N1'},
    'F15.05': {0: 'Ведомый', 1: 'Ведущий'},
    'F15.06': {0: 'Заданная частота', 1: 'Текущая рабочая частота'},
}
DECIMALS = {
    'F01.08': (Decimal('20'), Decimal('600'), Decimal('0.01')),
    'F03.00': (Decimal('0'), Decimal('6000'), Decimal('0.1')),
    'F03.01': (Decimal('0'), Decimal('6000'), Decimal('0.1')),
    'F13.01': (Decimal('0'), Decimal('100'), Decimal('0.1')),
    'F15.03': (Decimal('0'), Decimal('60'), Decimal('0.1')),
    'F15.04': (Decimal('0'), Decimal('200'), Decimal('1')),
}
UNITS = {'F01.08': 'Гц', 'F03.00': 'с', 'F03.01': 'с', 'F13.01': '%',
         'F15.03': 'с', 'F15.04': 'мс'}


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
                raise ValueError(f'Введите значение от {low} до {high} с шагом {step}')
            return str(n.quantize(step))
        except InvalidOperation as exc:
            raise ValueError('Введите корректное число') from exc
    raise ValueError('Для параметра нет проверенного редактора')


@dataclass
class OfflineProject:
    model: str
    values: dict = field(default_factory=dict)
    _undo: list = field(default_factory=list, init=False, repr=False)
    _redo: list = field(default_factory=list, init=False, repr=False)
    _saved: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        if self.model not in ('A650', 'A650M'):
            raise ValueError('Неизвестная модель')
        if not isinstance(self.values, dict):
            raise ValueError('Некорректные параметры проекта')
        # Preserve unknown enum codes from projects for inspection and round-trip;
        # selecting a new value still goes through strict validation in set().
        checked = {}
        for code, value in self.values.items():
            if code in ENUMS and type(value) is int and -(2**31) <= value < 2**31:
                checked[code] = value
            else:
                checked[code] = validate(code, value)
        self.values = checked
        self._saved = checked.copy()

    @property
    def dirty(self):
        return self.values != self._saved

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def set(self, code, value):
        value = validate(code, value)
        if self.values.get(code) == value:
            return
        self._undo.append(self.values.copy())
        self._redo.clear()
        self.values[code] = value

    def undo(self):
        if self._undo:
            self._redo.append(self.values.copy())
            self.values = self._undo.pop()

    def redo(self):
        if self._redo:
            self._undo.append(self.values.copy())
            self.values = self._redo.pop()

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
            self._saved = self.values.copy()
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
