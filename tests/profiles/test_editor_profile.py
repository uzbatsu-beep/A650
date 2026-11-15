import copy
from decimal import Decimal
from importlib.resources import files
import json
import pytest
from a650.a650lib.editor_profile import load_editor_profile, parse_profile, ProfileError
from a650.a650lib.offline_project import OfflineProject, validate


def profile_data(model='A650'):
    return json.loads(files('a650').joinpath('data', f'editors-{model.lower()}.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('model', ['A650', 'A650M'])
def test_bundled_profiles_are_immutable_and_match_catalog(model):
    from a650.a650lib.catalog import load_catalog
    profile = load_editor_profile(model)
    assert len(profile.enums) == 8 and len(profile.decimals) == 6
    assert set(profile.sources) <= {e.code for e in load_catalog(model)}
    assert profile.decimals['F13.01'] == (Decimal('0'), Decimal('100'), Decimal('0.1'))
    with pytest.raises(TypeError):
        profile.enums['F15.01'][0] = 'changed'
    with pytest.raises(TypeError):
        profile.sources['F15.01']['title'] = 'changed'


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(schema_version=2),
    lambda d: d.update(model='A650M'),
    lambda d: d.update(hardware_write_allowed=True),
    lambda d: d.update(revision=''),
    lambda d: d['parameters'].append(copy.deepcopy(d['parameters'][0])),
    lambda d: d['parameters'][0].update(kind='python'),
    lambda d: d['parameters'][0].update(source={}),
    lambda d: d['parameters'][0]['source'].update(pages=[True]),
    lambda d: d['parameters'][0]['options'].append(copy.deepcopy(d['parameters'][0]['options'][0])),
    lambda d: d['parameters'][0]['options'][0].update(label=''),
    lambda d: d['parameters'][0]['options'][0].update(code=True),
    lambda d: d['parameters'][-1].update(step='0'),
    lambda d: d['parameters'][-1].update(maximum='-1'),
    lambda d: d['parameters'][-1].update(step='NaN'),
    lambda d: d['parameters'][-1].update(minimum=0),
])
def test_malformed_profile_is_rejected(mutation):
    data = profile_data()
    mutation(data)
    with pytest.raises(ValueError):
        parse_profile(data, 'A650')


def test_model_specific_options_drive_validation(monkeypatch):
    import a650.a650lib.offline_project as module
    data = profile_data('A650M')
    data['parameters'][0]['options'] = [{'code': 42, 'label': 'Synthetic test option'}]
    extended = parse_profile(data, 'A650M')
    basic = load_editor_profile('A650')
    monkeypatch.setattr(module, 'load_editor_profile', lambda model: extended if model == 'A650M' else basic)
    assert validate('F01.01', 42, 'A650M') == 42
    with pytest.raises(ValueError):
        validate('F01.01', 42, 'A650')
    project = OfflineProject('A650M')
    project.set('F01.01', 42)
    assert project.values['F01.01'] == 42


def test_legacy_project_migrates_and_future_revision_is_not_silently_loaded(tmp_path):
    path = tmp_path / 'project.json'
    data = {'format': 'a650-offline-project', 'version': 1, 'model': 'A650',
            'values': {'F15.01': 1, 'F13.01': '50.0'}}
    path.write_text(json.dumps(data))
    project = OfflineProject.load(path)
    assert not project.dirty
    project.save(path)
    saved = json.loads(path.read_text())
    assert saved['editor_profile_revision'] == load_editor_profile('A650').revision
    assert saved['values'] == data['values']
    saved['editor_profile_revision'] = 'future-revision'
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='Ревизия'):
        OfflineProject.load(path)
