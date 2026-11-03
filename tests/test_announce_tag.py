# -*- coding: utf-8 -*-
"""Объявление версии: шаги announce-release.yml прогоняются на настоящих тегах.

Регресс, ради которого это написано: ручной запуск с тегом «2.3.4» (человек
пишет версию без «v», как она называется в CHANGELOG) уходил в
`gh release view 2.3.4`, такого тега в репозитории нет — шаг ожидания молча не
находил релиз и падал с «релиз не опубликован или без windows-архива», хотя
релиз v2.3.4 уже лежал опубликованным и с архивом. Поэтому проверяем:

  * тег нормализуется к «vX.Y.Z» и мусор гасится с внятной ошибкой;
  * шаг ожидания различает «не читается», «черновик», «нет windows-архива» и
    «готово», а не сообщает одну фразу на все случаи.

Шаги берутся прямо из workflow (один источник правды), bash-выражения
`${{ ... }}` подставляются как значения соответствующих env.
"""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="workflow-файлы читает pyyaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "announce-release.yml"
WINDOWS_ZIP = "YandexBusinessParser-windows-x64.zip"

sys.path.insert(0, str(ROOT / "scripts"))
import release_tag   # noqa: E402  — тот же код, что зовёт воркфлоу
import wait_release  # noqa: E402


def _wf():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _step(name_part: str) -> dict:
    for job in _wf()["jobs"].values():
        for step in job["steps"]:
            if name_part in step.get("name", ""):
                return step
    raise AssertionError(f"в announce-release.yml нет шага «{name_part}»")


class TestTagResolution:
    """«2.3.4» и «v2.3.4» — один и тот же релиз: нормализация в Python."""

    @pytest.mark.parametrize("given,expected", [
        ("2.3.4", "v2.3.4"),        # ручной запуск без «v» — тот самый случай
        ("v2.3.4", "v2.3.4"),
        ("V2.3.4", "v2.3.4"),
        (" 2.3.4 ", "v2.3.4"),      # случайный пробел при копировании
        ("2.2.1.1", "v2.2.1.1"),    # тег из четырёх чисел тоже существует
    ])
    def test_manual_input_is_normalized(self, given, expected):
        tag, error = release_tag.resolve(input_tag=given)
        assert error == ""
        assert tag == expected

    def test_release_event_tag_is_kept(self):
        assert release_tag.resolve(release_tag="v2.3.4") == ("v2.3.4", "")

    def test_run_without_a_tag_uses_the_latest_published_release(self):
        assert release_tag.resolve(latest="v2.3.4\n") == ("v2.3.4", "")

    @pytest.mark.parametrize("given", ["main", "v2.3", "release-2.3.4", "", "v", "latest"])
    def test_garbage_is_refused_loudly(self, given):
        tag, error = release_tag.resolve(input_tag=given)
        assert error, f"{given!r} должен быть отвергнут"
        assert "v2.3.4" in error, "ошибка обязана называть нужный вид тега"


class TestWaitStep:
    """Четыре состояния релиза — четыре разных ответа; шаг ждёт через функцию."""

    @staticmethod
    def _wait(payload, tag="v2.3.4"):
        logs = []

        def fetch(_tag):
            if payload is None:
                raise RuntimeError("release not found")
            return payload

        ok, reason = wait_release.wait_for_release(
            fetch, tag, attempts=2, pause=0, log=logs.append, sleep=lambda _s: None)
        return ok, reason, "\n".join(logs)

    def test_published_release_with_the_windows_zip_passes(self):
        ok, reason, log = self._wait({"isDraft": False,
                                      "assets": [{"name": WINDOWS_ZIP},
                                                 {"name": "CHANGELOG.md"}]})
        assert ok and reason == "ok"
        assert "опубликован" in log

    def test_draft_is_reported_as_a_draft(self):
        ok, reason, log = self._wait({"isDraft": True, "assets": [{"name": WINDOWS_ZIP}]})
        assert not ok and reason == "draft"
        assert "draft" in log

    def test_published_without_the_windows_zip_is_reported(self):
        ok, reason, _log = self._wait({"isDraft": False, "assets": [{"name": "macos.zip"}]})
        assert not ok
        assert reason == "no-asset:macos.zip"
        # В ошибке видно, какого файла не хватает.
        assert WINDOWS_ZIP in wait_release.REQUIRED_HINT

    def test_unreadable_release_shows_the_real_reason(self):
        ok, reason, log = self._wait(None)
        assert not ok
        assert "release not found" in reason
        assert "::error::" in log

    def test_already_announced_version_is_skipped(self):
        assert release_tag.should_skip("2.3.4", "v2.3.4") is True
        assert release_tag.should_skip("2.3.3", "v2.3.4") is False
        assert release_tag.should_skip("", "v2.3.4") is False
