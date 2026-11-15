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


def test_malformed_project_does_not_load(tmp_path):
    path = tmp_path / 'profile.json'
    path.write_text('{"format":"a650-offline-project","version":1,"model":"A650","values":{"F15.01":9}}')
    with pytest.raises(ValueError):
        OfflineProject.load(path)
