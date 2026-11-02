# -*- coding: utf-8 -*-
"""Сквозной аудит доступности и контраста — в НАСТОЯЩЕМ браузере.

Зачем: tests/test_theme_contrast.py проверяет токены и правила по тексту CSS,
но итоговый цвет надписи складывается из наследования, перекрытий и наложения
полупрозрачных слоёв — увидеть его можно только на отрисованной странице. Здесь
приложение поднимается на свободном порту (tests/conftest.py), страница
открывается браузером пользователя (тот же Chrome DevTools Protocol, что и при
поиске), и в ней выполняется tests/a11y_audit.js.

Проверяется то, что человек действительно видит и трогает:

* контраст текста к его фактическому фону (WCAG AA: 4.5:1, 3:1 для крупного);
* доступные имена кнопок, ссылок, полей и переключателей;
* подписи у полей ввода;
* ARIA-связи (aria-controls/aria-labelledby указывают на существующие узлы)
  и состояния (aria-expanded, aria-selected, aria-checked у role=switch);
* отсутствие горизонтального скролла страницы.

Матрица состояний: обе темы × (раскрытый сайдбар, свёрнутый сайдбар, попап
уведомлений, блок API-ключей, тосты, каждая вкладка, таблица с записями,
статистика).

Клавиатура (порядок фокуса, видимая рамка, ловушка Tab в модалках) проверяется
отдельно — там нужны НАСТОЯЩИЕ нажатия клавиш, см. tests/test_a11y_keyboard.py.

Отдельный тест-канарейка доказывает, что аудит вообще что-то находит: в
страницу подкладывается белая надпись на светлом фоне и кнопка без имени, и
аудит обязан про них сообщить. Без этого «нуль находок» ничего не значит.

Браузера на Chromium может не быть (CI-раннер без Chrome, чужой ноутбук) —
тогда тест СКИПАЕТСЯ с явной причиной, а не падает: отсутствие браузера не
делает интерфейс недоступным.

Run with: python -m pytest tests/test_a11y_browser.py -v
"""
import json
import time
from pathlib import Path

import pytest

from tests._browser import new_tab

ROOT = Path(__file__).resolve().parent.parent
AUDIT_JS = (ROOT / "tests" / "a11y_audit.js").read_text(encoding="utf-8")

TABS = ("log", "table", "map", "stats", "history", "templates")

# Состояния страницы, которые проверяются в обеих темах.
STATE_SPECS = (
    ("collapsed-sidebar", {"fillForm": True}),
    ("open-sidebar", {"fillForm": True, "expandAccordions": True}),
    ("notify-popover", {"fillForm": True, "openNotify": True}),
    ("api-keys", {"fillForm": True, "openApiKeys": True}),
    ("toasts", {"fillForm": True, "toasts": True}),
    ("table-with-rows", {"fillForm": True, "tab": "table", "seedRows": True}),
    ("stats-with-rows", {"fillForm": True, "tab": "stats", "seedRows": True, "seedStats": True}),
    *[(f"tab-{t}", {"fillForm": True, "expandAccordions": True, "tab": t}) for t in TABS],
)

CONTRAST_FLOOR = 4.5

# Размер окна проверки — один на всех машинах и системах. Без него раскладка
# зависит от того, каким окном запустился браузер на раннере: на широком окне
# горизонтального скролла нет, на узком (980px на macOS-раннере) та же
# страница скроллилась вбок, и тест «падал только на macOS».
# 1024×800 — самое узкое из обычных окон ноутбука: интерфейс обязан в него
# влезать.
VIEWPORT = (1024, 800)


def run_audit(cdp, url: str, state: dict) -> dict:
    """Открыть страницу в браузере, применить состояние и выполнить аудит."""
    ws_url = cdp._create_tab()
    assert ws_url, "не удалось создать вкладку в браузере"
    expression = f"window.__A11Y_STATE = {json.dumps(state, ensure_ascii=False)};\n{AUDIT_JS}"
    try:
        raw = cdp._cdp_eval_page(
            ws_url, url, expression,
            wait_expr="document.getElementById('setup-summary')",
            timeout_s=90,
            viewport=VIEWPORT,
        )
    finally:
        # Вкладка живёт один аудит: без закрытия за прогон их набираются
        # десятки, каждый держит процесс-рендерер, и проверка начинает
        # ловить таймауты вместо находок (замер: один тест — 6 с, а в общем
        # прогоне после восьми аудитов уже сотня секунд).
        cdp._close_dead_tab(ws_url)
    assert raw, f"аудит не вернул результат (состояние {state})"
    return json.loads(raw)


def format_findings(findings: list) -> str:
    return "\n".join(
        f"  [{f['check']}] {f['sel']}: {f['detail']}" for f in findings
    )


# ── Матрица: обе темы во всех состояниях страницы ───────────────
@pytest.mark.parametrize("theme", ("light", "dark"))
@pytest.mark.parametrize("name,extra", STATE_SPECS, ids=[s[0] for s in STATE_SPECS])
def test_interface_passes_audit(browser_cdp, live_app_url, theme, name, extra):
    state = {"theme": theme, **extra}
    result = run_audit(browser_cdp, live_app_url, state)
    assert result["stats"]["scanned"] > 50, (
        f"аудит осмотрел слишком мало элементов ({result['stats']}) — "
        "похоже, страница не отрисовалась"
    )
    findings = result["findings"]
    assert findings == [], (
        f"{theme} тема, состояние «{name}»: {len(findings)} нарушений\n"
        + format_findings(findings)
    )


# ── Канарейка: аудит обязан находить подложенные нарушения ──────
def test_audit_detects_broken_markup(browser_cdp, live_app_url):
    """Без этой проверки «нуль находок» ничего не доказывает.

    В страницу кладётся белая надпись на светлом фоне (2.27:1) и кнопка без
    доступного имени — обе обязаны попасть в отчёт.
    """
    result = run_audit(browser_cdp, live_app_url, {"theme": "light", "canary": True})
    findings = result["findings"]
    contrast = [f for f in findings if f["check"] == "contrast" and "canary" in f["sel"]]
    names = [f for f in findings if f["check"] == "name" and "canary" in f["sel"]]
    assert contrast, f"контраст-проверка не сработала:\n{format_findings(findings)}"
    assert names, f"проверка доступных имён не сработала:\n{format_findings(findings)}"
    assert float(contrast[0]["detail"].split(":1")[0]) < CONTRAST_FLOOR


# ── Тумблеры и попап уведомлений: тема переключается на живом интерфейсе ──
def test_theme_switch_keeps_the_notify_popover_readable(browser_cdp, live_app_url):
    """Один и тот же попап проверяется в двух темах — переключение на месте.

    Переключение темы не перерисовывает страницу заново: цвета в попапе
    (тумблеры, селекты звуков, ползунок громкости) меняются на месте, без
    перезагрузки — раньше именно здесь терялся контраст.
    """
    light = run_audit(browser_cdp, live_app_url, {"theme": "light", "openNotify": True})
    dark = run_audit(browser_cdp, live_app_url, {"theme": "dark", "openNotify": True})
    assert light["findings"] == [], format_findings(light["findings"])
    assert dark["findings"] == [], format_findings(dark["findings"])

# ── Кнопки шапки: клик доходит до обработчика ────────────────────
# Кнопки первого ряда; служебные действия живут в меню «Ещё» (MENU_BUTTONS).
HEADER_BUTTONS = ("btn-terms", "btn-notify", "btn-theme", "btn-tools")
MENU_BUTTONS = ("btn-logs", "btn-diag", "btn-report", "btn-whatsnew", "btn-updates")


def test_header_buttons_are_clickable(browser_cdp, live_app_url):
    """Клик по кнопке шапки доходит до неё, а не в слой поверх панели.

    Аудит доступности проверяет имена и контраст, но не то, попадает ли
    указатель в кнопку: прозрачный оверлей с inset:0 оставляет разметку
    идеально доступной и при этом съедает все клики — так панель выглядит
    «мёртвой». Здесь проверяются оба звена: кнопка сверху под курсором и
    настоящий клик, после которого открылось окно логов.
    """
    tab = new_tab(browser_cdp)
    try:
        tab.call("Emulation.setDeviceMetricsOverride", {
            "width": VIEWPORT[0], "height": VIEWPORT[1],
            "deviceScaleFactor": 1, "mobile": False,
        })
        tab.open(live_app_url, wait_expr="document.getElementById('setup-summary')")
        # Уведомление показываем сами: оно висит в правом верхнем углу, ровно
        # над служебными кнопками. Раньше тост перехватывал клики все 3,5 с
        # своей жизни, и кнопки под ним выглядели мёртвыми.
        # Чужие тосты убираем: очередь рисуется сверху вниз, и второй тост
        # уезжает ниже шапки — тогда перекрытие не воспроизводится.
        tab.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove()); true")
        tab.evaluate("showToast('Проверка: уведомление не перекрывает кнопки'); true")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if tab.evaluate("!!document.querySelector('.toast.show')"):
                break
            time.sleep(0.05)
        assert tab.evaluate("!!document.querySelector('.toast.show')"), "тост не появился"
        blocked = tab.evaluate(
            "(() => { const ids = " + json.dumps(list(HEADER_BUTTONS)) + ";"
            " return ids.filter(id => {"
            "   const el = document.getElementById(id);"
            "   if (!el || !el.offsetParent) return true;"
            "   const r = el.getBoundingClientRect();"
            "   const top = document.elementFromPoint(r.left + r.width / 2,"
            "                                           r.top + r.height / 2);"
            "   return !(top && (top === el || el.contains(top)));"
            " }); })()"
        )
        assert blocked == [], "клик не доходит до кнопок шапки: " + ", ".join(blocked)
        # Служебные действия — в меню «Ещё»: сначала открываем его.
        assert tab.click("#btn-tools"), "кнопка «Ещё» не найдена"
        hidden = tab.evaluate(
            "(() => { const ids = " + json.dumps(list(MENU_BUTTONS)) + ";"
            " return ids.filter(id => { const el = document.getElementById(id);"
            " return !(el && el.offsetParent); }); })()"
        )
        assert hidden == [], "пункты меню не открылись: " + ", ".join(hidden)
        assert tab.click("#btn-logs"), "кнопка «Логи» не найдена"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if tab.evaluate("!!document.querySelector('.logs-modal-overlay')"):
                break
            time.sleep(0.1)
        assert tab.evaluate("!!document.querySelector('.logs-modal-overlay')"), (
            "клик по «Логи» не открыл окно — обработчик не сработал"
        )
    finally:
        tab.close()

def test_toast_has_background_and_close_button(browser_cdp, live_app_url):
    """Уведомление всегда видно и его можно закрыть крестиком.

    Дважды подводило: тип без своего правила краски («info», «warn», «ok»)
    давал прозрачную подложку, и белая надпись пропадала на светлой
    странице; а закрыть уведомление можно было только ожиданием таймера.
    """
    tab = new_tab(browser_cdp)
    try:
        tab.open(live_app_url, "typeof showToast === 'function'")
        # Оба оформления: в тёмной теме ошибка раньше красилась токеном
        # рамки (полупрозрачным), и проверка одной темы это пропускала.
        rows = []
        for scheme in ('light', 'dark'):
            tab.evaluate("document.documentElement.dataset.theme = '%s'" % scheme)
            rows += json.loads(tab.evaluate("""(() => {
          document.querySelectorAll('#toast-container .toast').forEach(t => t.remove());
          const out = [];
          const theme = document.documentElement.dataset.theme;
          for (const kind of ['info', 'warn', 'warning', 'ok', 'success', 'error', 'неизвестный']) {
            showToast('Проверка уведомления: ' + kind, kind);
            const el = [...document.querySelectorAll('#toast-container .toast')].pop();
            const cs = getComputedStyle(el);
            out.push({
              kind,
              bg: cs.backgroundColor,
              alpha: cs.opacity,
              hasClose: !!el.querySelector('.toast-x'),
              translucent: /rgba\([^)]*,\s*0(\.\d+)?\)$/.test(cs.backgroundColor),
              closeBox: el.querySelector('.toast-x')
                ? (r => [Math.round(r.width), Math.round(r.height)])(el.querySelector('.toast-x').getBoundingClientRect())
                : null,
            });
            el.remove();
          }
          document.documentElement.dataset.theme = theme;
          return JSON.stringify(out);
        })()"""))
        assert len(rows) == 14, rows
        for row in rows:
            assert not row["translucent"], f"{row['kind']}: фон прозрачный — {row['bg']}"
            assert row["bg"] != "rgba(0, 0, 0, 0)", f"{row['kind']}: фон отсутствует"
            assert row["hasClose"], f"{row['kind']}: нет крестика"
            w, h = row["closeBox"]
            assert w >= 24 and h >= 24, f"{row['kind']}: крестик {w}×{h} меньше 24×24"

        # Крестик закрывает тост сразу, не дожидаясь таймера.
        tab.evaluate("showToast('Закрой меня', 'info'); true")
        assert tab.click("#toast-container .toast .toast-x"), "крестик не нажимается"
        gone = None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if not tab.evaluate("!!document.querySelector('#toast-container .toast')"):
                gone = True
                break
            time.sleep(0.1)
        assert gone, "крестик не закрыл уведомление"
    finally:
        tab.close()

