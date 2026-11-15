import pytest
from PySide6.QtWidgets import QApplication, QAbstractItemView
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
        assert view.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
        view.model.setCurrentText('A650')
        assert view.table.rowCount() == 0
    finally:
        view.close()
