"""Checkpoint / resume: save and restore parser progress across runs."""
import json
import os

from . import state


def _ckpt_path(base: str) -> str:
    return os.path.join(state.OUTPUT_DIR, f"{base}.checkpoint.json")


def load_checkpoint(base: str) -> dict:
    path = _ckpt_path(base)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            seen  = set(data.get("seen_urls", []))
            done  = {(c["query"], c["lat"], c["lon"]) for c in data.get("completed", [])}
            failed = set(data.get("failed_urls", []))
            state.info(f"  Checkpoint: {len(seen)} ранее найденных, {len(done)} точек уже обработано"
                       + (f", {len(failed)} карточек ждут повтора." if failed else "."))
            return {"seen_urls": seen, "completed": done, "failed_urls": failed}
        except Exception:
            pass
    return {"seen_urls": set(), "completed": set(), "failed_urls": set()}


def save_checkpoint(base: str, seen_urls: set[str], completed: set[tuple],
                    failed_urls: set[str] | None = None) -> None:
    from datetime import datetime
    path = _ckpt_path(base)
    os.makedirs(state.OUTPUT_DIR, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "seen_urls": list(seen_urls),
                    "completed": [
                        {"query": q, "lat": lat, "lon": lon}
                        for q, lat, lon in completed
                    ],
                    # Seen ≠ processed: карточка, которую не удалось прочитать,
                    # остаётся здесь и будет повторена при следующем запуске.
                    "failed_urls": list(failed_urls or ()),
                    "saved_at": datetime.now().isoformat(),
                },
                f,
                ensure_ascii=False,
            )
    except Exception:
        pass


def clear_checkpoint(base: str) -> None:
    path = _ckpt_path(base)
    if os.path.exists(path):
        os.remove(path)


# ── Global seen-store ─────────────────────────────────────────

def _global_seen_path() -> str:
    return os.path.join(state.OUTPUT_DIR, "_seen.json")


def load_global_seen() -> set[str]:
    return set(load_global_seen_dates())


def load_global_seen_dates() -> dict[str, str]:
    """UID → дата последней успешной обработки (старый формат — без дат)."""
    path = _global_seen_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            at = data.get("seen_at") or {}
            if isinstance(at, dict) and at:
                return {str(k): str(v) for k, v in at.items() if k}
            # Старый _seen.json хранил только список: считаем даты неизвестными.
            return {str(uid): "" for uid in data.get("seen_urls", [])}
        except Exception:
            pass
    return {}


def save_global_seen(seen_urls: set[str], seen_at: dict[str, str] | None = None) -> None:
    from datetime import datetime
    path = _global_seen_path()
    os.makedirs(state.OUTPUT_DIR, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "seen_urls": list(seen_urls),
                    # Дата последней успешной обработки нужна режиму
                    # «проверить старые»: без неё TTL не отличит свежую
                    # карточку от той, которую пора обновить.
                    "seen_at": dict(seen_at or {}),
                    "saved_at": datetime.now().isoformat(),
                },
                f,
                ensure_ascii=False,
            )
    except Exception:
        pass
