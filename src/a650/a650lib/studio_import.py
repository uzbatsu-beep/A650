"""Conservative ODS preview. Only known, dimensionless enum codes can be copied.

No numeric raw-to-engineering conversion and no hardware/connection operations.
"""
from collections import Counter
from dataclasses import dataclass
from .catalog import load_catalog
from .editor_profile import load_editor_profile
from .offline_project import validate


@dataclass(frozen=True)
class ImportRow:
    code: str
    name: str
    set_value: int | None
    read_value: int | None
    checked_in_source: bool
    import_value: int | None
    reason: str
    sensitive: bool = False

    @property
    def importable(self):
        return self.import_value is not None and not self.sensitive


def preview_studio_profile(source, model):
    if source.model != f'ПЧ ONI {model}':
        raise ValueError('Модель ODS не совпадает с текущим проектом')
    entries = load_catalog(model)
    counts = Counter(e.code for e in entries)
    by_code = {entry.code: entry for entry in entries}
    profile = load_editor_profile(model)
    result = []
    for code in sorted(set(source.parameter_set) | set(source.parameter_read) | set(source.checked)):
        entry = by_code.get(code)
        name = entry.name if entry else 'Неизвестный параметр'
        sensitive = code == 'F00.00' or 'парол' in name.casefold() or 'password' in name.casefold()
        raw_set = source.parameter_set.get(code)
        raw_read = source.parameter_read.get(code)
        value = None
        if sensitive:
            reason = 'Секретное значение скрыто; перенос запрещён'
        elif counts[code] > 1:
            reason = 'Код неоднозначен: дубликат в каталоге'
        elif entry is None:
            reason = 'Параметр не найден в каталоге выбранной модели'
        elif entry.conflict:
            reason = 'Конфликт адресов в источниках'
        elif raw_set is None:
            reason = 'В секции Parameter Set нет значения'
        elif code not in profile.enums:
            reason = 'Нет подтверждённого преобразования из целого ODS'
        else:
            try:
                value = validate(code, raw_set, model)
                reason = 'Код enum можно перенести только в офлайн-проект'
            except ValueError:
                reason = 'Неизвестный код enum'
        result.append(ImportRow(code, name, None if sensitive else raw_set,
                                None if sensitive else raw_read, code in source.checked,
                                value, reason, sensitive))
    return tuple(result)
