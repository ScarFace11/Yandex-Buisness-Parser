# -*- coding: utf-8 -*-
"""Сферы бизнеса: готовые наборы запросов к Яндекс.Картам.

Каталог можно править из интерфейса: имя сферы и её слова сохраняются
в spheres.json рядом с настройками и главнее встроенного набора.
"""
import json
import os
import re
import uuid

# Каждый набор — слова, с которыми Яндекс.Карты находят организации этой сферы.
SPHERES: tuple[dict, ...] = (
    {"id": "cafe", "name": "Кафе и кофейни", "icon": "☕",
     "queries": ("кафе", "кофейня")},
    {"id": "restaurant", "name": "Рестораны", "icon": "🍽",
     "queries": ("ресторан",)},
    {"id": "bar", "name": "Бары и пабы", "icon": "🍺",
     "queries": ("бар", "паб")},
    {"id": "pizza", "name": "Пиццерии", "icon": "🍕",
     "queries": ("пиццерия", "пицца")},
    {"id": "sushi", "name": "Суши и роллы", "icon": "🍣",
     "queries": ("суши", "роллы")},
    {"id": "bakery", "name": "Пекарни", "icon": "🥖",
     "queries": ("пекарня", "хлеб")},
    {"id": "cake", "name": "Кондитерские", "icon": "🎂",
     "queries": ("кондитерская", "торты")},
    {"id": "hookah", "name": "Кальянные", "icon": "💨",
     "queries": ("кальянная",)},
    {"id": "delivery", "name": "Доставка еды", "icon": "🛵",
     "queries": ("доставка еды",)},
    {"id": "hair", "name": "Парикмахерские", "icon": "✂️",
     "queries": ("парикмахерская", "барбершоп")},
    {"id": "beauty", "name": "Салоны красоты", "icon": "💅",
     "queries": ("салон красоты", "маникюр", "ногтевая студия")},
    {"id": "massage", "name": "Массаж и спа", "icon": "💆",
     "queries": ("массаж", "спа")},
    {"id": "dental", "name": "Стоматология", "icon": "🦷",
     "queries": ("стоматология", "зубной врач")},
    {"id": "clinic", "name": "Медицинские центры", "icon": "🏥",
     "queries": ("медицинский центр", "клиника")},
    {"id": "auto", "name": "Автосервисы", "icon": "🔧",
     "queries": ("автосервис", "шиномонтаж")},
    {"id": "carwash", "name": "Автомойки", "icon": "🚿",
     "queries": ("автомойка",)},
    {"id": "fitness", "name": "Фитнес-клубы", "icon": "🏋️",
     "queries": ("фитнес", "тренажёрный зал")},
    {"id": "yoga", "name": "Йога и растяжка", "icon": "🧘",
     "queries": ("йога",)},
    {"id": "vet", "name": "Ветеринарные клиники", "icon": "🐾",
     "queries": ("ветклиника", "ветеринарная клиника")},
    {"id": "hotel", "name": "Гостиницы и отели", "icon": "🏨",
     "queries": ("гостиница", "отель", "хостел")},
    {"id": "flowers", "name": "Цветочные магазины", "icon": "💐",
     "queries": ("цветочный магазин", "цветы")},
    {"id": "furniture", "name": "Мебель", "icon": "🛋",
     "queries": ("мебель", "мебельный магазин")},
    {"id": "building", "name": "Стройматериалы", "icon": "🧱",
     "queries": ("стройматериалы",)},
    {"id": "renovation", "name": "Ремонт квартир", "icon": "🛠",
     "queries": ("ремонт квартир",)},
    {"id": "legal", "name": "Юридические услуги", "icon": "⚖️",
     "queries": ("юрист", "юридическая консультация")},
    {"id": "accounting", "name": "Бухгалтерские услуги", "icon": "📊",
     "queries": ("бухгалтерские услуги", "бухгалтер")},
    {"id": "estate", "name": "Недвижимость", "icon": "🏠",
     "queries": ("агентство недвижимости",)},
    {"id": "photo", "name": "Фотостудии", "icon": "📷",
     "queries": ("фотостудия", "фотограф")},
    {"id": "kids", "name": "Детские центры", "icon": "🧸",
     "queries": ("детский центр", "детский сад")},
    {"id": "tutors", "name": "Репетиторы", "icon": "📚",
     "queries": ("репетитор",)},
)


def _norm(text: str) -> str:
    """Запрос к виду для сравнения: регистр, «ё», лишние пробелы."""
    return " ".join(str(text or "").lower().replace("ё", "е").split())


# ── Каталог, отредактированный пользователем ────────────────────
# Сферы правятся в окне «Сферы»: название и слова. Файл лежит рядом с
# настройками, а не в сборке: правки переживают обновление приложения.
_CUSTOM_FILE = "spheres.json"
_ID_OK = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def _custom_path() -> str | None:
    """Где лежит отредактированный каталог (None — писать некуда)."""
    try:
        import paths
        return os.path.join(str(paths.user_dir()), _CUSTOM_FILE)
    except Exception:
        return None


def clean_query(text) -> str:
    """Слово в том виде, в каком его отправим в поиск."""
    return " ".join(str(text or "").lower().split())


def clean_item(raw, used_ids: set[str]) -> dict | None:
    """Одна сфера из интерфейса → запись каталога (None — мусор)."""
    if not isinstance(raw, dict):
        return None
    name = " ".join(str(raw.get("name") or "").split())
    words: list[str] = []
    for q in (raw.get("queries") or []):
        text = clean_query(q)
        if text and text not in words:
            words.append(text)
    if not name or not words:
        return None
    sphere_id = str(raw.get("id") or "").strip().lower()
    if not _ID_OK.match(sphere_id) or sphere_id in used_ids:
        sphere_id = "custom-" + uuid.uuid4().hex[:8]
    used_ids.add(sphere_id)
    icon = str(raw.get("icon") or "").strip()
    return {"id": sphere_id, "name": name, "icon": icon[:8] or "•",
            "queries": words}


def load_custom() -> list[dict] | None:
    """Каталог из файла правок; None — пользователь его не менял."""
    path = _custom_path()
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    items: list[dict] = []
    used: set[str] = set()
    for raw in data if isinstance(data, list) else []:
        item = clean_item(raw, used)
        if item:
            items.append(item)
    return items or None


def save_custom(items) -> list[dict]:
    """Сохранить каталог, отредактированный в окне «Сферы» (атомарно)."""
    cleaned: list[dict] = []
    used: set[str] = set()
    for raw in items or []:
        item = clean_item(raw, used)
        if item:
            cleaned.append(item)
    if not cleaned:
        raise ValueError("оставьте хотя бы одну сферу с названием и словами")
    path = _custom_path()
    if not path:
        raise RuntimeError("некуда сохранить каталог сфер")
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cleaned, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return cleaned


def reset_custom() -> None:
    """Вернуть стандартный каталог (удалить файл правок)."""
    path = _custom_path()
    if path and os.path.exists(path):
        os.remove(path)


def _builtin() -> list[dict]:
    return [
        {"id": s["id"], "name": s["name"], "icon": s["icon"],
         "queries": list(s["queries"])}
        for s in SPHERES
    ]


def catalog() -> list[dict]:
    """Сферы для интерфейса: правки пользователя, иначе стандартные."""
    return load_custom() or _builtin()


def _best_sphere(queries, spheres) -> dict | None:
    """Сфера с наибольшим пересечением слов; list сфер передаётся готовым,
    чтобы сводка истории не перечитывала каталог на каждую запись."""
    wanted = {_norm(q) for q in (queries or []) if _norm(q)}
    if not wanted:
        return None
    best = None
    best_score = 0
    for sphere in spheres:
        score = len(wanted & {_norm(q) for q in sphere["queries"]})
        if score > best_score:
            best, best_score = sphere, score
    return best

def sphere_for_queries(queries) -> dict | None:
    """Какая сфера описывает этот набор запросов (None — не наша сфера)."""
    return _best_sphere(queries, catalog())

def match_text(queries) -> str:
    """Подпись сферы для запроса истории — пустая строка, если сфера не наша."""
    sphere = sphere_for_queries(queries)
    return sphere["name"] if sphere else ""


def history_summary(entries) -> list[dict]:
    """Сводка истории по сферам: когда, где и сколько раз парсили. *entries* — то, что отдаёт search_history.get_history() (сначала новые)."""
    spheres_now = catalog()
    by_id: dict[str, dict] = {}
    all_cities: dict[str, set[str]] = {}
    for entry in entries or []:
        sphere = _best_sphere(entry.get("queries") or [], spheres_now)
        if sphere is None:
            continue
        item = by_id.setdefault(sphere["id"], {
            "id": sphere["id"],
            "last_ts": 0,
            "cities": [],
            "cities_total": 0,
            "runs": 0,
            "results": 0,
            "queries": [],
        })
        seen = all_cities.setdefault(sphere["id"], set())
        ts = float(entry.get("timestamp") or 0)
        item["runs"] += 1
        item["results"] += int(entry.get("results_count") or 0)
        # История уже отсортирована: первый раз, когда сфера встретилась, — её последний запуск.
        if not item["last_ts"]:
            item["last_ts"] = ts
            item["queries"] = [q for q in (entry.get("queries") or []) if str(q).strip()]
        for city in entry.get("cities") or []:
            name = str(city or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            if len(item["cities"]) < 5:
                item["cities"].append(name)
    for sphere_id, item in by_id.items():
        # Полное число городов: список обрезан для читаемости, но "+N" должен быть честным, а не терять остальные города молча.
        item["cities_total"] = len(all_cities.get(sphere_id) or ())
    return list(by_id.values())
