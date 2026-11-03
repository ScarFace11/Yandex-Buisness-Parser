"""Lead Score — 0..100 «насколько это горячий клиент для продажи сайта».

Шкала набирается ровно базовыми сигналами, без ВК: раньше шесть правил
давали 90 и последние 10 добирала активность сообщества, но её проверка
требует ключ. Без ключа идеальный лид упирался в 90 и выглядел хуже, чем
есть; с ключом тот же лид получал 100 — то есть цифра зависела от
настроек, а не от клиента. ВК оставлен в разборе справочно: на балл он
больше не влияет.

Критерия «недавно на Картах» здесь больше нет: дату добавления карточка не
отдаёт (`added_at` никогда не заполняется), поэтому критерий не срабатывал
ни разу, а в разборе постоянно висело «Дата добавления — нет данных».
"""
from .constants import EXPENSIVE_CATEGORY_KEYWORDS

# Веса подобраны под вопрос «кому нужен сайт и кто за него заплатит».
NO_WEBSITE = 35          # главный сигнал: своего сайта нет
RATING_GOOD = 15         # бизнес реальный, клиенты им довольны
REVIEWS_MANY = 15        # есть поток клиентов
HAS_PHONE = 10           # до него можно дозвониться
EXPENSIVE_CATEGORY = 10  # услуги дорогие — бюджет на сайт есть
SOCIALS_PRESENT = 15     # уже ведёт маркетинг: соцсети или мессенджер

# Сумма шести критериев = 100: идеальный лид добирает шкалу без ВК.
BASE_MAX = (NO_WEBSITE + RATING_GOOD + REVIEWS_MANY + HAS_PHONE
            + EXPENSIVE_CATEGORY + SOCIALS_PRESENT)
MAX_SCORE = 100

SOCIAL_FIELDS = ("vk", "telegram", "instagram", "whatsapp")

_AGGREGATORS = r"taplink|linktree|linktr\.ee|becons\.ai|illions\.app"


def has_own_website(record: dict) -> bool:
    """A link page (taplink) does not count as a website — same rule as the collection-time filter, so the score agrees with «Только без сайтов»."""
    import re
    site = (record.get("website") or record.get("aggregator_url") or "").strip()
    if not site:
        return False
    return not re.search(_AGGREGATORS, site, re.I)


def _num(value, default=0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _has_socials(record: dict) -> bool:
    return any(str(record.get(field) or "").strip() for field in SOCIAL_FIELDS)


def is_expensive_category(category: str) -> bool:
    low = (category or "").lower()
    return any(word in low for word in EXPENSIVE_CATEGORY_KEYWORDS)


def compute_score(record: dict) -> tuple[int, list[str]]:
    """Return (score, reasons) for one record."""
    score = 0
    reasons: list[str] = []

    if not has_own_website(record):
        score += NO_WEBSITE
        reasons.append(f"нет сайта +{NO_WEBSITE}")

    # Rating is stored on a 5-point scale; some sources return 0..50.
    rating = _num(record.get("rating"))
    if rating > 5:
        rating = rating / 10
    if rating >= 4.5:
        score += RATING_GOOD
        reasons.append(f"рейтинг {rating:g} +{RATING_GOOD}")

    reviews = _num(record.get("reviews_count"))
    if reviews >= 50:
        score += REVIEWS_MANY
        reasons.append(f"отзывов {int(reviews)} +{REVIEWS_MANY}")

    if (record.get("phone") or "").strip():
        score += HAS_PHONE
        reasons.append(f"есть телефон +{HAS_PHONE}")

    if is_expensive_category(record.get("category") or ""):
        score += EXPENSIVE_CATEGORY
        reasons.append(f"дорогая категория +{EXPENSIVE_CATEGORY}")

    # Соцсети и мессенджеры — один канал: Telegram есть в обоих списках, и
    # отдельный критерий давал второй балл за ту же ссылку. Пятёрка мессенджера
    # перешла сюда, сумма сигналов по-прежнему 100.
    if _has_socials(record):
        score += SOCIALS_PRESENT
        reasons.append(f"есть соцсети или мессенджер +{SOCIALS_PRESENT}")


    # ВК баллы больше не добавляет: шкала набирается без него. Строка в
    # разборе остаётся справочной, чтобы видеть, проверяли сообщество или нет.
    activity = (record.get("vk_activity") or "").lower()
    if activity == "active":
        reasons.append("ВК активен (на оценку не влияет)")
    elif activity == "semi":
        reasons.append("ВК полуактивен (на оценку не влияет)")

    return min(MAX_SCORE, score), reasons


def annotate_records(records: list[dict]) -> None:
    """Fill `lead_score` (and `lead_score_why`) in place."""
    for record in records:
        try:
            score, reasons = compute_score(record)
        except Exception:
            score, reasons = 0, []
        record["lead_score"] = score
        record["lead_score_why"] = ", ".join(reasons)
