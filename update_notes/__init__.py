"""Тексты обновлений в одном месте, без правок в коде.

Заметка версии — отдельный файл `notes/<версия>.json`:

    {
      "version": "2.3.5",
      "date": "2026-10-25",
      "title": "Установщик Windows и история изменений",
      "summary": "Краткое описание в одну строку.",
      "items": [{"title": "Что изменилось", "text": "Подробности."}]
    }

`summary` — короткая строка (видна в баннере и списке версий),
`items` — полный текст, который открывается по нажатию на версию.
Подписи интерфейса — в `ui.json`, рядом.

Всё это уезжает в `static/version.json` при штамповке версии (см.
scripts/stamp_version.py), поэтому клиент видит краткое описание
новой версии ещё до установки.
"""
from __future__ import annotations

import json
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
NOTES_DIR = PACKAGE_DIR / "notes"
UI_FILE = PACKAGE_DIR / "ui.json"
HISTORY_LIMIT = 8


def _version_key(version: str) -> tuple[int, ...]:
    """2.3.4.2 -> (2, 3, 4, 2): сравниваем по числам, а не по строкам."""
    parts = []
    for chunk in str(version or "").split("."):
        chunk = chunk.strip()
        if chunk.isdigit():
            parts.append(int(chunk))
    return tuple(parts)


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _entry(raw: dict, version: str) -> dict:
    items = []
    for item in raw.get("items") or []:
        if isinstance(item, str):
            items.append({"title": "", "text": item})
            continue
        if not isinstance(item, dict):
            continue
        items.append({
            "title": str(item.get("title") or ""),
            "text": str(item.get("text") or ""),
        })
    return {
        "version": str(raw.get("version") or version),
        "date": str(raw.get("date") or ""),
        "title": str(raw.get("title") or ""),
        "summary": str(raw.get("summary") or ""),
        "items": [i for i in items if i["text"]],
    }


def releases() -> list:
    """Все версии из папки notes, свежие первыми."""
    if not NOTES_DIR.is_dir():
        return []
    out = []
    for path in sorted(NOTES_DIR.glob("*.json")):
        entry = _entry(_read(path), path.stem)
        if entry["version"]:
            out.append(entry)
    out.sort(key=lambda r: _version_key(r["version"]), reverse=True)
    return out


def find(version: str) -> dict:
    """Заметка версии (пустая запись, если её нет в этой сборке)."""
    version = str(version or "").strip()
    for entry in releases():
        if entry["version"] == version:
            return entry
    return {}


def latest() -> dict:
    all_entries = releases()
    return all_entries[0] if all_entries else {}


def summary(version: str) -> str:
    return find(version).get("summary", "")


def texts() -> dict:
    """Подписи окна «Что нового» и баннера: пустой файл — пустые строки."""
    return _read(UI_FILE)


def payload(limit: int = HISTORY_LIMIT) -> dict:
    """То, что уезжает в version.json и отдаётся в /update/changelog."""
    history = releases()[:max(1, int(limit or HISTORY_LIMIT))]
    newest = history[0] if history else {}
    return {
        "version": newest.get("version", ""),
        "changelog": newest.get("summary", ""),
        "history": history,
        "texts": texts(),
    }
