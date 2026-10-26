# -*- coding: utf-8 -*-
"""Баннер обновления и окно истории: вёрстка, повторный показ, действия.

Регресс 2.3.4.2: баннер был position:fixed под шапкой, body получал
padding-top на его высоту — при появлении обновления страница съезжала,
сверху шла чёрная полоса, а баннер перекрывал меню навигации.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static" / "js" / "09-ui-extras.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
HTML = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


def _func(name: str) -> str:
    """Тело функции из собранного фронтенда (по балансу скобок)."""
    start = JS.index("function " + name + "(")
    body = JS.index("{", start)
    depth = 0
    for i in range(body, len(JS)):
        if JS[i] == "{":
            depth += 1
        elif JS[i] == "}":
            depth -= 1
            if depth == 0:
                return JS[start:i + 1]
    raise AssertionError("незакрытая функция " + name)


def _css_block(selector: str) -> str:
    start = CSS.index(selector)
    block = CSS[start:CSS.index("}", start)]
    # Комментарии объясняют, ЧЕМ плох старый fixed-вариант, — проверяем
    # только сами объявления.
    while "/*" in block:
        a = block.index("/*")
        b = block.index("*/", a) + 2
        block = block[:a] + block[b:]
    return block


class TestBannerLayout:
    def test_banner_is_inserted_below_the_navigation(self):
        place = _func("_placeUpdateBanner")
        assert "'.tab-bar'" in place
        assert "nav.insertAdjacentElement('afterend', banner)" in place
        # Ветка «нет навигации» — аварийная: баннер всё равно не поверх шапки.
        assert place.index("afterend") < place.index("body.prepend")
        assert "fixed" not in place

    def test_banner_css_is_in_flow(self):
        block = _css_block("#update-banner{")
        assert "position:fixed" not in block.replace(" ", "")
        assert "position: absolute" not in block
        # Правка body на высоту баннера — источник чёрной полосы и сдвига.
        assert "padding-top" not in block
        assert "margin:0 0 10px" in block.replace("\n", "").replace("  ", "")

    def test_banner_sits_between_tabs_and_panels_in_the_markup(self):
        nav = HTML.index('<nav class="tab-bar"')
        panels = HTML.index('<div class="tab-panels"')
        assert nav < panels
        # Колонка — прямой родитель вкладок: баннер вставляется рядом с nav.
        assert '<main class="right-col"' in HTML

    def test_banner_texts_come_from_update_notes(self):
        """Заголовок и кнопка баннера — из ui.json, а не из скрипта."""
        show = _func("showUpdateBanner")
        assert "banner_new_version" in show and "banner_whats_new" in show
        assert "st.texts" in show
        assert 'id="btn-updates"' in HTML

    def test_header_button_stays_as_the_indicator(self):
        assert 'id="btn-updates"' in HTML
        render = _func("renderUpdateIndicator")
        assert "has-update" in render
        assert "Обновить до v" in render


class TestBannerRepeats:
    def test_closed_banner_returns_for_the_next_version(self):
        show = _func("showUpdateBanner")
        assert "_dismissedBannerVersion === String(newVer)" in show
        assert "return" in show

    def test_manual_check_brings_the_banner_back(self):
        manual = _func("manualUpdateCheck")
        assert "_dismissedBannerVersion = ''" in manual

    def test_failed_update_keeps_the_banner_and_the_button(self):
        upd = _func("selfUpdate")
        assert "_dismissedBannerVersion = ''" in upd
        assert "_updateErrorBox" in upd
        assert "btn.disabled = false" in upd
        # Ошибка видна строкой в баннере, а не только исчезающим тостом.
        err = _func("_updateErrorBox")
        assert "badge" not in err and "role" in err
        assert "'.ub-error'" not in err

    def test_error_box_is_part_of_the_banner(self):
        assert ".ub-error{" in CSS
        assert ".ub-error[hidden]{display:none}" in CSS


class TestChangelogWindow:
    def test_history_opens_without_an_update(self):
        show = _func("showChangelog")
        assert "/update/changelog" in show
        # Окно доступно всегда: кэш не даёт дёргать сеть на каждое открытие.
        assert "_changelogCache" in show
        assert "_renderChangelog" in show

    def test_history_shows_who_is_who(self):
        render = _func("_renderChangelog")
        assert "cl-latest" in render and "cl-yours" in render
        # Подписи «новейшая»/«у вас» приходят из update_notes/ui.json.
        texts = _func("_clTexts")
        assert "'latest'" in texts and "'yours'" in texts

    def test_list_shows_a_short_summary(self):
        render = _func("_renderChangelog")
        assert "cl-sum" in render
        assert "_clVersions" in render
        # Краткое и полное описание — разные поля, а не один текст.
        versions = _func("_clVersions")
        assert "summary" in versions and "items" in versions

    def test_version_opens_the_full_text(self):
        render = _func("_renderChangelog")
        assert "openChangelogVersion(" in render
        assert "cl-item-t" in render and "cl-item-x" in render
        opener = _func("openChangelogVersion")
        assert "_changelogOpen" in opener
        assert "_renderChangelog" in opener
        assert "_changelogOpen = ''" in _func("backToChangelog")

    def test_no_second_check_for_updates_button(self):
        """В шапке уже есть «Обновления» — дубль в окне истории убран."""
        show = _func("showChangelog")
        assert "Проверить обновление" not in show
        assert "showChangelogCheck" not in JS
        assert "Проверить обновление" not in _func("_renderChangelog")

    def test_ui_texts_are_not_hardcoded_in_the_js(self):
        """Подписи окна живут в update_notes/ui.json, а не в скрипте."""
        ui = (ROOT / "update_notes" / "ui.json").read_text(encoding="utf-8")
        for key in ("modal_title", "modal_subtitle", "latest", "yours",
                    "details", "back", "close", "empty", "offline", "error"):
            assert f'"{key}"' in ui, key
        assert "meta.texts" in _func("_clTexts")
        assert "/update/changelog" in _func("showChangelog")

    def test_offline_history_falls_back_to_the_bundled_file(self):
        src = (ROOT / "routes" / "update.py").read_text(encoding="utf-8")
        assert "version.json" in src
        assert "offline" in src
