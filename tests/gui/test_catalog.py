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
        assert view.table.item(0, 5).text() == 'Отличается'
        assert 'Нет чётности' in view.table.item(0, 5).toolTip()
        assert view.projects['A650'].values['F15.01'] == 1
        view.search.setText('F13.01')
        assert view.table.item(0, 5).text() == 'Нет в обоих'
    finally:
        view.close()


def test_unknown_enum_round_trip_is_visible_and_not_replaced(app):
    from a650.a650lib.offline_project import OfflineProject
    view = CatalogView()
    try:
        view.projects['A650'] = OfflineProject('A650', {'F15.01': 9})
        view.search.setText('F15.01')
        item = view.table.item(0, 4)
        assert 'Неизвестное значение (9)' == item.text()
        index = view.table.indexFromItem(item)
        delegate = view.table.itemDelegateForColumn(4)
        editor = delegate.createEditor(view.table, None, index)
        delegate.setEditorData(editor, index)
        assert editor.currentData() == 9
        delegate.setModelData(editor, view.table.model(), index)
        assert view.projects['A650'].values['F15.01'] == 9
        editor.setCurrentIndex(editor.findData(2))
        delegate.setModelData(editor, view.table.model(), index)
        assert view.projects['A650'].values['F15.01'] == 2
    finally:
        view.close()


def test_editable_filter_shows_only_supported_offline_entries(app):
    view = CatalogView()
    try:
        view.editable_only.setChecked(True)
        codes = {entry.code for entry in view.visible_entries}
        assert {'F15.01', 'F13.01', 'F01.01', 'F03.00'} <= codes
        assert 'F18.08' not in codes
        assert all(view.table.item(i, 4).flags() & Qt.ItemFlag.ItemIsEditable
                   for i in range(view.table.rowCount()))
        view.model.setCurrentText('A650M')
        view.search.setText('F18.08')
        assert view.table.rowCount() == 0
    finally:
        view.close()


def test_difference_filter_history_and_model_switch(app):
    from a650.a650lib.offline_project import OfflineProject
    view = CatalogView()
    try:
        view.commit_edit('F15.01', 1)
        view.comparison = OfflineProject('A650', {'F15.01': 0, 'F13.01': '25.0'})
        view.differences_only.setEnabled(True)
        view.differences_only.setChecked(True)
        assert {e.code for e in view.visible_entries} == {'F15.01', 'F13.01'}
        view.search.setText('F15.01')
        view.table.selectRow(0)
        view.commit_edit('F15.01', 0)
        assert view.table.rowCount() == 0
        view.undo_button.click()
        assert view.table.rowCount() == 1
        assert view.projects['A650'].values['F15.01'] == 1
        view.model.setCurrentText('A650M')
        view.commit_edit('F15.01', 2)
        view.undo_button.click()
        assert 'F15.01' not in view.projects['A650M'].values
        view.model.setCurrentText('A650')
        assert view.projects['A650'].values['F15.01'] == 1
        view.undo_button.click()
        assert view.projects['A650'].values == {}
        assert 'A650' not in view.unsaved
    finally:
        view.close()


def test_real_cell_commit_and_escape_with_comparison(app):
    from PySide6.QtWidgets import QComboBox
    from PySide6.QtTest import QTest
    from a650.a650lib.offline_project import OfflineProject
    view = CatalogView()
    try:
        view.show()
        view.comparison = OfflineProject('A650', {'F15.01': 0})
        view.search.setText('F15.01')
        index = view.table.model().index(0, 4)
        view.table.setCurrentIndex(index)
        view.table.edit(index)
        app.processEvents()
        editor = view.table.findChild(QComboBox)
        assert editor is not None
        editor.setCurrentIndex(editor.findData(1))
        QTest.keyClick(editor, Qt.Key.Key_Return)
        app.processEvents()
        assert view.projects['A650'].values['F15.01'] == 1
        assert 'Чётная' in view.table.item(0, 4).text()
        assert view.table.item(0, 5).text() == 'Отличается'
        assert view.table.currentRow() == 0
        index = view.table.model().index(0, 4)
        view.table.edit(index)
        app.processEvents()
        editor = view.table.findChild(QComboBox)
        editor.setCurrentIndex(editor.findData(2))
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        app.processEvents()
        assert view.projects['A650'].values['F15.01'] == 1
    finally:
        view.close()


def test_clearing_comparison_keeps_current_values_and_history(app):
    from a650.a650lib.offline_project import OfflineProject
    view = CatalogView()
    try:
        view.commit_edit('F15.01', 1)
        view.comparison = OfflineProject('A650', {'F15.01': 0})
        view.differences_only.setEnabled(True)
        view.differences_only.setChecked(True)
        view._clear_comparison()
        assert not view.differences_only.isChecked()
        assert not view.differences_only.isEnabled()
        assert view.projects['A650'].values['F15.01'] == 1
        assert view.undo_button.isEnabled()
        view.search.setText('F15.01')
        view.table.selectRow(0)
        view.search.setText('F15.0')
        assert view.visible_entries[view.table.currentRow()].code == 'F15.01'
        assert 'F15.01' in view.detail.toPlainText()
    finally:
        view.close()
