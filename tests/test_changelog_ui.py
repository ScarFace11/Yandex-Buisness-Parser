# -*- coding: utf-8 -*-
"""Окно «Что нового» в живом браузере: список кратко, полный текст по нажатию.

Проверяется то, что видит пользователь, а не наличие строк в скрипте:
в списке только краткое описание, нажатие на версию открывает её полный
текст, «Назад» возвращает список, Escape закрывает окно. Отдельно — что
дублирующей кнопки проверки обновлений в окне больше нет.

Run with: python -m pytest tests/test_changelog_ui.py -v
"""
import json
import time

from tests._browser import new_tab


def _wait(tab, expr, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if tab.evaluate(expr):
            return True
        time.sleep(0.2)
    return False


def test_changelog_list_shows_summary_and_opens_full_text(browser_cdp, live_app_url):
    tab = new_tab(browser_cdp)
    try:
        tab.open(live_app_url, "typeof showChangelog === 'function'")
        tab.evaluate("document.querySelectorAll('#version-gate,#terms-overlay').forEach(el => el.hidden = true)")
        tab.evaluate("showChangelog()")
        assert _wait(tab, "!!document.querySelector('#changelog-overlay .cl-entry')"), "список версий не появился"

        # 1. В списке — краткое описание, а не полный текст.
        info = tab.evaluate("""(() => {
          const rows = [...document.querySelectorAll('#changelog-overlay .cl-entry')];
          const r = rows[0];
          return JSON.stringify({
            count: rows.length,
            ver: r.querySelector('.cl-ver').textContent.trim(),
            sum: (r.querySelector('.cl-sum') || {}).textContent || '',
            hasItems: !!r.querySelector('.cl-item-x'),
            buttons: [...document.querySelectorAll('#changelog-overlay button')].map(b => b.textContent.trim()),
            title: document.querySelector('#cl-title').textContent.trim(),
            sub: document.querySelector('.cl-sub').textContent.trim(),
          });
        })()""")
        info = json.loads(info) if isinstance(info, str) else info
        assert info["count"] >= 3, info
        assert info["ver"].startswith("v"), info
        assert len(info["sum"]) > 20, info
        assert info["hasItems"] is False, "в списке не должно быть полного текста"
        assert not any("Проверить обновление" in b for b in info["buttons"]), info

        # 2. Нажатие на версию открывает полный текст.
        assert tab.click("#changelog-overlay .cl-entry")
        assert _wait(tab, "!!document.querySelector('#changelog-overlay .cl-detail')"), "полный текст не открылся"
        detail = json.loads(tab.evaluate("""(() => {
          const items = [...document.querySelectorAll('#changelog-overlay .cl-item-x')];
          return JSON.stringify({
            items: items.length,
            first: items.length ? items[0].textContent.trim() : '',
            head: document.querySelector('#changelog-overlay .cl-ver').textContent.trim(),
            list: !!document.querySelector('#changelog-overlay .cl-entry'),
            buttons: [...document.querySelectorAll('#changelog-overlay button')].map(b => b.textContent.trim()),
          });
        })()"""))
        assert detail["items"] >= 1, detail
        assert len(detail["first"]) > 40, detail
        assert detail["list"] is False, "в подробном виде список должен уступать место тексту"
        assert any("Назад" in b for b in detail["buttons"]), detail

        # 3. «Назад» возвращает к списку версий.
        assert tab.click("#changelog-overlay .cl-foot .m-cancel")
        assert _wait(tab, "!!document.querySelector('#changelog-overlay .cl-entry')"), "назад не вернул список"

        # 4. Escape закрывает окно.
        tab.press("Escape")
        assert _wait(tab, "!document.querySelector('#changelog-overlay')"), "Escape не закрыл окно"
    finally:
        tab.close()
