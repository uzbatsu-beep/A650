import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from a650.a650lib.catalog import load_catalog, search_catalog
from a650.gui.catalog import CatalogView


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_model_search_duplicates_and_conflicting_addresses():
    basic, extended = load_catalog('A650'), load_catalog('A650M')
    assert len(search_catalog(basic, 'F13.01')) == 1
    assert not search_catalog(basic, 'F18.08')
    found = search_catalog(extended, 'f18.08')
    assert len(found) == 1
    assert found[0].ram == 0x1206 and found[0].expected_ram == 0x1208
    assert found[0].conflict and not found[0].writable
    duplicate = search_catalog(extended, 'F17.28')
    assert len(duplicate) == 2 and all(x.duplicate for x in duplicate)
    assert search_catalog(extended, 'ПИД', 'F13')
    with pytest.raises(ValueError):
        load_catalog('../other')


def test_catalog_view_shows_conflict_without_write_actions(app):
    view = CatalogView()
    try:
        view.model.setCurrentText('A650M')
        view.search.setText('F18.08')
        assert view.table.rowCount() == 1
        assert view.table.item(0, 3).text() == 'Конфликт'
        view.table.selectRow(0)
        text = view.detail.toPlainText()
        assert '0x1206' in text and '0x1208' in text
        assert 'Запись из каталога недоступна' in text
        assert not (view.table.item(0, 4).flags() & Qt.ItemFlag.ItemIsEditable)
        view.model.setCurrentText('A650')
        assert view.table.rowCount() == 0
    finally:
        view.close()


def test_typed_editors_and_filter_preserve_values(app):
    from PySide6.QtWidgets import QComboBox, QLineEdit
    from a650.gui.project_delegate import ProjectDelegate
    view = CatalogView()
    try:
        view.search.setText('F15.01')
        item = view.table.item(0, 4)
        index = view.table.indexFromItem(item)
        delegate = view.table.itemDelegateForColumn(4)
        editor = delegate.createEditor(view.table, None, index)
        assert isinstance(editor, QComboBox)
        assert [editor.itemData(i) for i in range(1, 5)] == [0, 1, 2, 3]
        delegate.setEditorData(editor, index)
        assert editor.currentData() is None
        editor.setCurrentIndex(editor.findData(1))
        delegate.setModelData(editor, view.table.model(), index)
        assert view.projects['A650'].values['F15.01'] == 1
        assert 'Чётная' in view.table.item(0, 4).text()
        view.search.setText('F13.01')
        index = view.table.indexFromItem(view.table.item(0, 4))
        editor = delegate.createEditor(view.table, None, index)
        assert isinstance(editor, QLineEdit)
        editor.setText('50,0')
        delegate.setModelData(editor, view.table.model(), index)
        assert view.projects['A650'].values['F13.01'] == '50.0'
        view.search.setText('F15.01')
        assert 'Чётная' in view.table.item(0, 4).text()
        assert view.table.item(0, 5).text() == 'Не выбрано'
    finally:
        view.close()


def test_compare_file_reports_difference_without_changing_project(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from a650.a650lib.offline_project import OfflineProject
    view = CatalogView()
    try:
        view.projects['A650'].set('F15.01', 1)
        baseline = OfflineProject('A650', {'F15.01': 0})
        path = tmp_path / 'baseline.a650.json'
        baseline.save(path)
        monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
        view.search.setText('F15.01')
        view._compare_project()
        assert view.table.item(0, 5).text() == 'Было: 0'
        assert view.projects['A650'].values['F15.01'] == 1
        view.search.setText('F13.01')
        assert view.table.item(0, 5).text() == 'Не задано'
    finally:
        view.close()
