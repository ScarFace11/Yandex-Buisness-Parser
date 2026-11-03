"""Карточки объёма живут в settings.json, а не только в браузере.

Список вариантов — такая же настройка приложения, как папка результатов:
после очистки браузера он не должен исчезать, а выбранный вариант обязан
пережить перезапуск. Сервер нормализует присланное, чтобы испорченный запрос
не мог записать мусор в settings.json.
"""
from pathlib import Path

import pytest
from flask import Flask


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import paths

    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    from routes import api as api_mod

    app = Flask(__name__)
    app.register_blueprint(api_mod.bp)
    return app.test_client()


def _card(key, **extra):
    data = {"key": key, "name": key.title(), "note": "описание",
            "pages": 2, "candidates": 200, "vk": False}
    data.update(extra)
    return data


def _saved(tmp_path):
    import json

    import paths

    return json.loads(paths.settings_path().read_text(encoding="utf-8"))


def test_empty_settings_returns_no_cards(client):
    data = client.get("/effort/cards").get_json()

    assert data == {"ok": True, "cards": [], "active": ""}


def test_cards_are_saved_to_settings_json(client, tmp_path):
    cards = [_card("fast", name="Быстро", pages=1, candidates=20),
             _card("thorough", name="Тщательно", pages=5, candidates=600, vk=True)]

    resp = client.post("/effort/cards", json={"cards": cards, "active": "thorough"})
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is True
    assert [c["key"] for c in data["cards"]] == ["fast", "thorough"]
    assert data["active"] == "thorough"
    saved = _saved(tmp_path)
    assert saved["effort_active"] == "thorough"
    assert saved["effort_cards"][1]["candidates"] == 600

    again = client.get("/effort/cards").get_json()
    assert again["cards"] == data["cards"]
    assert again["active"] == "thorough"


def test_normalization_clamps_trims_and_drops_duplicates(client):
    cards = [
        _card("a", name="  " + "Д" * 40, note="Я" * 200, pages=99, candidates=0),
        _card("a", name="Дубль"),
        _card("bad key!", name="Ключ с пробелом", pages=-4, candidates=999999),
        {"key": "no-name"},
        "не карточка",
    ]

    data = client.post("/effort/cards", json={"cards": cards}).get_json()

    assert [c["key"] for c in data["cards"]] == ["a", "badkey", "no-name"]
    first = data["cards"][0]
    assert first["name"] == "Д" * 24
    assert first["note"] == "Я" * 90
    assert first["pages"] == 20
    assert first["candidates"] == 1


def test_unknown_active_falls_back_to_first_card(client):
    data = client.post("/effort/cards", json={
        "cards": [_card("one"), _card("two")],
        "active": "missing",
    }).get_json()

    assert data["active"] == "one"


def test_at_most_twenty_cards_are_kept(client):
    cards = [_card(f"c{i}") for i in range(25)]

    data = client.post("/effort/cards", json={"cards": cards}).get_json()

    assert len(data["cards"]) == 20
    assert data["cards"][-1]["key"] == "c19"


def test_broken_body_is_rejected_without_touching_settings(client):
    assert client.post("/effort/cards", json={"cards": "нет"}).status_code == 400
    assert client.post("/effort/cards", json={"cards": []}).status_code == 400
    assert client.get("/effort/cards").get_json()["cards"] == []
