from decimal import Decimal
import json
import pytest
from a650.a650lib.offline_project import OfflineProject, validate


def test_typed_project_roundtrip(tmp_path):
    project = OfflineProject('A650')
    project.set('F15.01', 1)
    project.set('F13.01', '50,0')
    path = tmp_path / 'profile.a650.json'
    project.save(path)
    restored = OfflineProject.load(path)
    assert restored.model == 'A650'
    assert restored.values == {'F15.01': 1, 'F13.01': '50.0'}
    assert json.loads(path.read_text())['values']['F15.01'] == 1


@pytest.mark.parametrize('code,value', [('F15.01', 9), ('F15.01', '1'),
    ('F13.01', '100.1'), ('F13.01', '50.05'), ('F13.01', 'NaN'),
    ('F13.01', 'Infinity'), ('F18.08', 1)])
def test_invalid_value_never_changes_project(code, value):
    project = OfflineProject('A650M')
    with pytest.raises(ValueError):
        project.set(code, value)
    assert not project.values


def test_unknown_enum_is_preserved_without_permitting_new_invalid_value(tmp_path):
    path = tmp_path / 'profile.json'
    path.write_text('{"format":"a650-offline-project","version":1,"model":"A650","values":{"F15.01":9}}')
    project = OfflineProject.load(path)
    assert project.values["F15.01"] == 9
    with pytest.raises(ValueError):
        project.set("F15.01", 9)
    project.save(path)
    assert OfflineProject.load(path).values["F15.01"] == 9


@pytest.mark.parametrize('code,value,expected', [
    ('F01.01', 6, 6), ('F02.00', 2, 2), ('F02.12', 1, 1),
    ('F13.00', 7, 7), ('F15.00', 5, 5), ('F15.05', 0, 0),
    ('F15.06', 1, 1), ('F01.08', '50,00', '50.00'),
    ('F03.00', '15,0', '15.0'), ('F03.01', '6000', '6000.0'),
    ('F15.03', '60,0', '60.0'), ('F15.04', '200', '200'),
])
def test_verified_offline_values(code, value, expected):
    assert validate(code, value) == expected


@pytest.mark.parametrize('code,value', [
    ('F01.01', 10), ('F02.00', 3), ('F02.12', 2), ('F13.00', 8),
    ('F15.00', 6), ('F15.05', 2), ('F15.06', 2),
    ('F01.08', '19.99'), ('F03.00', '6000.1'), ('F15.03', '-0.1'),
    ('F15.04', '1.5'),
])
def test_rejects_out_of_range_values(code, value):
    with pytest.raises(ValueError):
        validate(code, value)


def test_history_tracks_saved_point_and_preserves_unknown_enum(tmp_path):
    project = OfflineProject('A650', {'F15.01': 9})
    assert not project.dirty
    project.set('F15.01', 1)
    assert project.dirty and project.can_undo
    project.undo()
    assert project.values['F15.01'] == 9 and not project.dirty
    project.redo()
    path = tmp_path / 'saved.json'
    project.save(path)
    assert not project.dirty
    project.undo()
    assert project.dirty and project.values['F15.01'] == 9
    project.redo()
    assert not project.dirty


def test_noop_and_invalid_edit_do_not_destroy_redo():
    project = OfflineProject('A650')
    project.set('F15.01', 1)
    project.set('F15.01', 2)
    project.undo()
    project.set('F15.01', 1)
    with pytest.raises(ValueError):
        project.set('F15.01', 100)
    assert project.can_redo
    project.set('F15.01', 3)
    assert not project.can_redo


def test_failed_atomic_save_keeps_dirty_and_original_file(tmp_path, monkeypatch):
    import a650.a650lib.offline_project as module
    project = OfflineProject('A650')
    path = tmp_path / 'project.json'
    project.save(path)
    original = path.read_bytes()
    project.set('F15.01', 1)
    def fail(*args):
        raise OSError('disk unavailable')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError):
        project.save(path)
    assert project.dirty and path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_batch_changes_are_atomic_and_one_undo_step():
    project = OfflineProject('A650', {'F15.01': 9, 'F13.01': '20.0'})
    project.apply_changes({'F15.01': 1, 'F13.01': None, 'F03.00': '15.0'})
    assert project.values == {'F15.01': 1, 'F03.00': '15.0'}
    project.undo()
    assert project.values == {'F15.01': 9, 'F13.01': '20.0'}
    assert not project.dirty
    assert not project.can_undo
    project.redo()
    assert project.values == {'F15.01': 1, 'F03.00': '15.0'}
    before = project.values.copy()
    with pytest.raises(ValueError):
        project.apply_changes({'F15.01': 2, 'F03.00': '6001.0'})
    assert project.values == before


def test_removal_is_not_zero_and_missing_removal_does_not_change_history(tmp_path):
    project = OfflineProject('A650', {'F15.01': 0})
    project.apply_changes({'F15.01': None})
    assert 'F15.01' not in project.values
    project.apply_changes({'F15.01': None})
    project.undo()
    assert project.values['F15.01'] == 0 and not project.can_undo
    path = tmp_path / 'profile.json'
    project.apply_changes({'F15.01': None})
    project.save(path)
    assert OfflineProject.load(path).values == {}
