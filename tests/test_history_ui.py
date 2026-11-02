"""История поисков: поиск по категориям, режим сетки и убранная кнопка.

Пользователь не понимал, что делает «Применить фильтры заново», поэтому кнопки
и её кода больше нет, а список истории научился фильтроваться и раскладываться
сеткой.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates/index.html").read_text(encoding="utf-8")
HISTORY_JS = (ROOT / "static/js/11-app-init.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static/css/12-socials-empty.css").read_text(encoding="utf-8")


def _all_js() -> str:
    return "".join(p.read_text(encoding="utf-8")
                   for p in sorted((ROOT / "static/js").glob("*.js")))


def _all_css() -> str:
    return "".join(p.read_text(encoding="utf-8")
                   for p in sorted((ROOT / "static/css").glob("*.css")))


def test_history_searches_by_category():
    """Категория — это запрос поиска: фильтр идёт по queries, а не по разметке."""
    assert 'id="hist-search"' in TEMPLATE
    assert 'oninput="onHistorySearchInput()"' in TEMPLATE
    assert "function onHistorySearchInput" in HISTORY_JS
    assert "(h.queries || [])" in HISTORY_JS
    # Пустой результат объясняет следующий шаг, а не просто «ничего нет».
    assert "очистите поле, чтобы увидеть все" in HISTORY_JS


def test_history_has_grid_mode_with_short_cards():
    assert 'id="btn-hist-view"' in TEMPLATE
    assert 'aria-pressed="false"' in TEMPLATE
    assert "function toggleHistoryView" in HISTORY_JS
    # Режим запоминается между открытиями истории.
    assert "hist-view" in HISTORY_JS
    assert "hist-grid" in HISTORY_JS
    assert "#history-list.hist-grid" in STYLE
    # В узкой карточке категория занимает две строки, дальше — многоточие.
    assert "-webkit-line-clamp:2" in STYLE


def test_refilter_button_and_its_code_are_gone():
    assert "btn-refilter" not in TEMPLATE
    assert "Применить фильтры заново" not in TEMPLATE
    js = _all_js()
    assert "refilterNow" not in js
    assert "Применить фильтры заново" not in js
    assert "btn-refilter" not in _all_css()
