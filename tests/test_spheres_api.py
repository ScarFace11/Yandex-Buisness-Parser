# -*- coding: utf-8 -*-
"""HTTP-часть новых настроек: выбор браузера и каталог сфер.

Тесты поднимают только нужные blueprint'ы и не пишут настоящий settings.json:
выбор браузера — машинная настройка, и тест не должен менять выбор
пользователя на его машине.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import paths
from routes import api as api_mod
from routes import diagnostics as diag
from yandex_maps_parser import cdp_client


@pytest.fixture()
def api_client():
    app = Flask(__name__)
    app.register_blueprint(api_mod.bp)
    return app.test_client()


@pytest.fixture()
def diag_client():
    app = Flask(__name__)
    app.register_blueprint(diag.bp)
    return app.test_client()


def test_spheres_endpoint_returns_catalog_and_history(api_client, monkeypatch):
    import search_history

    monkeypatch.setattr(search_history, "get_history", lambda limit=50: [
        {"timestamp": 1000.0, "queries": ["кафе"], "cities": ["Москва"],
         "results_count": 12},
    ])
    data = api_client.get("/spheres").get_json()
    assert data["ok"] is True
    assert any(s["id"] == "cafe" for s in data["spheres"])
    cafe = [h for h in data["history"] if h["id"] == "cafe"][0]
    assert cafe["last_ts"] == 1000.0 and cafe["cities"] == ["Москва"]


def test_engines_status_lists_browsers_for_the_select(diag_client, monkeypatch):
    monkeypatch.setattr(cdp_client, "browser_info", lambda: {
        "path": "C:/b/chrome.exe", "name": "Google Chrome", "chromium": True,
        "unsupported": [], "selected": "",
        "browsers": [{"name": "Google Chrome", "path": "C:/b/chrome.exe"},
                     {"name": "Яндекс Браузер", "path": "C:/b/browser.exe"}],
    })
    data = diag_client.get("/engines/status").get_json()
    assert [b["name"] for b in data["browsers"]] == ["Google Chrome", "Яндекс Браузер"]
    assert data["selected"] == ""


def test_browser_select_rejects_unknown_path(diag_client, monkeypatch):
    monkeypatch.setattr(cdp_client, "available_browsers", lambda: [
        {"name": "Google Chrome", "path": "C:/b/chrome.exe"},
    ])
    resp = diag_client.post("/browser/select", json={"path": "C:/nope/firefox.exe"})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_browser_select_saves_a_found_browser(diag_client, monkeypatch):
    saved: list[dict] = []
    chosen: list[str] = []
    monkeypatch.setattr(cdp_client, "available_browsers", lambda: [
        {"name": "Google Chrome", "path": "C:/b/chrome.exe"},
    ])
    monkeypatch.setattr(paths, "save_settings", lambda values: saved.append(values))
    monkeypatch.setattr(cdp_client, "set_browser", lambda p: chosen.append(p))
    monkeypatch.setattr(cdp_client, "browser_info", lambda: {
        "path": "C:/b/chrome.exe", "name": "Google Chrome", "chromium": True,
        "unsupported": [], "selected": "C:/b/chrome.exe", "browsers": [],
    })

    data = diag_client.post("/browser/select", json={"path": "C:/b/chrome.exe"}).get_json()
    assert data["ok"] is True
    assert saved == [{"browser_path": "C:/b/chrome.exe"}]
    assert chosen == ["C:/b/chrome.exe"]

    # Пустой путь — «автоматически»: это тоже сохранённое решение.
    saved.clear(); chosen.clear()
    data = diag_client.post("/browser/select", json={"path": ""}).get_json()
    assert data["ok"] is True
    assert saved == [{"browser_path": ""}]
    assert chosen == [""]


# ── Редактор сфер: сохранение, сброс, отказы ──────────────────

@pytest.fixture()
def custom_spheres(tmp_path, monkeypatch):
    """Каталог правок во временном файле — настоящий spheres.json не трогаем."""
    from yandex_maps_parser import spheres as spheres_mod
    path = tmp_path / "spheres.json"
    monkeypatch.setattr(spheres_mod, "_custom_path", lambda: str(path))
    return path


def test_save_spheres_replaces_the_catalog(api_client, custom_spheres):
    resp = api_client.post("/spheres", json={"spheres": [
        {"id": "cafe", "name": "Кофейни", "icon": "☕", "queries": ["кофе", "кофейня"]},
        {"name": "Барбершопы", "queries": ["барбершоп", "стрижка"]},
    ]})
    data = resp.get_json()
    assert data["ok"] is True
    assert [s["name"] for s in data["spheres"]] == ["Кофейни", "Барбершопы"]
    # Новая сфера без id его получает, слова нормализуются.
    new = data["spheres"][1]
    assert new["id"].startswith("custom-")
    assert new["queries"] == ["барбершоп", "стрижка"]

    listed = api_client.get("/spheres").get_json()
    assert [s["name"] for s in listed["spheres"]] == ["Кофейни", "Барбершопы"]


def test_save_spheres_rejects_empty_catalog(api_client, custom_spheres):
    resp = api_client.post("/spheres", json={"spheres": [{"name": "", "queries": []}]})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_save_spheres_rejects_non_list(api_client, custom_spheres):
    resp = api_client.post("/spheres", json={"spheres": "кафе"})
    assert resp.status_code == 400


def test_reset_spheres_returns_the_builtin_catalog(api_client, custom_spheres):
    api_client.post("/spheres", json={"spheres": [
        {"id": "only", "name": "Одна сфера", "queries": ["тест"]},
    ]})
    data = api_client.post("/spheres/reset").get_json()
    assert data["ok"] is True
    assert len(data["spheres"]) >= 20          # встроенный набор вернулся
    assert not custom_spheres.exists()
