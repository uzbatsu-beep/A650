"""Verify release payload identity and runnable demonstration data."""
import hashlib
import json
from pathlib import Path
import runpy
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from a650 import __version__
from a650.a650lib.offline_project import OfflineProject, validate
from a650.a650lib.studio_import import preview_studio_profile
from a650.a650lib.studio_profile import read_studio_profile
from a650.cli import main


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = runpy.run_path(str(ROOT / 'packaging' / 'package_preview.py'))


def test_cli_reports_the_release_version(capsys):
    with pytest.raises(SystemExit) as stopped:
        main(['--version'])
    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == f'a650 {__version__}'


def test_archive_contains_launcher_examples_provenance_and_correct_checksums(tmp_path, monkeypatch):
    binary = tmp_path / 'a650.exe'
    binary.write_bytes(b'MZ-synthetic-test-not-an-executable')
    monkeypatch.setattr(PACKAGE['subprocess'], 'run',
                        lambda *args, **kwargs: SimpleNamespace(stdout=f'a650 {__version__}\n'))
    commit = 'a' * 40
    tag = f'preview-{__version__}'
    archive, checksum = PACKAGE['package_preview'](binary, tmp_path / 'output', commit, tag)
    assert checksum.read_text().strip() == f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}'
    with ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {
            'a650.exe', 'start-preview.cmd', 'README-ru.md', 'RELEASE-NOTES-ru.md', 'BUILD-INFO.json',
            'examples/demo.a650.json', 'examples/comparison.a650.json', 'examples/synthetic-oni-profile.ods'}
        assert bundle.read('a650.exe') == binary.read_bytes()
        info = json.loads(bundle.read('BUILD-INFO.json'))
        assert info == {'version': __version__, 'commit': commit, 'source_ref': tag,
                        'platform': 'windows-x86_64', 'executable': 'a650.exe',
                        'executable_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
        assert '--simulate gui' in bundle.read('start-preview.cmd').decode()


@pytest.mark.parametrize('commit,tag,executable_version', [
    ('short', f'preview-{__version__}', __version__),
    ('a' * 40, 'preview-wrong-version', __version__),
    ('a' * 40, f'preview-{__version__}', '0.0.1'),
])
def test_inconsistent_release_identity_is_rejected_before_packaging(
        tmp_path, monkeypatch, commit, tag, executable_version):
    monkeypatch.setattr(PACKAGE['subprocess'], 'run',
                        lambda *args, **kwargs: SimpleNamespace(stdout=f'a650 {executable_version}\n'))
    output = tmp_path / 'output'
    with pytest.raises(ValueError):
        PACKAGE['package_preview'](tmp_path / 'a650.exe', output, commit, tag)
    assert not output.exists()


def test_demo_projects_support_edit_compare_merge_and_undo():
    examples = ROOT / 'packaging' / 'preview' / 'examples'
    project = OfflineProject.load(examples / 'demo.a650.json')
    sample = OfflineProject.load(examples / 'comparison.a650.json')
    for source in (project, sample):
        for code, value in source.values.items():
            assert validate(code, value, source.model) == value
    original = dict(project.values)
    differences = {code for code in set(project.values) | set(sample.values)
                   if project.values.get(code) != sample.values.get(code)}
    assert {'F15.01', 'F13.01', 'F15.06'} <= differences
    project.apply_changes({code: sample.values[code] for code in differences if code in sample.values})
    project.undo()
    assert project.values == original and not project.dirty
    rows = preview_studio_profile(read_studio_profile(examples / 'synthetic-oni-profile.ods'), project.model)
    assert {row.code: row.import_value for row in rows if row.importable} == {
        'F01.01': 3, 'F15.01': 2, 'F15.05': 0}
    assert next(row for row in rows if row.code == 'F13.01').import_value is None
