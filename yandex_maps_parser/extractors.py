"""HTML / text extraction: social links, emails, descriptions, reviews."""
import json
import re
from html import unescape as _html_unescape

from .constants import (
    LINK_AGGREGATORS,
    SOCIAL_DOMAINS,
    EXCLUDE_URLS,
)
from . import state

# ── Compiled patterns ─────────────────────────────────────────

# Метки, которые площадки и Яндекс вешают на исходящие ссылки. `trackcode` — собственная метка Яндекс.Карт: без неё ссылка из карточки приходит вида «https://vk.ru/club?trackcode=4433fd7c…» и в выгрузке выглядит мусором.
_UTM_RE = re.compile(
    r'[?&](utm_\w+|ref|from|fbclid|gclid|yclid|ysclid|trackcode|erid|si|igshid)=[^&]*',
    re.I,
)
_TRAILING_RE = re.compile(r'[?&]$')

_VK_NON_PROFILE = re.compile(
    r'vk\.com/(wall|photo|video|album|doc|club(?=[?#])|app|feed|away|share|'
    r'login|join|invite|oauth|im|search|explore|fave|bookmarks)\b',
    re.I,
)
_IG_NON_PROFILE = re.compile(
    r'instagram\.com/(p|reel|tv|stories|explore|accounts|'
    r'ar|challenge|static|_n|sharer)\b',
    re.I,
)
_FB_NON_PROFILE = re.compile(
    r'facebook\.com/(permalink|share|dialog|plugins|login|photo|video|'
    r'events|groups(?=/[0-9])|pages/create|sharer|tr\b|ads\b|pixel|'
    r'watch|gaming|marketplace|policies|privacy|business|settings|recover|reg)\b',
    re.I,
)
_YOUTUBE_NON_PROFILE = re.compile(
    r'youtube\.com/(embed|watch|playlist|live|attribution_link|redirect|'
    r'howyoutubeworks|about|press|creators)\b',
    re.I,
)
_TIKTOK_NON_PROFILE = re.compile(
    r'tiktok\.com/(embed|discover|explore|trending|music|tag|share|upload|search)\b',
    re.I,
)
_OK_NON_PROFILE = re.compile(
    r'ok\.ru/(video|live|search|market|app|mail|feed|groups|sticker|emoji|dk)\b',
    re.I,
)
_TWITTER_NON_PROFILE = re.compile(
    r'(?:twitter|x\.com)/(intent|share|search|home|hashtag|explore|settings|'
    r'notifications|messages|compose|status|i/)\b',
    re.I,
)

# ── Блок контактов самой организации ──────────────────────────
_CONTACTS_SEC_RE = re.compile(
    r'<h[23][^>]*class="[^"]*card-section-header__title[^"]*"[^>]*>\s*Контакты\s*</h[23]>'
    r'.*?'
    # Конец секции: следующий заголовок раздела, скрипт (state страницы) или конец документа — дальше на странице уже чужие данные.
    r'(?=<h[23][^>]*class="[^"]*card-section-header__title|<script|</body>|$)',
    re.S,
)

# Ключи встроенных данных, которые описывают ЧУЖИЕ организации:
_FOREIGN_JSON_KEYS = frozenset({
    "competitor", "relatedadverts", "relatedplaces",
    "nearbyonmap", "nearbyoncard",
})


def _is_foreign_key(key) -> bool:
    return str(key).lower() in _FOREIGN_JSON_KEYS


def own_contacts_html(html: str) -> str:
    """Секция «Контакты» карточки — или пустая строка."""
    if not html:
        return ""
    m = _CONTACTS_SEC_RE.search(html)
    return m.group(0) if m else ""


_JSON_BLOB_RE = re.compile(
    r'(?:window\.(?:__)?(?:NUXT|INITIAL_STATE|SERVER_STATE|PRELOADED_STATE|'
    r'APP_STATE|REDUX_STATE|DATA|STATE)(?:__)?'
    r'|window\.serverState'
    # NOTE: whitespace is allowed on BOTH sides of the «=» — pages are not always minified (`window.__INITIAL_STATE__ = {` used to match nothing, so both the socials and the rating/reviews of such a page were lost).
    r'|<script[^>]+type=["\']application/ld\+json["\'][^>]*>'
    r'|<script[^>]+type=["\']application/json["\'][^>]*>)\s*[=]*\s*(\{)',
    re.I,
)

# Только явные признаки проверки Яндекса. Слова «robot» и «captcha»
# встречаются в обычных скриптах карточки (аналитика, настройки), и по ним
# хорошая страница ошибочно считалась антибот-заглушкой.
_ANTIBOT_MARKERS = (
    "showcaptcha", "smartcaptcha", "i-am-not-robot",
    "вы не робот", "похоже, вы робот",
    "access denied", "too many requests",
)


def is_antibot_html(html: str) -> bool:
    """Страница — проверка «Вы не робот?», а не карточка организации."""
    if not html:
        return False
    lower = html[:4000].lower()
    return any(marker in lower for marker in _ANTIBOT_MARKERS)

# Fast pre-check: does this string look like it could contain social URLs?
_HTTP_LIKE = re.compile(r'https?://[^\s"\'<>\\\\,}{]+', re.I)


# ── URL helpers ───────────────────────────────────────────────

def _is_aggregator(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        # Именно префикс «www.», а не набор символов: lstrip("www.") съедал
        # первую «w» у доменов из списка агрегаторов вроде wlo.link и
        # withkoji.com — они переставали считаться агрегаторами.
        if host.startswith("www."):
            host = host[len("www."):]
        return any(host == agg or host.endswith("." + agg) for agg in LINK_AGGREGATORS)
    except Exception:
        return False


def _clean_social_url(url: str) -> str:
    """Remove UTM / tracking parameters from a social URL."""
    url = _html_unescape(url or "")
    url = _UTM_RE.sub("", url)
    if "?" not in url:
        url = url.split("&", 1)[0]
    url = _TRAILING_RE.sub("", url)
    return url.rstrip("/.,);\"'")


def _normalize_social_url(platform: str, url: str) -> str | None:
    """Return a canonical profile URL, or None if the URL is not a profile."""
    from urllib.parse import urlparse, urlunparse
    try:
        parsed = urlparse(url)
        # Social pages are served over https; pages hand out plain http:// links and the exported column then looks untrustworthy/broken in Excel.
        if parsed.scheme == "http":
            parsed = parsed._replace(scheme="https")
        if platform == "vk":
            if _VK_NON_PROFILE.search(url):
                return None
            return urlunparse(parsed._replace(query="", fragment=""))
        if platform == "instagram":
            if _IG_NON_PROFILE.search(url):
                return None
            return urlunparse(parsed._replace(query="", fragment=""))
        if platform == "facebook":
            if _FB_NON_PROFILE.search(url):
                return None
            return urlunparse(parsed._replace(query="", fragment=""))
        if platform == "youtube":
            if _YOUTUBE_NON_PROFILE.search(url):
                return None
            return urlunparse(parsed._replace(query="", fragment=""))
        if platform == "tiktok":
            if _TIKTOK_NON_PROFILE.search(url):
                return None
            return urlunparse(parsed._replace(query="", fragment=""))
        if platform == "ok":
            if _OK_NON_PROFILE.search(url):
                return None
            return urlunparse(parsed._replace(query="", fragment=""))
        if platform == "twitter":
            if _TWITTER_NON_PROFILE.search(url):
                return None
            return urlunparse(parsed._replace(query="", fragment=""))
        if platform == "telegram":
            return urlunparse(parsed._replace(query="", fragment=""))
        return urlunparse(parsed._replace(fragment=""))
    except Exception:
        return url# ── Fetch ─────────────────────────────────────────────────────

def fetch_html(url: str, session=None, biz_id: str = "",
               force_refresh: bool = False) -> str:
    """Загрузить страницу карточки реальным браузером (CDP), с дисковым кэшем.

    `force_refresh` нужен режиму «Проверить старые»: он не должен отдавать
    вчерашнюю страницу из суточного кэша вместо свежих данных.
    """
    # Кэш страниц: повторный прогон не ждёт браузер на каждой карточке.
    if biz_id and not force_refresh:
        try:
            from .cache import get_cached
            cached = get_cached(biz_id)
            if cached:
                state.syslog(f"cache_hit: biz_id={biz_id}")
                return cached
        except Exception:
            pass

    from . import cdp_client
    text = ""
    try:
        text = cdp_client.fetch_page(url, biz_id=biz_id) or ""
    except Exception as exc:
        state.syslog(f"fetch_html: browser error: {type(exc).__name__}: {exc}")
        text = ""

    if not text:
        # Остановка/пропуск города — это не потерянная карточка: считать её в счётчике значило бы показать в итоге «не прочитано N» там, где пользователь сам прервал прогон.
        aborted = bool((state._STOP_EVENT and state._STOP_EVENT.is_set())
                       or state.is_skip_city())
        if aborted:
            return ""
        reason = ""
        try:
            reason = cdp_client.take_failure_reason()
        except Exception:
            reason = ""
        if reason not in state.READ_FAILURE_LABELS:
            reason = "no_page"
        state.syslog(f"fetch_html: gave up ({reason}): {url}")
        state.warn("Не удалось открыть карточку организации после нескольких попыток — "
                   "пропустили её и продолжили. На остальные записи это не влияет.")
        # Счётчик потерь: запись всё равно попадёт в выгрузку, и без этой цифры её «пустые контакты» выглядят как «так и есть».
        state.inc_read_failure(reason, key=biz_id or url)
        return ""

    if is_antibot_html(text):
        state.warn("Яндекс вернул anti-bot страницу — детали этой карточки пропущены.")
        state.inc_read_failure("antibot", key=biz_id or url)
        return ""

    if biz_id:
        try:
            from .cache import set_cached
            set_cached(biz_id, text)
        except Exception:
            pass
    return text


# ── Extractors ────────────────────────────────────────────────

# ── Разобранная страница ──────────────────────────────────────


class PageView:
    """Страница карточки, разобранная один раз: блобы JSON и секция контактов."""

    JSON_LIMIT = 200_000

    __slots__ = ("html", "head", "_blobs", "_contacts")

    def __init__(self, html: str):
        self.html = html or ""
        self.head = self.html[:self.JSON_LIMIT]
        self._blobs = None
        self._contacts = None

    def blobs(self) -> list:
        """Встроенные данные страницы (state-JSON, ld+json), уже разобранные."""
        if self._blobs is None:
            self._blobs = _blobs_in(self.head)
        return self._blobs

    def contacts(self) -> str:
        """Секция «Контакты» самой организации или пустая строка."""
        if self._contacts is None:
            self._contacts = own_contacts_html(self.html)
        return self._contacts


def view_of(html, view=None) -> "PageView":
    """Готовая PageView или новая — чтобы вызов с одной страницей не менялся."""
    return view if view is not None else PageView(html)


def _blobs_in(text: str) -> list:
    """Разобрать встроенные данные из куска HTML — в порядке появления."""
    objs = []
    if not text:
        return objs
    decoder = json.JSONDecoder()
    for m in _JSON_BLOB_RE.finditer(text):
        try:
            obj, _ = decoder.raw_decode(text, m.start(1))
        except (ValueError, json.JSONDecodeError):
            continue
        objs.append(obj)
    return objs


def _collect_url_strings(obj, depth: int = 0, limit: int = 200) -> list[str]:
    """Recursively collect string values that look like URLs from a decoded object."""
    out: list[str] = []

    def walk(o, d: int) -> None:
        if len(out) >= limit or d > 8:
            return
        if isinstance(o, str):
            if "http" in o:  # fast pre-check, avoids regex on non-URL strings
                out.append(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                if _is_foreign_key(k):
                    continue
                walk(v, d + 1)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v, d + 1)

    walk(obj, depth)
    return out


def _extract_from_json_blob(html: str = "", view=None) -> dict[str, str]:
    """Parse embedded JSON blobs in a Yandex Maps page and extract socials."""
    result: dict[str, str] = {}
    # Only the first 200KB, and only once per page — social links are always near the top (см.
    for obj in view_of(html, view).blobs():
        for url in _collect_url_strings(obj):
            url = _clean_social_url(url)
            if not url or EXCLUDE_URLS.search(url):
                continue
            for platform, pat in SOCIAL_DOMAINS.items():
                if platform not in result and pat.search(url):
                    normalized = _normalize_social_url(platform, url)
                    if normalized:
                        result[platform] = normalized
                    break
        if len(result) >= 3:
            break
    return result


_RATING_KEYS = ("ratingvalue", "rating", "score", "votesscore")
_REVIEWS_KEYS = ("reviewscount", "reviewscountvalue", "reviewcount", "reviews")


def _num(value):
    """Coerce a JSON value to float/int, or None when it is not numeric."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def _find_numbers(obj, keys, depth: int = 0):
    """Depth-first search for the first numeric value under any of `keys`."""
    if depth > 10 or obj is None:
        return None
    if isinstance(obj, dict):
        for key, value in obj.items():
            if _is_foreign_key(key):
                continue          # рейтинг похожей/соседней организации — чужой
            if str(key).lower() in keys:
                num = _num(value)
                if num is not None:
                    return num
                # `"rating": {"value": 4.5}` and `"reviews": {"count": 7}`
                if isinstance(value, dict):
                    for sub in ("value", "count", "countValue", "ratingValue"):
                        num = _num(value.get(sub))
                        if num is not None:
                            return num
        for key, value in obj.items():
            if _is_foreign_key(key):
                continue
            num = _find_numbers(value, keys, depth + 1)
            if num is not None:
                return num
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            num = _find_numbers(value, keys, depth + 1)
            if num is not None:
                return num
    return None


def extract_rating_reviews(html: str, view=None) -> tuple[object, object]:
    """Pull (rating, reviews_count) out of a Yandex Maps page, or ("", "")."""
    if not html:
        return "", ""
    rating = reviews = None
    for obj in view_of(html, view).blobs():
        if rating is None:
            rating = _find_numbers(obj, _RATING_KEYS)
        if reviews is None:
            reviews = _find_numbers(obj, _REVIEWS_KEYS)
        if rating is not None and reviews is not None:
            break
    # Ratings arrive on a 5-point scale, but some page builds embed a ×10 value (4.7 → 47).
    if rating is not None:
        if 5 < rating <= 50:
            rating = rating / 10
        if not 0 <= rating <= 5:
            rating = None
    rating_out = round(rating, 1) if rating else ""
    reviews_out = int(reviews) if reviews else ""
    return rating_out, reviews_out


def extract_socials(text: str, view=None) -> dict[str, str]:
    """Extract real social-profile links (URLs only — no fabrication from phone numbers or @mentions in arbitrary text)."""
    text = (view.contacts() if view is not None else own_contacts_html(text)) or text
    result: dict[str, str] = {}
    for url in _HTTP_LIKE.findall(text):
        url = _clean_social_url(url)
        if not url or EXCLUDE_URLS.search(url):
            continue
        for platform, pat in SOCIAL_DOMAINS.items():
            if platform not in result and pat.search(url):
                normalized = _normalize_social_url(platform, url)
                if normalized:
                    result[platform] = normalized
                break
    return result


# ── Телефон из карточки ──────────────────────────────────
_TEL_LINK_RE = re.compile(r'href=["\']tel:([+\d\s()\-]{7,25})["\']', re.I)
# Номер, как его рендерит блок контактов самой организации (<span dir="ltr" itemprop="telephone">+7 (913) 714-24-24</span>).
_TEL_ITEMPROP_RE = re.compile(r'itemprop=["\']telephone["\'][^>]*>([^<]{7,25})<', re.I)
# Scripts/styles are cut out before the loose text pass: otherwise any 11-digit number in the page state (a view counter, an id) reads as a phone.
_SCRIPT_BLOCK_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_PHONE_TEXT_RE = re.compile(
    r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
)


def _phone_digits(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def _format_phone(digits: str) -> str:
    """10/11 digits → «+7 XXX XXX-XX-XX»; anything else is not a phone. 8-800-X… hotlines («+7 800 …») are rejected: they are support lines of the platform or of a franchise head office, never the number to call the owner about a website."""
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) != 11 or digits[0] not in "78":
        return ""
    digits = "7" + digits[1:]
    if digits[1:4] == "800":
        return ""
    return f"+{digits[0]} {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:]}"


# Keys under which embedded page data carries a phone number.
_PHONE_KEYS = ("phone", "phonenumber", "phone_number", "telephone", "contactphone")


def _phone_from_json(value, depth: int = 0) -> str:
    """First phone-shaped value stored under a phone-ish key in embedded data."""
    if depth > 12 or value is None:
        return ""
    if isinstance(value, dict):
        for key, sub in value.items():
            if _is_foreign_key(key):
                continue          # телефон «похожей» организации — чужой
            if str(key).lower() not in _PHONE_KEYS:
                continue
            cand = sub
            if isinstance(cand, dict):
                cand = cand.get("value") or cand.get("text") or cand.get("number") or ""
            if isinstance(cand, (list, tuple)):
                cand = next((x for x in cand if isinstance(x, str)), "")
            if isinstance(cand, (int, float)):
                cand = str(cand)
            if isinstance(cand, str):
                phone = _format_phone(_phone_digits(cand))
                if phone:
                    return phone
        for key, sub in value.items():
            if _is_foreign_key(key):
                continue
            phone = _phone_from_json(sub, depth + 1)
            if phone:
                return phone
    elif isinstance(value, (list, tuple)):
        for sub in value:
            phone = _phone_from_json(sub, depth + 1)
            if phone:
                return phone
    return ""


# ── Сайт организации ─────────────────────────────────────────
_WEBSITE_KEYS = ("url", "site", "website", "siteurl", "domain")
_WEBSITE_LINK_RE = re.compile(
    r'href=["\'](https?://[^"\']+)["\'][^>]*>\s*(?:<[^>]+>)*[^<]{0,40}?Сайт',
    re.I,
)


def _is_own_website(url: str) -> bool:
    """True для сайта самой организации (не соцсеть, не агрегатор, не Яндекс)."""
    if not url or not url.lower().startswith("http"):
        return False
    low = url.lower()
    if EXCLUDE_URLS.search(low) or _is_aggregator(low):
        return False
    for pat in SOCIAL_DOMAINS.values():
        if pat.search(low):
            return False
    return True


def _site_link_in_page(html: str, view, accept) -> str:
    """Первая ссылка «Сайт» на странице карточки, проходящая фильтр ``accept``."""
    v = view_of(html, view)
    text = v.html or v.head
    for m in _WEBSITE_LINK_RE.finditer(text):
        cand = m.group(1).strip()
        if accept(cand):
            return _clean_social_url(cand)
    return ""


def _site_key_from_json(value, accept, depth: int = 0) -> str:
    """Первый URL под ключом url/site/website в данных страницы, проходящий accept."""
    if depth > 12 or value is None:
        return ""
    if isinstance(value, dict):
        for key, sub in value.items():
            if _is_foreign_key(key):
                continue
            if str(key).lower() not in _WEBSITE_KEYS:
                continue
            cand = sub
            if isinstance(cand, dict):
                cand = cand.get("value") or cand.get("text") or cand.get("url") or ""
            if isinstance(cand, (list, tuple)):
                cand = next((x for x in cand if isinstance(x, str)), "")
            if isinstance(cand, str) and accept(cand.strip()):
                return _clean_social_url(cand.strip())
        for key, sub in value.items():
            if _is_foreign_key(key):
                continue
            found = _site_key_from_json(sub, accept, depth + 1)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for sub in value:
            found = _site_key_from_json(sub, accept, depth + 1)
            if found:
                return found
    return ""


def extract_website(html: str, view=None) -> str:
    """Сайт организации со страницы карточки — или "" (если сайта нет)."""
    if not html:
        return ""
    # 1. Блок контактов: ссылка рядом со словом «Сайт» — самый надёжный сигнал.
    found = _site_link_in_page(html, view, _is_own_website)
    if found:
        return found

    # 2. Данные страницы: url/site/website с настоящим адресом организации.
    for obj in view_of(html, view).blobs():
        found = _site_key_from_json(obj, _is_own_website)
        if found:
            return found
    return ""


def extract_aggregator(html: str, view=None) -> str:
    """Ссылка-витрина (taplink/linktree) из карточки — или ""."""
    if not html:
        return ""
    found = _site_link_in_page(html, view, _is_aggregator)
    if found:
        return found
    for obj in view_of(html, view).blobs():
        found = _site_key_from_json(obj, _is_aggregator)
        if found:
            return found
    return ""


def extract_phone(html: str, view=None) -> str:
    """Первый настоящий телефон со страницы карточки — или ""."""
    if not html:
        return ""
    section = view.contacts() if view is not None else own_contacts_html(html)
    text = section if section else (view.head if view is not None else html[:200_000])
    for m in _TEL_ITEMPROP_RE.finditer(text):
        phone = _format_phone(_phone_digits(m.group(1)))
        if phone:
            return phone
    for m in _TEL_LINK_RE.finditer(text):
        phone = _format_phone(_phone_digits(m.group(1)))
        if phone:
            return phone
    # Данные страницы: в секции контактов своего JSON нет (она кончается на `<script`), поэтому берётся либо своя секция, либо начало страницы — ровно как раньше, только разобранное один раз.
    for obj in (_blobs_in(section) if section else view_of(html, view).blobs()):
        phone = _phone_from_json(obj)
        if phone:
            return phone
    for m in _PHONE_TEXT_RE.finditer(_SCRIPT_BLOCK_RE.sub(" ", text)):
        phone = _format_phone(_phone_digits(m.group(0)))
        if phone:
            return phone
    return ""


# ── Дополнительные поля карточки ─────────────────────────────

_EMAIL_RE = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+")
_EMAIL_KEYS = ("email", "emails", "mail", "contactemail", "emailaddress")
_HOURS_KEYS = ("hours", "workinghours", "openinghours", "schedule", "timetable")
_DESCRIPTION_KEYS = ("description", "shortdescription", "about", "summary")
_SERVICES_KEYS = ("services", "goods", "products", "features", "offers")
_STATUS_KEYS = ("closed", "isclosed", "temporarilyclosed", "temporaryclosed")


def _plain_text(fragment: str) -> str:
    """HTML-фрагмент → одна читаемая строка."""
    text = re.sub(r"<br\s*/?>", ", ", fragment or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html_unescape(text)
    return re.sub(r"\s+", " ", text).strip(" ,;")


def _json_strings(value, keys, depth: int = 0) -> list[str]:
    """Строки/списки под ключами `keys`, кроме чужих организаций."""
    if depth > 12 or value is None:
        return []
    found: list[str] = []
    if isinstance(value, dict):
        for key, sub in value.items():
            if _is_foreign_key(key):
                continue
            if str(key).lower() in keys:
                if isinstance(sub, str) and sub.strip():
                    found.append(sub.strip())
                elif isinstance(sub, (list, tuple)):
                    for item in sub:
                        if isinstance(item, str) and item.strip():
                            found.append(item.strip())
                        elif isinstance(item, dict):
                            for k in ("name", "title", "text", "value"):
                                if isinstance(item.get(k), str) and item[k].strip():
                                    found.append(item[k].strip())
                                    break
                elif isinstance(sub, dict):
                    for k in ("text", "name", "value", "title"):
                        if isinstance(sub.get(k), str) and sub[k].strip():
                            found.append(sub[k].strip())
                            break
            found.extend(_json_strings(sub, keys, depth + 1))
    elif isinstance(value, (list, tuple)):
        for sub in value:
            found.extend(_json_strings(sub, keys, depth + 1))
    return found


def _uniq(values) -> list[str]:
    out: list[str] = []
    for value in values:
        value = str(value or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def extract_phones(html: str, view=None) -> list[str]:
    """Все телефоны организации со страницы, в порядке появления."""
    if not html:
        return []
    v = view_of(html, view)
    section = v.contacts()
    text = section or v.head
    phones: list[str] = []
    for m in _TEL_ITEMPROP_RE.finditer(text):
        phone = _format_phone(_phone_digits(m.group(1)))
        if phone:
            phones.append(phone)
    for m in _TEL_LINK_RE.finditer(text):
        phone = _format_phone(_phone_digits(m.group(1)))
        if phone:
            phones.append(phone)
    # Блобы страницы уже разобраны один раз в PageView: повторный
    # _blobs_in(section) ломал обещание extract_page «один разбор на карточку».
    for obj in v.blobs():
        for key in _PHONE_KEYS:
            for raw in _json_strings(obj, {key}):
                phone = _format_phone(_phone_digits(raw))
                if phone:
                    phones.append(phone)
    for m in _PHONE_TEXT_RE.finditer(_SCRIPT_BLOCK_RE.sub(" ", text)):
        phone = _format_phone(_phone_digits(m.group(0)))
        if phone:
            phones.append(phone)
    return _uniq(phones)


def extract_email(html: str, view=None) -> str:
    """Email организации; чужие адреса и служебные ящики не берём."""
    if not html:
        return ""
    v = view_of(html, view)
    section = v.contacts()
    text = section or v.head
    emails: list[str] = []
    for m in re.finditer(r'mailto:([^"\'<>?\s]+)', text, re.I):
        emails.append(_html_unescape(m.group(1)).strip())
    emails.extend(_EMAIL_RE.findall(_plain_text(text)))
    for obj in v.blobs():
        emails.extend(_json_strings(obj, _EMAIL_KEYS))
    clean: list[str] = []
    for email in emails:
        email = email.lower().strip(".,;")
        if not _EMAIL_RE.fullmatch(email):
            continue
        # Поддержка площадки/франшизы — не контакт владельца.
        if any(x in email for x in ("yandex", "support", "example.", "noreply", "no-reply")):
            continue
        if email not in clean:
            clean.append(email)
    return ", ".join(clean)


def extract_hours(html: str, view=None) -> str:
    """Режим работы карточки, если он есть в разметке или данных страницы."""
    if not html:
        return ""
    v = view_of(html, view)
    for m in re.finditer(r'itemprop=["\']openingHours["\'][^>]*(?:content=["\']([^"\']+)["\']|>([^<]{2,120})<)', v.html, re.I):
        value = _plain_text(m.group(1) or m.group(2) or "")
        if value:
            return value
    for m in re.finditer(r'<[^>]+class="[^"]*(?:working|hours|schedule)[^"]*"[^>]*>(.*?)</(?:div|span|p)>', v.html, re.I | re.S):
        value = _plain_text(m.group(1))
        if 3 <= len(value) <= 300:
            return value
    for obj in v.blobs():
        for value in _json_strings(obj, _HOURS_KEYS):
            value = _plain_text(value)
            if 3 <= len(value) <= 300:
                return value
    text = _plain_text(_SCRIPT_BLOCK_RE.sub(" ", v.html))
    m = re.search(r"(?:Время|Режим) работы\s*[:—-]?\s*([^|]{3,120})", text, re.I)
    return m.group(1).strip(" ,;") if m else ""


def extract_description(html: str, view=None) -> str:
    """Короткое описание организации (до 500 символов)."""
    if not html:
        return ""
    for obj in view_of(html, view).blobs():
        for value in _json_strings(obj, _DESCRIPTION_KEYS):
            value = _plain_text(value)
            if len(value) >= 12:
                return value[:500]
    return ""


def extract_services(html: str, view=None) -> str:
    """Услуги/товары/цены из встроенных данных — по одной строке."""
    if not html:
        return ""
    values: list[str] = []
    for obj in view_of(html, view).blobs():
        for value in _json_strings(obj, _SERVICES_KEYS):
            value = _plain_text(value)
            if 2 <= len(value) <= 120:
                values.append(value)
    return ", ".join(_uniq(values)[:40])


def _json_true(value, keys, depth: int = 0) -> bool:
    """Есть ли под одним из `keys` явное true (JSON-флаг закрытия)."""
    if depth > 12 or value is None:
        return False
    if isinstance(value, dict):
        for key, sub in value.items():
            if _is_foreign_key(key):
                continue
            if str(key).lower() in keys:
                if sub is True or str(sub).strip().lower() in ("true", "1", "yes"):
                    return True
            if _json_true(sub, keys, depth + 1):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_json_true(sub, keys, depth + 1) for sub in value)
    return False


def extract_status(html: str, view=None) -> str:
    """«Временно закрыто» / «Закрыто» — только явный признак со страницы."""
    if not html:
        return ""
    for obj in view_of(html, view).blobs():
        for key in _STATUS_KEYS:
            if _json_true(obj, {key}):
                return "Временно закрыто" if "tempor" in key or "врем" in key else "Закрыто"
    low = view_of(html, view).head.lower()
    if "временно закрыт" in low:
        return "Временно закрыто"
    if re.search(r"(?:^|>)\s*закрыто\s*(?:<|$)", low):
        return "Закрыто"
    return ""


# ── Всё, что нужно от страницы, за один разбор ─────────────────

def extract_page(html: str, *, socials: bool = True, rating: bool = True,
                 phone: bool = True, website: bool = True,
                 aggregator: bool = True, details: bool = True) -> dict:
    """Собрать с карточки всё сразу, разобрав страницу ОДИН раз."""
    view = PageView(html)
    out: dict = {"socials_json": {}, "socials_contacts": {},
                 "rating": "", "reviews": "", "phone": "", "phones": [],
                 "website": "", "aggregator": "", "email": "", "hours": "",
                 "description": "", "services": "", "status": ""}
    if not html:
        return out
    if socials:
        out["socials_json"] = _extract_from_json_blob(view=view)
        out["socials_contacts"] = extract_socials(html, view=view)
    if rating:
        out["rating"], out["reviews"] = extract_rating_reviews(html, view=view)
    if phone:
        out["phones"] = extract_phones(html, view=view)
        out["phone"] = out["phones"][0] if out["phones"] else ""
    if website:
        out["website"] = extract_website(html, view=view)
    if aggregator:
        out["aggregator"] = extract_aggregator(html, view=view)
    if details:
        out["email"] = extract_email(html, view=view)
        out["hours"] = extract_hours(html, view=view)
        out["description"] = extract_description(html, view=view)
        out["services"] = extract_services(html, view=view)
        out["status"] = extract_status(html, view=view)
    return out


