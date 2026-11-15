import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from a650.a650lib.catalog import load_catalog, search_catalog
from a650.gui.catalog import CatalogView


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_main_window_starts_on_editable_parameters_and_identifies_build(app):
    from a650 import __version__
    from a650.gui.app import MainWindow
    window = MainWindow()
    try:
        assert window.tabs.currentWidget() is window.catalog
        assert window.catalog.editable_only.isChecked()
        assert len(window.catalog.visible_entries) == 14
        assert __version__ in window.windowTitle()
        assert all(window.catalog.table.item(i, 4).flags() & Qt.ItemFlag.ItemIsEditable
                   for i in range(window.catalog.table.rowCount()))
    finally:
        window.close()


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


def test_observations_keep_timestamp_and_ignore_old_connection(app):
    import time
    view = CatalogView()
    try:
        view.set_connection(True)
        view.search.setText('F15.01')
        view._request_read()
        token = view._read_token
        view.receive_values(token, {'F15.01': 1})
        assert 'Чётная' in view.table.item(0, 6).text()
        stamp = view.observed['F15.01']['stamp']
        view.observed['F15.01']['time'] = time.monotonic() - 6
        view._expire_observations()
        assert 'Устарело' in view.table.item(0, 6).text()
        assert view.observed['F15.01']['stamp'] == stamp
        view.set_connection(False)
        view.receive_values(token, {'F15.01': 0})
        assert view.observed['F15.01']['value'] == 1
        assert not view.read_button.isEnabled()
        assert view.projects['A650'].values == {}
    finally:
        view.close()


def test_real_controller_to_catalog_reads_without_writing(app):
    import time
    from a650.gui.app import MainWindow
    win = MainWindow()
    def wait_for(condition):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            app.processEvents()
            if condition():
                return
            time.sleep(0.005)
        pytest.fail('reading did not finish')
    try:
        win.ctrl.connect_drive(simulate=True, session='catalog-read-test')
        wait_for(lambda: win.catalog.read_button.isEnabled())
        view = win.catalog
        view.search.setText('F15.01')
        view.read_button.click()
        assert not view.read_button.isEnabled()
        wait_for(lambda: 'F15.01' in view.observed)
        assert view.observed['F15.01']['value'] == 0
        assert win.ctrl.client.transport.log[-1][1] == 3
        assert all(frame[1] == 3 for frame in win.ctrl.client.transport.log)
        view.commit_edit('F15.01', 1)
        view.table.selectRow(0)
        assert 'Проект отличается от симулятора' in view.detail.toPlainText()
        win.ctrl.disconnect_drive()
        wait_for(lambda: not view.read_button.isEnabled())
        assert view.observed['F15.01']['stale']
    finally:
        win.catalog.unsaved.clear()
        win.close()


def test_failed_read_keeps_old_value_stale_and_unscaled_numbers_unread(app):
    view = CatalogView()
    try:
        view.set_connection(True)
        view.search.setText('F15.01')
        view._request_read()
        token = view._read_token
        view.receive_values(token, {'F15.01': 2})
        stamp = view.observed['F15.01']['stamp']
        view._request_read()
        view.read_failed(view._read_token, 'тайм-аут')
        assert view.observed['F15.01']['value'] == 2
        assert view.observed['F15.01']['stamp'] == stamp
        assert 'Устарело' in view.table.item(0, 6).text()
        view.search.setText('F13.01')
        assert view.table.item(0, 6).text() == 'Нет подтверждённого кодека'
        requests = []
        view.readRequested.connect(lambda codes, token: requests.append(codes))
        view._request_read()
        assert not requests
    finally:
        view.close()


def test_take_sample_batch_disappears_from_difference_filter_and_undo_restores(app):
    from a650.a650lib.offline_project import OfflineProject
    view = CatalogView()
    try:
        view.projects['A650'] = OfflineProject('A650', {'F15.01': 1, 'F13.01': '10.0'})
        view.comparison = OfflineProject('A650', {'F15.01': 0, 'F13.01': '20.0'})
        view.differences_only.setEnabled(True)
        view.differences_only.setChecked(True)
        view.table.selectAll()
        assert view.take_sample_button.isEnabled()
        view.take_sample_button.click()
        assert view.projects['A650'].values == {'F15.01': 0, 'F13.01': '20.0'}
        assert view.table.rowCount() == 0
        assert not view.take_sample_button.isEnabled()
        view.undo_button.click()
        assert view.projects['A650'].values == {'F15.01': 1, 'F13.01': '10.0'}
        assert view.table.rowCount() == 2
        assert not view.projects['A650'].can_undo
    finally:
        view.close()


def test_take_unknown_sample_is_blocked_and_clear_is_undoable(app):
    from a650.a650lib.offline_project import OfflineProject
    view = CatalogView()
    try:
        view.projects['A650'] = OfflineProject('A650', {'F15.01': 1})
        view.comparison = OfflineProject('A650', {'F15.01': 9})
        view.search.setText('F15.01')
        view.table.selectRow(0)
        assert not view.take_sample_button.isEnabled()
        view._take_sample()  # handler also guards against invalid programmatic requests
        assert view.projects['A650'].values['F15.01'] == 1
        assert view.remove_value_button.isEnabled()
        view.remove_value_button.click()
        assert 'F15.01' not in view.projects['A650'].values
        assert view.table.item(0, 4).text() == 'Выбрать…'
        view.undo_button.click()
        assert view.projects['A650'].values['F15.01'] == 1
        assert not view.projects['A650'].dirty
    finally:
        view.close()


def test_selection_with_missing_sample_never_partially_merges(app):
    from a650.a650lib.offline_project import OfflineProject
    view = CatalogView()
    try:
        view.projects['A650'] = OfflineProject('A650', {'F15.00': 2, 'F15.01': 1})
        view.comparison = OfflineProject('A650', {'F15.01': 0})
        view.group.setCurrentText('F15')
        view.table.selectAll()
        assert not view.take_sample_button.isEnabled()
        view._take_sample()
        assert view.projects['A650'].values == {'F15.00': 2, 'F15.01': 1}
        assert not view.projects['A650'].can_undo
    finally:
        view.close()
