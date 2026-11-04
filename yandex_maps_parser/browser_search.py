"""Поиск организаций через сам Яндекс.Карты (реальный Chrome, CDP)."""
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote

from . import cdp_client
from . import city_coords
from . import state

# Селекторы карточки поисковой выдачи Яндекс.Карт (проверены на живой странице: data-object="search-list-item" + data-id/data-coordinates).
CARD_SELECTOR = '[data-object="search-list-item"]'

# Сколько карточек максимум забирать с одной точки.
_MAX_CARDS = 250

# Яндекс отдаёт по 25 организаций на страницу выдачи.
_CARDS_PER_PAGE = 25

# Минимальный размер inline-JSON, который считаем состоянием выдачи:
_STATE_MIN_BYTES = 50_000

# Признаки страницы-проверки вместо выдачи.
_BLOCK_JS = (
    "(location.href.indexOf('showcaptcha') >= 0"
    " || /(вы не робот|подтвердите, что запросы)/i.test(document.title || '')"
    " || !!document.querySelector('.SmartCaptcha, #captcha-container'))"
)

# Почему выдача не пришла — на прогон, для человеческого объяснения в UI.
_block_lock = threading.Lock()
_last_block = ""


def blocked_reason() -> str:
    """«captcha», если Яндекс в этом прогоне показал проверку вместо выдачи."""
    with _block_lock:
        return _last_block


def reset_blocked() -> None:
    """Забыть прошлую проверку: новый прогон — новый отсчёт."""
    global _last_block
    with _block_lock:
        _last_block = ""


def _set_blocked(reason: str) -> None:
    global _last_block
    first = False
    with _block_lock:
        first = not _last_block
        _last_block = reason
    if not first:
        return
    # Раньше антибот-детектор жил только в тестах: cooldown и счётчик не
    # включались в рабочем поиске. Теперь капча один раз на прогон включает
    # общий backoff (следующие открытия уже не долбят Яндекс с той же силой).
    try:
        from .rate_limit import _anti_bot_detected
        _anti_bot_detected()
    except Exception:
        pass


# Бюджет на добирание следующих страниц внутри страницы (секунды):
_PAGING_BUDGET_S = 45

_city_cache: dict[str, tuple[float, float] | None] = {}
_city_lock = threading.Lock()

# Центр, который Яндекс.Карты ставят, когда НЕ узнали название: с ним поиск молча уезжал в Москву, хотя пользователь просил другой город.
_DEFAULT_CENTER = (55.7558, 37.6173)
_DEFAULT_EPS = 0.002


def _looks_like_default_center(city: str, coords: tuple[float, float]) -> bool:
    """Это «Москва по умолчанию» вместо запрошенного города?"""
    if city_coords.lookup(city) is not None:
        return False
    low = str(city or "").strip().lower().replace("ё", "е")
    if low.startswith("москв") or low in ("мск", "moscow"):
        return False
    lat, lon = coords
    return (abs(lat - _DEFAULT_CENTER[0]) < _DEFAULT_EPS
            and abs(lon - _DEFAULT_CENTER[1]) < _DEFAULT_EPS)


def _state_wait_expr() -> str:
    """Готовность страницы: состояние выдачи уже в документе — или это капча."""
    return (
        "(Array.prototype.some.call("
        "document.querySelectorAll('script[type=\"application/json\"]'),"
        f"function (s) {{ return (s.textContent || '').length > {_STATE_MIN_BYTES}; }})"
        " || " + _BLOCK_JS + ")"
    )


def _state_harvest_js(want: int) -> str:
    """JS: прочитать выдачу из состояния страницы и добрать следующие страницы."""
    want = max(1, min(int(want), _MAX_CARDS))
    max_page = max(1, min(_MAX_CARDS // _CARDS_PER_PAGE,
                          -(-want // _CARDS_PER_PAGE)))
    return _STATE_JS.replace("$WANT$", str(int(want))) \
                   .replace("$MAXPAGE$", str(int(max_page))) \
                   .replace("$BUDGET$", str(int(_PAGING_BUDGET_S * 1000))) \
                   .replace("$BLOCK$", _BLOCK_JS)


# Шаблон JS (подстановки — $WANT$/$MAXPAGE$/$BUDGET$).
_STATE_JS = """
(async () => {
  const want = $WANT$;
  const maxPage = $MAXPAGE$;
  const budgetMs = $BUDGET$;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // Проверка «Вы не робот?» — не выдача: сообщаем наверх сразу и не ждём
  // состояние, которого на такой странице не появится.
  if ($BLOCK$) return JSON.stringify({blocked: 'captcha'});

  // Состояние выдачи — самый большой inline-JSON документа.
  const readState = (doc) => {
    let best = null;
    for (const s of doc.querySelectorAll('script[type="application/json"]')) {
      const t = s.textContent || '';
      if (!best || t.length > best.length) best = t;
    }
    if (!best) return null;
    try {
      const root = JSON.parse(best);
      return (root && root.stack && root.stack[0] && root.stack[0].results) || null;
    } catch (e) {
      return null;
    }
  };

  // Организация состояния → карточка. Координаты Яндекс отдаёт как
  // [долгота, широта] (GeoJSON, так же как атрибут data-coordinates в вёрстке),
  // поэтому порядок сохраняем: остальной конвейер ждёт "долгота,широта"
  // (см. _items_to_cards, _card_feature).
  const norm = (it) => {
    const id = (it && it.id !== undefined && it.id !== null) ? String(it.id) : '';
    const name = String((it && (it.title || it.shortTitle || it.name)) || '').trim();
    if (!id || !name) return null;              // рекламные врезки без организации
    const rd = it.ratingData || {};
    const value = Number(rd.ratingValue);
    const rating = isFinite(value) ? value.toFixed(1) : '';
    const count = Number(rd.ratingCount || rd.reviewCount || 0);
    const coords = it.coordinates || it.displayCoordinates || [];
    return {
      id: id,
      name: name,
      category: (it.categories || []).map(c => c && c.name).filter(Boolean).join(', '),
      address: String(it.address || it.fullAddress || '').trim(),
      rating: rating,
      reviews: count > 0 ? String(count) : '',
      coords: coords.length > 1 ? (String(coords[0]) + ',' + String(coords[1])) : ''
    };
  };

  let st = null;
  for (let i = 0; i < 40; i++) {
    st = readState(document);
    if (st && (st.items || []).length) break;
    await sleep(500);
  }
  if (!st) return '';   // нет состояния → DOM-фолбэк
  const total = Number(st.totalResultCount || 0) || 0;
  const out = new Map();
  let blocked = '';
  const add = (items) => {
    for (const it of (items || [])) {
      const card = norm(it);
      if (card && !out.has(card.id)) out.set(card.id, card);
    }
  };
  add(st.items);
  if (!out.size) return JSON.stringify({total: total, cards: [], complete: true});

  let complete = true;
  const startedAt = Date.now();
  for (let page = 2; page <= maxPage && out.size < want; page++) {
    if (Date.now() - startedAt > budgetMs) { complete = false; break; }
    if (total && out.size >= total) break;
    // Пауза между страницами: без неё Яндекс видит серию запросов подряд и
    // чаще включает проверку вместо продолжения выдачи.
    await sleep(250 + Math.floor(Math.random() * 400));
    let html = '';
    try {
      // Тот же запрос, что делает сам Яндекс.Карты при прокрутке списка:
      // из страницы, с её cookie и заголовками.
      const pageUrl = location.origin + location.pathname + location.search
                      + (location.search ? '&' : '?') + 'page=' + page;
      const resp = await fetch(pageUrl, {credentials: 'include'});
      if (!resp.ok) { complete = false; break; }
      html = await resp.text();
    } catch (e) {
      complete = false;
      break;
    }
    // Проверка «Вы не робот?» может прийти не на первой, а на следующей
    // странице: раньше такой ответ молча обрывал пагинацию, и точка
    // кэшировалась как неполная, но «завершённая».
    if (/showcaptcha|вы не робот|smartcaptcha/i.test(html)) {
      blocked = 'captcha';
      complete = false;
      break;
    }
    const next = readState(new DOMParser().parseFromString(html, 'text/html'));
    if (!next || !(next.items || []).length) {
      if (total && out.size < total) complete = false;
      break;
    }
    const before = out.size;
    add(next.items);
    if (out.size === before) {
      if (total && out.size < total) complete = false;
      break;
    }
  }
  if (total && out.size < total) complete = false;
  return JSON.stringify({total: total, cards: [...out.values()], complete: complete,
                         blocked: blocked});
})()
"""


def _harvest_js(want: int) -> str:
    """Запасной путь: дождаться выдачи, прокрутить список, вернуть карточки."""
    return """
(async () => {
  const want = %d;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  if ($BLOCK$) return JSON.stringify({blocked: 'captcha'});
  const cards = () => [...document.querySelectorAll('%s')];
  // Ждём первую отрисовку списка (SPA подгружает его после загрузки страницы).
  for (let i = 0; i < 40 && cards().length === 0; i++) await sleep(500);
  // Прокручиваем МАЛЕНЬКИМИ шагами, как человек колесом. Список выдачи
  // виртуализован: прыжок сразу в самый низ (`scrollTop = scrollHeight`)
  // не догружает продолжение — список остаётся на первой горстке карточек
  // (в живом тесте 5–8 вместо 25+). Пока замера не совпадает с размером
  // списка, шагаем дальше.
  // Контейнер перезапрашиваем каждый шаг: SPA может подменить его
  // (в живых замерах первый найденный .scroll__container иногда оказывался
  // пустой заготовкой — scrollHeight 0).
  let prev = -1, still = 0, noScroll = 0;
  const startedAt = Date.now();
  for (let i = 0; i < 120 && cards().length < want; i++) {
    const box = document.querySelector('.scroll__container') || document.scrollingElement;
    const scrollable = !!box && box.scrollHeight > box.clientHeight + 8;
    const before = scrollable ? box.scrollTop : 0;
    if (scrollable) {
      box.scrollTop = Math.min(before + 300, box.scrollHeight);
      box.dispatchEvent(new WheelEvent('wheel', {bubbles: true, deltaY: 300}));
    }
    await sleep(400);
    const n = cards().length;
    // Низ списка: прокрутка дальше не идёт и карточки прибывать перестали.
    const atBottom = scrollable && box.scrollTop <= before + 1
      && box.scrollTop + box.clientHeight >= box.scrollHeight - 8;
    if (n === prev && atBottom) { if (++still >= 3) break; } else { still = 0; }
    // Список не прокручивается вообще — ждать нечего (карточки уже все).
    if (scrollable) { noScroll = 0; } else if (++noScroll >= 8) { break; }
    prev = n;
    if (Date.now() - startedAt > 25000) break;
  }
  const txt = (el, sel) => { const n = el.querySelector(sel); return n ? (n.textContent || '').trim() : ''; };
  const out = cards().map(el => {
    const a = el.querySelector('a[href*="/maps/org/"]');
    const badge = el.querySelector('[class*="rating-badge"]');
    return {
      id: el.getAttribute('data-id') || '',
      coords: el.getAttribute('data-coordinates') || '',
      name: txt(el, '.search-business-snippet-view__title') || (a ? (a.getAttribute('aria-label') || '') : ''),
      category: txt(el, '.search-business-snippet-view__category'),
      address: txt(el, '.search-business-snippet-view__address'),
      rating: txt(el, '.business-rating-badge-view__rating-text'),
      reviews: txt(el, '.business-rating-badge-view__rating-count') || (badge ? (badge.textContent || '') : '')
    };
  });
  let total = 0;
  const head = document.querySelector('.search-list-view__title, .search-heading-title, h1');
  if (head) { const m = (head.textContent || '').match(/(\\d[\\d\\s]*)/); if (m) total = parseInt(m[1].replace(/\\s/g, ''), 10) || 0; }  return JSON.stringify({cards: out, url: location.href, total: total});
})()
""".replace("$BLOCK$", _BLOCK_JS) % (int(want), CARD_SELECTOR)


def _search_url(query: str, city: str, lat: float | None, lon: float | None) -> str:
    """URL страницы поиска: текст запроса + город, при точке — её центр."""
    text = f"{query} {city}".strip()
    url = "https://yandex.ru/maps/?text=" + quote(text)
    if lat is not None and lon is not None:
        url += f"&ll={lon:.6f}%2C{lat:.6f}&z=15&sll={lon:.6f}%2C{lat:.6f}"
    return url


def _num(raw: str) -> str:
    """«4,9» → «4.9», «(1 490 оценок)» → «1490», пустое остаётся пустым."""
    text = re.sub(r"[^\d,.]", "", str(raw or "").replace("\u00a0", " ").replace(" ", ""))
    return text.replace(",", ".").strip(".")


def _reviews(raw: str) -> str:
    m = re.search(r"(\d[\d\s\u00a0]*)", str(raw or ""))
    return m.group(1).replace(" ", "").replace("\u00a0", "") if m else ""


def _items_to_cards(items: list) -> list[dict]:
    """Карточки из состояния страницы → тот же формат, что отдаёт разбор вёрстки."""
    cards: list[dict] = []
    seen: set[str] = set()
    for card in items or []:
        biz_id = str(card.get("id") or "").strip()
        name = str(card.get("name") or "").strip()
        if not biz_id or not name or biz_id in seen:
            continue
        seen.add(biz_id)
        coords = [p.strip() for p in str(card.get("coords") or "").split(",")]
        clat = coords[1] if len(coords) == 2 else ""
        clon = coords[0] if len(coords) == 2 else ""
        cards.append({
            "_biz_id": biz_id,
            "name": name,
            "category": str(card.get("category") or "").strip(),
            "address": str(card.get("address") or "").strip(),
            "rating": _num(card.get("rating")),
            "reviews_count": _reviews(card.get("reviews")),
            "lat": clat,
            "lon": clon,
        })
    return cards


_harvest_local = threading.local()


def _result_info(cards: list[dict], *, total=None, complete=True,
                 status: str = "") -> dict:
    """Результат выдачи вместе с её состоянием.

    `status`: ok / empty / partial / no_state / blocked. Пустая выдача и
    «страница не открылась» — разные вещи: только для второй нужен повтор и
    предупреждение пользователю.
    """
    if not status:
        status = "ok" if cards else "empty"
    try:
        total = int(total) if total not in (None, "") else None
    except (TypeError, ValueError):
        total = None
    if total is not None and total < 0:
        total = None
    if cards and not complete:
        status = "partial"
    return {"cards": cards, "total": total, "complete": bool(complete),
            "status": status}


def _harvest_from_state_ex(url: str, want: int) -> dict:
    raw = cdp_client.eval_in_page(
        url,
        _state_harvest_js(want),
        wait_expr=_state_wait_expr(),
        timeout_s=90.0,
    )
    if not raw:
        return _result_info([], complete=False, status="no_state")
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        state.syslog(f"browser_search: не разобрал состояние выдачи ({str(raw)[:120]!r})")
        return _result_info([], complete=False, status="no_state")
    if data.get("blocked"):
        _set_blocked(str(data.get("blocked")))
        state.syslog("browser_search: вместо выдачи Яндекс показал проверку «Вы не робот?»")
        return _result_info([], total=data.get("total"), complete=False, status="blocked")
    cards = _items_to_cards(data.get("cards") or [])
    total = data.get("total")
    if cards:
        state.syslog(f"browser_search: cards={len(cards)} из {total or '?'} "
                     f"(состояние страницы)")
    return _result_info(cards, total=total,
                        complete=bool(data.get("complete", True)))


def _harvest_from_state(url: str, want: int) -> list[dict]:
    """Совместимый вход: карточки из состояния страницы."""
    info = _harvest_from_state_ex(url, want)
    _harvest_local.state_info = info
    return info["cards"]


def _harvest_from_dom_ex(url: str, want: int) -> dict:
    raw = cdp_client.eval_in_page(
        url,
        _harvest_js(want),
        wait_expr=(f"(document.querySelectorAll('{CARD_SELECTOR}').length > 0"
                   f" || {_BLOCK_JS})"),
        timeout_s=90.0,
    )
    if not raw:
        return _result_info([], complete=False, status="no_state")
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        state.syslog(f"browser_search: не разобрал JSON выдачи ({str(raw)[:120]!r})")
        return _result_info([], complete=False, status="no_state")
    if data.get("blocked"):
        _set_blocked(str(data.get("blocked")))
        return _result_info([], complete=False, status="blocked")
    return _result_info(_items_to_cards(data.get("cards") or []),
                        total=data.get("total"))


def _harvest_from_dom(url: str, want: int) -> list[dict]:
    """Совместимый вход: карточки из вёрстки выдачи."""
    info = _harvest_from_dom_ex(url, want)
    _harvest_local.dom_info = info
    return info["cards"]


def harvest_cards_ex(query: str, city: str, lat: float | None, lon: float | None,
                     max_cards: int = 50) -> dict:
    """Карточки и состояние выдачи: total/status/complete."""
    want = max(1, min(int(max_cards or 50), _MAX_CARDS))
    url = _search_url(query, city, lat, lon)
    state.syslog(f"browser_search: {url}")
    _harvest_local.state_info = None
    cards = _harvest_from_state(url, want)
    info = getattr(_harvest_local, "state_info", None)
    if info is None:
        # Тесты и внешние вызовы могут подменить старый вход списком.
        info = _result_info(cards, complete=bool(cards),
                            status="ok" if cards else "no_state")
    if info.get("status") != "blocked" and not cards and info.get("status") != "empty":
        state.syslog("browser_search: состояния с выдачей нет — разбираю вёрстку")
        _harvest_local.dom_info = None
        cards = _harvest_from_dom(url, want)
        dom_info = getattr(_harvest_local, "dom_info", None)
        if dom_info is None:
            dom_info = _result_info(cards, status="ok" if cards else "empty")
        info = dom_info
        if cards:
            state.syslog(f"browser_search: cards={len(cards)} (вёрстка)")
    info = dict(info, cards=cards)
    state.syslog(f"browser_search: cards={len(cards)} из {info.get('total') or '?'} "
                 f"(запрошено до {want}, status={info.get('status')}), запрос={query!r}")
    return info


def harvest_cards(query: str, city: str, lat: float | None, lon: float | None,
                  max_cards: int = 50) -> list[dict]:
    """Карточки выдачи Яндекс.Карт по запросу (без API-ключей)."""
    return harvest_cards_ex(query, city, lat, lon, max_cards)["cards"]


def city_center(city: str) -> tuple[float, float] | None:
    """Координаты центра города: таблица → кэш → карта (без геокодера-API)."""
    key = (city or "").strip().lower()
    if not key:
        return None
    with _city_lock:
        if key in _city_cache:
            return _city_cache[key]

    coords = city_coords.lookup(city)

    if coords is None:
        coords = _center_from_disk(key)
        if coords is not None and _looks_like_default_center(city, coords):
            # Мусор в кэше: когда-то город не опознался и туда лёг центр Москвы.
            state.syslog(f"browser_search: в кэше координат «{city}» лежит центр "
                         "по умолчанию — ищу заново")
            coords = None

    if coords is None:
        coords = _center_from_browser(city)
        if coords is not None:
            _center_to_disk(key, coords)

    with _city_lock:
        _city_cache[key] = coords
    return coords


def _center_from_browser(city: str) -> tuple[float, float] | None:
    """Центр города с карты: варианты запроса + отбраковка «Москвы по умолчанию»."""
    for query in (city, f"{city}, Россия", f"город {city}"):
        raw = cdp_client.eval_in_page(
            "https://yandex.ru/maps/?text=" + quote(query),
            "location.href",
            timeout_s=45.0,
        )
        coords = _parse_center(raw or "")
        if coords is None:
            continue
        if _looks_like_default_center(city, coords):
            state.syslog(f"browser_search: «{query}» не распознан — Яндекс вернул "
                         "центр по умолчанию, пробую иначе")
            continue
        state.syslog(f"browser_search: центр «{city}» с карты: "
                     f"{coords[0]:.4f}, {coords[1]:.4f}")
        return coords
    state.syslog(f"browser_search: координаты «{city}» не получены — "
                 "поиск пойдёт по тексту без сетки точек")
    return None


# Accept both the usual %2C and a raw comma: the mobile page / live JS rewrites can leave ll=37.6,55.7 unencoded, and then _parse_center used to return None and the city silently fell back to the Moscow default.
_CENTER_RE = re.compile(r"[?&](?:ll|sll)=(-?\d+\.\d+)(?:%2C|,)(-?\d+\.\d+)")


def _parse_center(url: str) -> tuple[float, float] | None:
    m = _CENTER_RE.search(url or "")
    if not m:
        return None
    try:
        lon, lat = float(m.group(1)), float(m.group(2))
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return (lat, lon)


def _cache_path() -> Path:
    return Path(state.OUTPUT_DIR) / ".cache" / "city_centers.json"


def _center_from_disk(key: str) -> tuple[float, float] | None:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        item = data.get(key)
        if isinstance(item, list) and len(item) == 2:
            return (float(item[0]), float(item[1]))
    except Exception:
        pass
    return None


def _center_to_disk(key: str, coords: tuple[float, float]) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data[key] = [coords[0], coords[1]]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
