# -*- coding: utf-8 -*-
"""Тексты обновлений: данные, эндпоинт «Что нового» и штамповка версии.

Тексты живут в update_notes отдельно от кода: `notes/<версия>.json` —
краткое описание и полный текст, `ui.json` — подписи. Ошибка в них не роняет
приложение (файл просто пропадёт из окна), поэтому проверяем данные явно:
битый JSON или пустой `items` иначе доедут до пользователя пустой строкой.
"""
import json
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "update_notes" / "notes"
UI = ROOT / "update_notes" / "ui.json"
sys.path.insert(0, str(ROOT / "scripts"))

import stamp_version  # noqa: E402
import update_notes  # noqa: E402

REQUIRED_UI_KEYS = (
    "modal_title", "modal_subtitle", "latest", "yours", "details", "back",
    "close", "empty", "offline", "error", "banner_new_version",
    "banner_whats_new",
)


class TestNotesData:
    def test_every_note_is_valid(self):
        files = sorted(NOTES.glob("*.json"))
        assert files, "нет ни одного файла версии"
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            assert data.get("version") == path.stem, (
                f"{path.name}: version={data.get('version')!r} не совпадает с именем файла")
            assert str(data.get("summary") or "").strip(), f"{path.name}: нет краткого описания"
            assert str(data.get("title") or "").strip(), f"{path.name}: нет заголовка"
            items = data.get("items") or []
            sections = data.get("sections") or []
            assert items or sections, f"{path.name}: нет полного текста (ни items, ни sections)"
            for item in items:
                assert str(item.get("text") or "").strip(), f"{path.name}: пустой пункт"
            for sec in sections:
                assert str(sec.get("title") or "").strip(), f"{path.name}: раздел без заголовка"
                points = sec.get("points") or []
                assert points, f"{path.name}: раздел без пунктов"
                for point in points:
                    assert str(point or "").strip(), f"{path.name}: пустой пункт в разделе"

    def test_the_newest_note_is_split_into_release_sections(self):
        """Полный текст новой версии читается как релиз: разделы с пунктами."""
        note = update_notes.latest()
        sections = note.get("sections") or []
        assert len(sections) >= 3, "полный текст должен быть разбит на разделы"
        assert not note.get("items"), "дублировать тот же текст в items не нужно"
        titles = [s["title"] for s in sections]
        assert len(titles) == len(set(titles)), f"разделы повторяются: {titles}"
        points = sum(len(s["points"]) for s in sections)
        assert points >= 10, f"пунктов слишком мало для полного текста: {points}"

    def test_sections_survive_the_endpoint(self, monkeypatch):
        """Разделы доезжают до окна, а не теряются по дороге."""
        data = _client(monkeypatch, RuntimeError("нет сети")).get("/update/changelog").get_json()
        top = data["history"][0]
        assert top["sections"], "у верхней версии нет разделов"
        assert top["sections"][0]["points"], "раздел приехал без пунктов"

    def test_the_current_build_has_its_own_note(self):
        from config import APP_VERSION
        assert update_notes.find(APP_VERSION), (
            f"для версии {APP_VERSION} нет update_notes/notes/{APP_VERSION}.json")

    def test_ui_texts_are_complete(self):
        ui = json.loads(UI.read_text(encoding="utf-8-sig"))
        for key in REQUIRED_UI_KEYS:
            assert str(ui.get(key) or "").strip(), f"ui.json: пустой ключ {key}"

    def test_summary_is_short_enough_for_a_banner(self):
        """Краткое описание — одна строка для баннера и списка, а не абзац."""
        for path in sorted(NOTES.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            summary = str(data.get("summary") or "")
            assert len(summary) <= 300, f"{path.name}: краткое описание {len(summary)} символов"
            assert "\n" not in summary, f"{path.name}: краткое описание в несколько строк"


def _client(monkeypatch, remote):
    from routes import update as update_mod

    def _meta():
        if isinstance(remote, Exception):
            raise remote
        return remote

    monkeypatch.setattr(update_mod, "_remote_meta", _meta)
    app = Flask(__name__)
    app.register_blueprint(update_mod.bp)
    return app.test_client()


class TestChangelogEndpoint:
    def test_newest_known_version_is_marked_latest(self, monkeypatch):
        """main может отставать от собранной версии — «новейшая» всё равно верхняя."""
        remote = {"version": "2.3.4.2", "changelog": "старое",
                  "history": [{"version": "2.3.4.2", "changelog": "старое"}]}
        data = _client(monkeypatch, remote).get("/update/changelog").get_json()
        assert data["version"] == "2.4", data["version"]
        assert data["history"][0]["version"] == "2.4"
        top = data["history"][0]
        assert top["items"] or top["sections"], "у верхней версии нет полного текста"
        assert update_notes.summary("2.4") == data["changelog"]

    def test_texts_for_the_modal_come_from_the_package(self, monkeypatch):
        data = _client(monkeypatch, RuntimeError("нет сети")).get("/update/changelog").get_json()
        ui = json.loads(UI.read_text(encoding="utf-8-sig"))
        assert data["texts"] == ui
        assert data["offline"] is True
        assert data["history"], "офлайн-история должна быть из самой сборки"

    def test_a_broken_remote_does_not_break_the_window(self, monkeypatch):
        data = _client(monkeypatch, ValueError("плохой json")).get("/update/changelog").get_json()
        assert data["current"]
        assert data["version"]
        assert data["history"]

    def test_remote_only_version_appears_in_history(self, monkeypatch):
        remote = {"version": "9.9.9", "changelog": "новая версия",
                  "history": [{"version": "9.9.9", "changelog": "новая версия",
                               "items": [{"title": "Новое", "text": "Подробности"}]}]}
        data = _client(monkeypatch, remote).get("/update/changelog").get_json()
        assert data["version"] == "9.9.9"
        assert data["history"][0]["items"][0]["text"] == "Подробности"
        assert data["history"][0]["summary"] == "новая версия"


class TestStampVersion:
    def test_history_gets_the_full_text_from_notes(self, tmp_path):
        path = tmp_path / "version.json"
        path.write_text(json.dumps({"version": "2.3.4.2", "history": [
            {"version": "2.3.4.2", "changelog": "старое"}]}), encoding="utf-8")
        data = stamp_version.apply_version(
            path, "2.4", changelog_file=ROOT / "CHANGELOG.md",
            repo="owner/name", bump_history=True)
        top = data["history"][0]
        assert top["version"] == "2.4"
        assert top["title"] and top["date"]
        assert top["summary"] == update_notes.summary("2.4")
        assert len(top["sections"] or top["items"]) >= 1, "у версии нет полного текста"
        assert data["changelog"] == update_notes.summary("2.4")
        assert data["download_url"].endswith("v2.4/YandexBusinessParser-windows-x64.zip")
        assert len(data["history"]) <= stamp_version.HISTORY_LIMIT

    def test_stamped_file_is_readable_by_the_app(self, tmp_path):
        """version.json после штамповки — тот же формат, что читает фронтенд."""
        path = tmp_path / "version.json"
        stamp_version.apply_version(path, "2.4", repo="owner/name")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["history"][0]["summary"]
        assert isinstance(data["history"][0]["items"], list)
        assert isinstance(data["history"][0]["sections"], list)
