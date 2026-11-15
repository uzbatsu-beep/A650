"""Import candidates from synthetic profiles; no vendor-export compatibility claim."""
import pytest

from a650.a650lib.studio_import import preview_studio_profile
from a650.a650lib.studio_profile import StudioProfile


def profile(values=None, read=None, checked=(), model='A650'):
    return StudioProfile(f'ПЧ ONI {model}', {'Port': 'COM17', 'Baud': '3'},
                         values or {}, read or {}, frozenset(checked))


@pytest.mark.parametrize('model', ['A650', 'A650M'])
def test_only_known_enum_set_becomes_an_import_candidate(model):
    source = profile({'F15.01': 0, 'F02.00': 9, 'F13.01': 500, 'F99.99': 1},
                     {'F15.01': 2, 'F15.05': 1}, checked=['F15.01', 'F15.06'], model=model)
    rows = {row.code: row for row in preview_studio_profile(source, model)}
    assert {code: row.import_value for code, row in rows.items() if row.importable} == {'F15.01': 0}
    assert rows['F15.01'].set_value == 0 and rows['F15.01'].read_value == 2
    assert rows['F15.01'].checked_in_source
    assert 'Неизвестный код' in rows['F02.00'].reason
    assert 'преобразования' in rows['F13.01'].reason
    assert 'не найден' in rows['F99.99'].reason
    # Read and Check are informational; neither substitutes a missing Set value.
    assert rows['F15.05'].set_value is None and rows['F15.05'].read_value == 1
    assert rows['F15.06'].set_value is None and rows['F15.06'].checked_in_source
    assert source.parameter_set['F13.01'] == 500


def test_ambiguous_and_conflicting_parameters_remain_visible_but_blocked():
    rows = {row.code: row for row in preview_studio_profile(
        profile({'F17.28': 0, 'F18.08': 0}, model='A650M'), 'A650M')}
    assert set(rows) == {'F17.28', 'F18.08'}
    assert all(not row.importable for row in rows.values())
    assert 'дубликат' in rows['F17.28'].reason
    assert 'Конфликт' in rows['F18.08'].reason


@pytest.mark.parametrize('code', ['F00.00', 'F00.19', 'F00.24'])
def test_password_values_are_redacted_before_reaching_the_gui(code):
    row, = preview_studio_profile(profile({code: 123456}, {code: 654321}, [code]), 'A650')
    assert row.sensitive and not row.importable
    assert row.set_value is None and row.read_value is None and row.import_value is None
    assert '123456' not in repr(row) and '654321' not in repr(row)


def test_model_mismatch_rejected_without_reinterpreting_codes():
    with pytest.raises(ValueError, match='Модель'):
        preview_studio_profile(profile({'F15.01': 0}, model='A650M'), 'A650')


def test_sparse_empty_profile_does_not_create_defaults():
    assert preview_studio_profile(profile(), 'A650') == ()
