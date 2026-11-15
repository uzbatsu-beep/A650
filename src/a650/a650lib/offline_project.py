"""Versioned, offline-only project values; no transport or hardware operations."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import os
import tempfile


from .editor_profile import load_editor_profile


def validate(code, value, model="A650"):
    profile = load_editor_profile(model)
    if code in profile.enums:
        if type(value) is not int or value not in profile.enums[code]:
            raise ValueError('Выберите допустимый вариант из списка')
        return value
    if code in profile.decimals:
        try:
            n = Decimal(str(value).strip().replace(',', '.'))
            low, high, step = profile.decimals[code]
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
        profile = load_editor_profile(self.model)
        checked = {}
        for code, value in self.values.items():
            if code in profile.enums and type(value) is int and -(2**31) <= value < 2**31:
                checked[code] = value
            else:
                checked[code] = validate(code, value, self.model)
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
        self.apply_changes({code: validate(code, value, self.model)})

    def apply_changes(self, changes):
        """Validate a whole local change set before changing anything.

        None removes a local value; it never means writing zero to a device.
        A batch is one undo step, including removal of unknown loaded enums.
        """
        profile = load_editor_profile(self.model)
        updated = self.values.copy()
        for code, value in changes.items():
            if code not in profile.enums and code not in profile.decimals:
                raise ValueError('Для параметра нет проверенного редактора')
            if value is None:
                updated.pop(code, None)
            else:
                updated[code] = validate(code, value, self.model)
        if updated == self.values:
            return
        self._undo.append(self.values.copy())
        self._redo.clear()
        self.values = updated

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
                   'model': self.model, 'values': self.values,
                   'editor_profile_revision': load_editor_profile(self.model).revision}
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
        profile = load_editor_profile(data.get('model'))
        revision = data.get('editor_profile_revision')
        if revision is not None and revision != profile.revision:
            raise ValueError('Ревизия редакторов проекта не поддерживается')
        return cls(data.get('model'), data['values'])
