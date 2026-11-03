"""История поисков: поиск по категориям и общий для двух вкладок вид списка.

Отсутствие кнопки «Применить фильтры заново» проверяет tests/test_ui_markup.py
рядом с остальной разметкой «Фильтрации результата» — здесь этот дубль не нужен.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates/index.html").read_text(encoding="utf-8")
HISTORY_JS = (ROOT / "static/js/11-app-init.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static/css/12-socials-empty.css").read_text(encoding="utf-8")


def test_history_searches_by_category():
    """Категория — это запрос поиска: фильтр идёт по queries, а не по разметке."""
    assert 'id="hist-search"' in TEMPLATE
    assert 'oninput="onHistorySearchInput()"' in TEMPLATE
    assert "function onHistorySearchInput" in HISTORY_JS
    assert "(h.queries || [])" in HISTORY_JS
    # Пустой результат объясняет следующий шаг, а не просто «ничего нет».
    assert "очистите поле, чтобы увидеть все" in HISTORY_JS


def test_history_has_grid_mode_with_short_cards():
    # Две маленькие иконки вместо текстовой кнопки: сразу видно, что выйдет.
    assert 'id="btn-hist-view-rows"' in TEMPLATE
    assert 'id="btn-hist-view-grid"' in TEMPLATE
    assert '<use href="#i-list"/>' in TEMPLATE
    assert '<use href="#i-grid"/>' in TEMPLATE
    assert "function setHistoryView" in HISTORY_JS
    # Режим запоминается между открытиями истории.
    assert "hist-view" in HISTORY_JS
    assert "hist-grid" in HISTORY_JS
    assert "#history-list.hist-grid" in STYLE
    # В узкой карточке категория занимает две строки, дальше — многоточие.
    assert "-webkit-line-clamp:2" in STYLE


def test_one_view_switch_drives_both_history_tabs():
    """«Поиски» и «Файлы» — один список: переключатель общий, режим вешается
    и на поиски, и на три списка файлов."""
    assert "function _applyHistoryView" in HISTORY_JS
    assert "#hist-files .history-list" in HISTORY_JS
    files_js = (ROOT / "static/js/05-results-bulk.js").read_text(encoding="utf-8")
    assert "_applyHistoryView()" in files_js
    files_css = (ROOT / "static/css/15-results-tabs.css").read_text(encoding="utf-8")
    assert ".history-list.hist-grid{" in files_css
    assert ".history-list.hist-grid .file-card{flex-direction:column" in files_css


def test_map_follows_the_dark_theme():
    """Тёмной карты у OSM нет: инвертируем только слой тайлов, маркеры и
    попапы остаются в цветах темы."""
    map_css = (ROOT / "static/css/06-map-stats.css").read_text(encoding="utf-8")
    assert '[data-theme="dark"] .leaflet-tile-pane{' in map_css
    assert "filter:invert(1) hue-rotate(180deg)" in map_css

