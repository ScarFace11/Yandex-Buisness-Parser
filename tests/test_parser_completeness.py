# -*- coding: utf-8 -*-
"""Надёжность сбора: seen ≠ готово, слияние дублей, TTL старого кэша.

Эти проверки фиксируют то, из-за чего повторные прогоны теряли организации:
неудачная карточка попадала в seen как обработанная, а дубль отдавал только
первую копию записи.
"""
import json
import types

import pytest

from yandex_maps_parser import checkpoint, enrichment, state
from yandex_maps_parser.exporters import dedupe_records


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoint.state, "OUTPUT_DIR", str(tmp_path))
    return tmp_path


def _pbar():
    return types.SimpleNamespace(update=lambda *a, **k: None)


class TestCheckpointAndSeen:
    def test_failed_cards_survive_a_save(self, output_dir):
        checkpoint.save_checkpoint(
            "job", {"a", "b"}, {("кафе", 54.0, 55.0)}, {"b"}
        )
        loaded = checkpoint.load_checkpoint("job")
        assert loaded["failed_urls"] == {"b"}
        assert loaded["seen_urls"] == {"a", "b"}

    def test_seen_dates_roundtrip(self, output_dir):
        checkpoint.save_global_seen(
            {"card-1", "card-2"},
            {"card-1": "2026-10-01T10:00:00", "card-2": "2026-11-01T10:00:00"},
        )
        dates = checkpoint.load_global_seen_dates()
        assert dates["card-1"].startswith("2026-10-01")
        assert set(checkpoint.load_global_seen()) == {"card-1", "card-2"}

    def test_old_seen_file_without_dates_still_loads(self, output_dir):
        (output_dir / "_seen.json").write_text(
            json.dumps({"seen_urls": ["old-1", "old-2"]}), encoding="utf-8"
        )
        dates = checkpoint.load_global_seen_dates()
        assert dates == {"old-1": "", "old-2": ""}


class TestFailedEnrichment:
    def test_unread_card_is_not_marked_done(self, monkeypatch):
        from yandex_maps_parser import cdp_client

        for key, value in {
            "FETCH_DETAIL": True,
            "USE_BROWSER": True,
            "PARSE_MODE": "all",
            "SOCIAL_MODE": "all",
            "REQUIRED_SOCIALS": set(),
            "BLACKLIST_WORDS": [],
            "MAX_WORKERS": 1,
            "MIN_LEAD_SCORE": 0,
            "ONLY_SINGLE_BRANCH": False,
            "ONLY_NEW_MONTHS": None,
            "VK_CHECK": False,
            "STOP_EVENT": None,
        }.items():
            monkeypatch.setattr(state, key, value, raising=False)
        monkeypatch.setattr(state, "_detail_semaphore", None, raising=False)
        monkeypatch.setattr(cdp_client, "is_available", lambda: True)
        monkeypatch.setattr(enrichment, "fetch_html", lambda *a, **k: "")

        report = {}
        out = enrichment.enrich(
            [{"_biz_id": "123", "name": "Тест", "city": "Уфа", "query": "кафе"}],
            _pbar(), report=report,
        )
        assert [r["name"] for r in out] == ["Тест"]
        assert report["failed"] == {"123"}
        assert "123" not in report["done"]


class TestDuplicateMerge:
    def test_missing_fields_are_filled_from_the_duplicate(self):
        records = [
            {"name": "Кофейня", "yandex_maps_url": "https://yandex.ru/maps/org/1",
             "phone": "+7 900 111-22-33"},
            {"name": "Кофейня", "yandex_maps_url": "https://yandex.ru/maps/org/1",
             "phone": "+7 900 444-55-66", "email": "hello@cafe.ru",
             "hours": "10:00–20:00", "description": "Уютно"},
        ]
        merged = dedupe_records(records)
        assert len(merged) == 1
        row = merged[0]
        assert "+7 900 111-22-33" in row["phone"]
        assert "+7 900 444-55-66" in row["phone"]
        assert row["email"] == "hello@cafe.ru"
        assert row["hours"] == "10:00–20:00"
        assert row["description"] == "Уютно"


class TestRefreshParams:
    def test_refresh_is_off_by_default_and_can_be_enabled(self):
        from yandex_maps_parser import runner

        old_seen, old_days = state.REFRESH_SEEN, state.REFRESH_DAYS
        try:
            runner._apply_params({"queries": ["кафе"], "cities": ["Уфа"]})
            assert state.REFRESH_SEEN is False
            runner._apply_params({"queries": ["кафе"], "refresh_seen": True,
                                  "refresh_days": 30})
            assert state.REFRESH_SEEN is True
            assert state.REFRESH_DAYS == 30
        finally:
            state.REFRESH_SEEN, state.REFRESH_DAYS = old_seen, old_days
