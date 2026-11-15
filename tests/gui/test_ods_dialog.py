"""Exercise actual ODS dialog and project merge using synthetic INI files."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QMessageBox

from a650.a650lib.studio_import import preview_studio_profile
from a650.a650lib.studio_profile import StudioProfile
from a650.gui.catalog import CatalogView
from a650.gui.studio_import import StudioImportDialog


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def rows():
    source = StudioProfile('ПЧ ONI A650', {},
                           {'F15.01': 0, 'F15.05': 1, 'F13.01': 500, 'F00.00': 123456},
                           {'F15.01': 2, 'F00.00': 654321}, frozenset(['F15.01']))
    return preview_studio_profile(source, 'A650')


def select(dialog, code):
    index = next(i for i, row in enumerate(dialog.rows) if row.code == code)
    dialog.table.item(index, 0).setCheckState(Qt.CheckState.Checked)


def test_preview_requires_explicit_selection_shows_labels_and_redacts_passwords(app):
    dialog = StudioImportDialog(rows(), 'A650', project_values={'F15.01': 1, 'F00.00': 112233})
    try:
        assert not dialog.selected_changes()
        assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
        index = next(i for i, row in enumerate(dialog.rows) if row.code == 'F15.01')
        assert 'Чётная' in dialog.table.item(index, 3).text()
        assert dialog.table.item(index, 4).text() == '0'
        assert dialog.table.item(index, 5).text() == '2'
        assert dialog.table.item(index, 6).text() == 'Да'
        assert 'Нет чётности' in dialog.table.item(index, 7).text()
        assert 'Заменит' in dialog.table.item(index, 7).text()
        for i, row in enumerate(dialog.rows):
            if not row.importable:
                assert not dialog.table.item(i, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable
        displayed = ' '.join(dialog.table.item(i, j).text() + dialog.table.item(i, j).toolTip()
                             for i in range(dialog.table.rowCount()) for j in range(dialog.table.columnCount()))
        assert all(secret not in displayed for secret in ['123456', '654321', '112233'])
        select(dialog, 'F15.01')
        assert dialog.selected_changes() == {'F15.01': 0}
        assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
        assert 'Заменят значения проекта: 1' in dialog.summary.text()
        # Even a programmatically checked blocked row cannot enter the merge.
        select(dialog, 'F13.01')
        assert dialog.selected_changes() == {'F15.01': 0}
    finally:
        dialog.close()


def ods_path(tmp_path, model='A650'):
    path = tmp_path / 'профиль.ods'
    path.write_text(f'[General]\nModel=ПЧ ONI {model}\nPort=COM17\nBaud=3\n'
                    '[Parameter Set]\nF15.01=0\nF15.05=1\nF13.01=500\n'
                    '[Parameter Read]\nF15.01=2\n[Check Parameter]\nF15.01=1\n', encoding='utf-8-sig')
    return path


@pytest.mark.parametrize('accepted', [True, False])
def test_import_merges_only_selected_set_as_one_undo_and_cancel_preserves_project(
        app, tmp_path, monkeypatch, accepted):
    view = CatalogView()
    try:
        project = view.projects['A650']
        project.set('F15.01', 1)
        project.set('F03.00', '10.0')
        before = dict(project.values)
        # Opening an import must never promote file Read to a device observation.
        view.observed = {'F15.01': {'value': 3, 'stale': True, 'stamp': '12:00:00', 'time': 0}}
        observed_before = {key: dict(value) for key, value in view.observed.items()}
        requests = []
        view.readRequested.connect(lambda *args: requests.append(args))
        path = ods_path(tmp_path)
        monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))

        def preview(dialog):
            assert dialog.project_values == before
            assert not dialog.selected_changes()
            select(dialog, 'F15.01')
            select(dialog, 'F15.05')
            assert project.values == before
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

        monkeypatch.setattr(StudioImportDialog, 'exec', preview)
        view.import_ods_button.click()
        assert not requests and view.observed == observed_before
        assert view.projects['A650M'].values == {}
        if accepted:
            assert project.values == {'F15.01': 0, 'F15.05': 1, 'F03.00': '10.0'}
            assert 'A650' in view.unsaved
            view.undo_button.click()
            assert project.values == before
            view.redo_button.click()
            assert project.values['F15.01'] == 0 and project.values['F15.05'] == 1
        else:
            assert project.values == before
            project.undo()
            assert project.values == {'F15.01': 1}  # No import history entry was added.
    finally:
        view.close()


@pytest.mark.parametrize('invalid', ['different_model', 'zip'])
def test_unusable_file_never_opens_preview_or_mutates_project(app, tmp_path, monkeypatch, invalid):
    view = CatalogView()
    try:
        path = ods_path(tmp_path, model='A650M')
        if invalid == 'zip':
            path.write_bytes(b'PK\x03\x04')
        view.projects['A650'].set('F15.01', 2)
        monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
        errors, previews = [], []
        monkeypatch.setattr(QMessageBox, 'warning', lambda *args: errors.append(args[-1]))
        monkeypatch.setattr(StudioImportDialog, 'exec', lambda *args: previews.append(args))
        view._import_ods()
        assert len(errors) == 1 and not previews
        assert view.projects['A650'].values == {'F15.01': 2}
        assert view.projects['A650M'].values == {}
    finally:
        view.close()


def test_empty_profile_has_no_selectable_defaults(app):
    dialog = StudioImportDialog((), 'A650')
    try:
        assert dialog.table.rowCount() == 0
        assert not dialog.selected_changes()
        assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    finally:
        dialog.close()
