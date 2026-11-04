"""Поиск организаций в Яндекс.Картах — через настоящий браузер (CDP)."""
import random
import threading
import time

from . import state
from . import browser_search
from .browser_search import harvest_cards, harvest_cards_ex

_PAGE_SIZE = 25           # Яндекс отдаёт 25 карточек на страницу выдачи
_HARVEST_CACHE_MAX = 8    # сколько выдач держать в памяти (query+точка)

# В кэше храним не только карточки, но и состояние выдачи: неполный сбор
# нельзя запоминать на весь прогон, иначе одна неудача навсегда оставит
# точку недобранной.
_harvest_cache: dict[tuple, dict] = {}
_cache_lock = threading.Lock()


def search_failure_hint(reason: str = "") -> str:
    """Человеческое объяснение пустой выдачи."""
    if reason == "captcha" or browser_search.blocked_reason() == "captcha":
        return ("Яндекс показал проверку «Вы не робот?» вместо выдачи — браузер "
                "и интернет тут ни при чём. Проверка включается на подозрительные "
                "запросы: повторите поиск через несколько минут.")
    if reason == "no_page":
        return ("Страница выдачи не открылась. Проверьте, что браузер "
                "запускается (вкладка «🩺 Диагностика») и есть доступ в интернет.")
    return ("Яндекс не показал ни одной организации. Если их действительно нет — "
            "измените запрос; если нет — проверьте браузер и интернет во вкладке "
            "«🩺 Диагностика».")


def _cache_key(query: str, lat: float, lon: float) -> tuple:
    return (query.strip().lower(), round(float(lat), 3), round(float(lon), 3))


def _remember(key: tuple, info: dict) -> None:
    with _cache_lock:
        _harvest_cache[key] = info
        if len(_harvest_cache) > _HARVEST_CACHE_MAX:
            for old in list(_harvest_cache)[:-_HARVEST_CACHE_MAX]:
                _harvest_cache.pop(old, None)


def _harvest(query: str, city: str, lat: float, lon: float) -> dict:
    """Выдача для (query, точка) — с кэшем только завершённого сбора."""
    key = _cache_key(query, lat, lon)
    with _cache_lock:
        cached = _harvest_cache.get(key)
    if cached is not None:
        return cached

    want = max(_PAGE_SIZE, min(int(getattr(state, "MAX_PAGES", 1) or 1) * _PAGE_SIZE,
                               browser_search._MAX_CARDS))
    attempts = max(1, int(getattr(state, "RETRY_COUNT", 3) or 1))
    base_delay = max(0.0, float(getattr(state, "RETRY_DELAY", 1.0) or 0.0))
    info = harvest_cards_ex(query, city, lat, lon, max_cards=want)

    # Капчу и осознанно пустую выдачу не повторяем: первая только усугубится,
    # вторая не изменится. Повтор нужен, когда страница не открылась или
    # сбор оборвался на середине.
    for attempt in range(1, attempts):
        if info.get("status") not in ("no_state", "partial"):
            break
        if state._STOP_EVENT and state._STOP_EVENT.is_set():
            break
        delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
        state.syslog(f"search retry {attempt}/{attempts - 1}: {query!r} "
                     f"({info.get('status')}), пауза {delay:.1f}s")
        time.sleep(delay)
        info = harvest_cards_ex(query, city, lat, lon, max_cards=want)

    if info.get("complete") and info.get("status") in ("ok", "empty"):
        _remember(key, info)
    return info


def search_page(
    query: str, city: str, lat: float, lon: float, skip: int, session=None,
    with_status: bool = False,
):
    """Одна «страница» выдачи Яндекс.Карт для (query, точка).

    Возвращает `(features, total)` или `(features, total, info)`, если нужен
    статус: `ok` / `empty` / `no_state` / `partial` / `blocked`.
    """
    if state._STOP_EVENT and state._STOP_EVENT.is_set():
        return ([], None, {"status": "stopped", "cards": [], "total": None,
                           "complete": False}) if with_status else ([], None)
    if state.is_skip_city():
        return ([], None, {"status": "stopped", "cards": [], "total": None,
                           "complete": False}) if with_status else ([], None)

    info = _harvest(query, city, lat, lon)
    cards = info.get("cards") or []
    total = info.get("total")
    if total is None and cards:
        total = len(cards)
    if not cards:
        status = info.get("status") or "no_state"
        blocked = browser_search.blocked_reason()
        if blocked or status == "blocked":
            # Один раз на прогон: иначе каждый город и запрос повторял бы то же
            # самое, и в «Важных» было бы двадцать одинаковых строк.
            if not getattr(state, "SEARCH_BLOCKED", ""):
                state.SEARCH_BLOCKED = blocked or "captcha"
                state.warn(search_failure_hint("captcha"))
            state.tech(f"search: Яндекс показал проверку вместо выдачи ({blocked or 'captcha'})")
        elif status in ("no_state", "partial"):
            if not getattr(state, "SEARCH_PAGE_FAILED", False):
                state.SEARCH_PAGE_FAILED = True
                state.warn(search_failure_hint("no_page"))
            state.tech(f"search: страница выдачи не открылась ({status})")
        else:
            # Пустая выдача — это ответ Яндекса, а не сбой: не пугаем
            # пользователя советом про браузер и интернет.
            state.tech("search: Яндекс вернул пустую выдачу (организаций нет)")
        return ([], total, info) if with_status else ([], total)

    chunk = cards[skip:skip + _PAGE_SIZE]
    features = [_card_feature(card) for card in chunk]
    return (features, total, info) if with_status else (features, total)


def _card_feature(card: dict) -> dict:
    """Карточка выдачи → GeoJSON-фича в формате прежнего Search API."""
    lat, lon = card.get("lat") or "", card.get("lon") or ""
    coords: list[float] = []
    try:
        coords = [float(lon), float(lat)]
    except (TypeError, ValueError):
        coords = []

    categories = [{"name": part.strip()} for part in str(card.get("category") or "").split(",") if part.strip()]
    meta = {
        "id": card.get("_biz_id", ""),
        "name": card.get("name", ""),
        "address": card.get("address", ""),
        # Сайт в выдаче не показывается — он выяснится на карточке организации (см. extractors.extract_website и фильтр в enrichment).
        "url": "",
        "rating": card.get("rating", ""),
        "reviews_count": card.get("reviews_count", ""),
        "Categories": categories,
    }
    return {"properties": {"CompanyMetaData": meta}, "geometry": {"coordinates": coords}}


def parse_feature(feature: dict, query: str) -> dict | None:
    """Convert a feature (DOM-карточка Яндекс.Карт) into a candidate record."""
    from .extractors import _is_aggregator

    props = feature.get("properties", {})
    meta  = props.get("CompanyMetaData", {})

    name = str(meta.get("name", "")).strip()
    if not name:
        return None

    raw_url    = str(meta.get("url", "")).strip()
    aggregator = ""

    if raw_url and _is_aggregator(raw_url):
        aggregator = raw_url

    # Parse mode "without_website": выдача не сообщает сайт, поэтому решение принимается на карточке организации (enrichment → extract_website): запись с сайтом отбрасывается уже после загрузки карточки.
    if state.PARSE_MODE == "without_website" and raw_url and not aggregator:
        return None

    coords = feature.get("geometry", {}).get("coordinates", [])
    phones = ", ".join(
        p.get("formatted") or p.get("number", "")
        for p in meta.get("Phones", [])
        if p.get("formatted") or p.get("number")
    )
    biz_id = str(meta.get("id", ""))

    return {
        "_biz_id":       biz_id,
        "_raw_feature":  feature,
        "_aggregator_url": aggregator,
        # Сайт в выдаче неизвестен → проверить его на карточке организации.
        "_site_unknown": not raw_url,
        "reviewed":      "",
        "name":          name,
        "category":      ", ".join(c.get("name", "") for c in meta.get("Categories", [])),
        "address":       meta.get("address", ""),
        "phone":         phones,
        # Рейтинг и отзывы видны прямо в выдаче (раньше приходили только с карточки — теперь экономим запросы).
        "rating":        meta.get("rating", ""),
        "reviews_count": meta.get("reviews_count", ""),
        "aggregator_url": aggregator,
        "lat":           coords[1] if len(coords) > 1 else "",
        "lon":           coords[0] if len(coords) > 1 else "",
        "yandex_maps_url": f"https://yandex.ru/maps/org/{biz_id}" if biz_id else "",
        "query":         query,
    }
