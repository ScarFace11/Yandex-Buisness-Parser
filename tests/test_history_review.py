"""«История»: сколько записей прогона уже просмотрено.

Счёт идёт по тем же отметкам, что и в таблице (`_reviewed.json`), а файлы
прогона ищутся по метке времени запуска в имени — raw_2026-11-01_16-30_…:
у записей истории список файлов появился позже, у прошлых прогонов он пуст.
"""
import json
from datetime import datetime

import pytest
from flask import Flask


def _rec(name, url):
    return {"name": name, "city": "Ярославль", "query": "автомойка",
            "yandex_maps_url": url, "address": f"ул. {name}, 1"}


RECORDS = [
    _rec("Автомойка 1", "https://yandex.ru/maps/org/1"),
    _rec("Автомойка 2", "https://yandex.ru/maps/org/2"),
    _rec("Автомойка 3", "https://yandex.ru/maps/org/3"),
    _rec("Автомойка 4", "https://yandex.ru/maps/org/4"),
]
STAMP = "2026-11-01_16-30"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from routes import api as api_mod
    import search_history

    root = tmp_path / "output"
    raw = root / "raw"
    proc = root / "processed"
    for d in (raw, proc / "excel", proc / "json", root / "_archive"):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(api_mod, "OUTPUT_DIR", str(root))
    monkeypatch.setattr(api_mod, "RESULTS_DIR", str(root))
    monkeypatch.setattr(api_mod, "REVIEWED_FILE", str(root / "_reviewed.json"))
    monkeypatch.setattr(api_mod, "_raw_dir", lambda: str(raw))
    monkeypatch.setattr(api_mod, "_processed_dir", lambda: str(proc))
    monkeypatch.setattr(api_mod, "_archive_root", lambda: str(root / "_archive"))
    api_mod._clear_file_caches()
    api_mod._run_index.update(key=None, by_stamp={}, processed={}, newest={})

    monkeypatch.setattr(search_history, "HISTORY_FILE", str(root / ".search_history.json"))
    monkeypatch.setattr(search_history, "_cache", [])

    app = Flask(__name__)
    app.register_blueprint(api_mod.bp)
    c = app.test_client()
    c.out = root
    c.raw = raw
    c.proc = proc
    return c


def _write_json(path, rows):
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def _history(client, ts=None, files=None, results=4):
    """Одна запись истории с меткой времени = метка в имени файла."""
    ts = ts if ts is not None else datetime(2026, 11, 1, 16, 30).timestamp()
    entry = {"run_id": "run1", "timestamp": ts, "queries": ["автомойка"],
             "cities": ["Ярославль"], "social_mode": "all", "results_count": results,
             "files": files or [], "elapsed_sec": 12, "status": "completed"}
    (client.out / ".search_history.json").write_text(
        json.dumps([entry], ensure_ascii=False), encoding="utf-8")
    import search_history
    search_history._cache = None


def _marks(client, urls):
    data = {u: {"reviewed_at": 1762000000.0} for u in urls}
    (client.out / "_reviewed.json").write_text(json.dumps(data), encoding="utf-8")


def test_history_counts_viewed_records(client):
    _write_json(client.raw / f"raw_{STAMP}_автомойка_ярославль.json", RECORDS)
    _marks(client, [RECORDS[0]["yandex_maps_url"]])
    _history(client)

    entry = client.get("/history").get_json()["history"][0]
    assert entry["viewed"] == 1
    assert entry["viewed_total"] == 4


def test_history_shows_full_progress_when_everything_is_viewed(client):
    _write_json(client.raw / f"raw_{STAMP}_автомойка_ярославль.json", RECORDS)
    _marks(client, [r["yandex_maps_url"] for r in RECORDS])
    _history(client)

    entry = client.get("/history").get_json()["history"][0]
    assert entry["viewed"] == entry["viewed_total"] == 4


def test_processed_file_wins_for_the_latest_run_so_records_are_not_counted_twice(client):
    """raw и processed одного прогона — одни и те же компании: 4, а не 8."""
    _write_json(client.raw / f"raw_{STAMP}_автомойка_ярославль.json", RECORDS)
    _write_json(client.proc / "json" / "автомойка_ярославль_filtered.json", RECORDS)
    _marks(client, [RECORDS[1]["yandex_maps_url"]])
    _history(client)

    entry = client.get("/history").get_json()["history"][0]
    assert entry["viewed_total"] == 4
    assert entry["viewed"] == 1


def test_history_without_files_keeps_the_plain_count(client):
    _history(client, results=44)

    entry = client.get("/history").get_json()["history"][0]
    assert "viewed_total" not in entry, "нечего считать — выдуманных нулей не показываем"
    assert entry["results_count"] == 44


def test_files_list_shows_review_progress_per_file(client):
    """Карточка файла показывает «0/60 записей» — прогресс до открытия таблицы."""
    _write_json(client.raw / f"raw_{STAMP}_автомойка_ярославль.json", RECORDS)
    _marks(client, [RECORDS[0]["yandex_maps_url"]])

    files = client.get("/files/list").get_json()
    item = files["raw"][0]
    assert item["records"] == 4
    assert item["viewed"] == 1


def test_files_list_without_marks_reports_zero(client):
    _write_json(client.raw / f"raw_{STAMP}_автомойка_ярославль.json", RECORDS)
    item = client.get("/files/list").get_json()["raw"][0]
    assert item["viewed"] == 0
