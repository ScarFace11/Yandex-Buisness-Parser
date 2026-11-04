# -*- coding: utf-8 -*-
"""Автопубликация релиза: черновик публикуется сам, когда оба билда зелёные.

Почему это отдельный воркфлоу и почему именно так:

* публикация — это момент, когда у ВСЕХ установленных приложений включается
  авто-обновление, поэтому она не должна быть шагом внутри сборки: сборка
  Windows не знает, чем закончилась сборка macOS;
* воркфлоу .github/workflows/publish-release.yml запускается завершением
  обоих билдов (workflow_run) и публикует черновик, только если:
  у тега зелёные обе сборки, на черновике лежат все файлы, а сам он ещё
  черновик (иначе повторный запуск ничего не делает);
* dev- и rc-теги автоматика не публикует — это внутренние сборки;
* version.json здесь не пишется: его обновляет announce-release.yml уже
  ПОСЛЕ публикации, иначе приложения обещали бы недоступное обновление.
"""
import os
import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="workflow-файлы читает pyyaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
PUBLISH = WORKFLOWS / "publish-release.yml"
WINDOWS_BUILD = WORKFLOWS / "build-exe.yml"
MACOS_BUILD = WORKFLOWS / "build-macos.yml"

sys.path.insert(0, str(ROOT / "scripts"))
import release_tag  # noqa: E402  — та же логика, что зовёт воркфлоу
import wait_builds  # noqa: E402


def text(path=PUBLISH):
    return path.read_text(encoding="utf-8")


def code(path=PUBLISH):
    """Строки без комментариев: проверяем только то, что реально выполнится."""
    return "\n".join(ln for ln in text(path).splitlines()
                     if not ln.lstrip().startswith("#"))


def wf(path=PUBLISH):
    # PyYAML читает ключ `on:` как булево True.
    return yaml.safe_load(text(path))


def trigger():
    data = wf()
    return data.get("on", data.get(True))


# ── Триггеры ──────────────────────────────────────────────────

class TestTriggers:
    def test_runs_when_either_build_finishes(self):
        wr = trigger()["workflow_run"]
        assert wr["types"] == ["completed"]
        assert set(wr["workflows"]) == {"Build Windows EXE", "Build macOS .app"}

    def test_workflow_names_match_the_real_builds(self):
        for name, path in (("Build Windows EXE", WINDOWS_BUILD),
                           ("Build macOS .app", MACOS_BUILD)):
            assert wf(path)["name"] == name, f"{path.name}: имя workflow изменилось"

    def test_manual_run_can_publish_an_already_built_tag(self):
        """Аварийный выход: черновик собрали до появления автоматики."""
        assert trigger()["workflow_dispatch"]["inputs"]["tag"]["required"] is True


# ── Права и место в конвейере ─────────────────────────────────

class TestPermissionsAndScope:
    def test_can_publish_a_release_and_start_the_announcement(self):
        perms = wf()["permissions"]
        assert perms["contents"] == "write"
        # Не только читать статусы сборок: workflow_dispatch объявления
        # версии — единственный способ разбудить announce-release после
        # публикации, сделанной GITHUB_TOKEN.
        assert perms["actions"] == "write"

    def test_publishing_is_not_scattered_across_the_builds(self):
        """Черновик публикует ровно один workflow — иначе гонка за релиз."""
        owners = [p.name for p in WORKFLOWS.glob("*.yml") if "--draft=false" in text(p)]
        assert owners == [PUBLISH.name], owners

    def test_nothing_is_rebuilt_here(self):
        body = code()
        for forbidden in ("pyinstaller", "pip install", "stamp_version",
                          "version.json"):
            assert forbidden not in body, f"публикация не должна: {forbidden}"

    def test_scripts_are_checked_out_before_they_run(self):
        """Без checkout `python3 scripts/...` падает с can't open file."""
        steps = wf()["jobs"]["publish"]["steps"]
        checkout_at = next(i for i, s in enumerate(steps)
                           if str(s.get("uses", "")).startswith("actions/checkout"))
        tag_at = next(i for i, s in enumerate(steps)
                      if "Check the tag" in s.get("name", ""))
        assert checkout_at < tag_at


# ── Гейты: обе сборки, файлы, статус черновика ────────────────

class TestGates:
    def test_both_builds_must_be_green(self):
        """Успех — только success; остальное либо ждёт, либо останавливает."""
        assert set(wait_builds.WORKFLOWS) == {"build-exe.yml", "build-macos.yml"}
        for bad in ("failure", "cancelled", "timed_out"):
            assert bad in wait_builds.FAILED_CONCLUSIONS
        assert "wait_builds.py" in code(), "шаг ожидания обязан звать Python-скрипт"
    def test_a_failed_build_stops_the_publication(self):
        ok, reason = wait_builds.wait_for_builds(
            lambda wf: ("completed failure" if wf == "build-macos.yml"
                        else "completed success"),
            "v2.3.4", attempts=1, log=lambda *_: None, sleep=lambda _s: None)
        assert not ok and reason == "failure"
        names = [s.get("name", "") for s in wf()["jobs"]["publish"]["steps"]]
        wait_at = next(i for i, n in enumerate(names) if "both builds" in n)
        publish_at = next(i for i, n in enumerate(names) if n.startswith("Publish the release"))
        assert wait_at < publish_at, "падение сборки обязано остановить работу до публикации"
    def test_the_wait_is_bounded(self):
        """Ожидание конечно: иначе job висел бы в очереди сутками."""
        assert 1 <= wait_builds.ATTEMPTS <= 60
        assert 5 <= wait_builds.PAUSE <= 120
        assert wait_builds.ATTEMPTS * wait_builds.PAUSE <= 30 * 60, \
            "суммарное ожидание больше получаса"
    def test_required_assets_match_what_the_builds_produce(self):
        required = list(release_tag.REQUIRED_ASSETS)
        assert required == [
            "YandexBusinessParser-windows-x64.zip",
            # Установщик с ярлыком и удалением: именно его скачивают
            # пользователи Windows, portable-архив остаётся альтернативой.
            "YandexBusinessParser-windows-x64-setup.exe",
            # 2.3.5: отдельный .zip для macOS больше не собирается —
            # приложение ставится из .dmg, и требовать архив не за что.
            "YandexBusinessParser-macos-arm64.dmg",
            "YandexBusinessParser-macos-x64.dmg",
            "CHANGELOG.md",
        ]
        # Каждый файл обязан реально появляться в сборке — иначе публикация
        # зависнет навсегда, а релиз будет без архива.
        assert "YandexBusinessParser-windows-x64.zip" in text(WINDOWS_BUILD)
        assert "YandexBusinessParser-windows-x64-setup.exe" in text(WINDOWS_BUILD)
        assert "CHANGELOG.md" in text(WINDOWS_BUILD)
        macos = text(MACOS_BUILD)
        assert "YandexBusinessParser-macos-$ARCH.dmg" in macos
        assert 'asset_arch: arm64' in macos and 'asset_arch: x64' in macos

    def test_missing_assets_block_the_publication(self):
        verdict, missing = release_tag.draft_decision({
            "isDraft": True,
            "assets": [{"name": "CHANGELOG.md"},
                       {"name": "YandexBusinessParser-windows-x64.zip"}],
        })
        assert verdict == "missing"
        assert "YandexBusinessParser-windows-x64-setup.exe" in missing
        assert "CHANGELOG.md" not in missing
        assert "release_tag.py draft" in code(), "шаг обязан звать Python-скрипт"

    def test_all_assets_present_lets_the_publication_pass(self):
        payload = {"isDraft": True,
                   "assets": [{"name": n} for n in release_tag.REQUIRED_ASSETS]}
        assert release_tag.draft_decision(payload) == ("ok", ())

    def test_extra_and_repeated_assets_do_not_break_the_check(self):
        names = list(release_tag.REQUIRED_ASSETS)
        payload = {"isDraft": True,
                   "assets": [{"name": n} for n in names + names + ["notes.txt"]]}
        assert release_tag.draft_decision(payload) == ("ok", ())

    def test_already_published_release_is_a_noop(self):
        verdict, _missing = release_tag.draft_decision({"isDraft": False, "assets": []})
        assert verdict == "published"

    def test_absent_draft_is_a_quiet_noop(self):
        """Черновик создаёт отдельный job: его отсутствие — не красный конвейер."""
        assert release_tag.draft_decision(None) == ("absent", ())

    def test_publishes_by_flipping_the_draft_flag(self):
        body = code()
        assert 'gh release edit "$TAG"' in body
        assert "--draft=false" in body

    def test_asset_upload_keeps_the_release_as_a_draft(self):
        """softprops по умолчанию публикует черновик после загрузки."""
        steps = wf(WINDOWS_BUILD)["jobs"]["build"]["steps"]
        upload = next(s for s in steps
                      if str(s.get("uses", "")).startswith("softprops/action-gh-release"))
        assert upload["with"]["draft"] is True

    def test_published_release_is_announced_explicitly(self):
        """GITHUB_TOKEN не создаёт release: published — запускаем вручную."""
        steps = wf()["jobs"]["publish"]["steps"]
        names = [s.get("name", "") for s in steps]
        publish_at = next(i for i, n in enumerate(names) if n == "Publish the release")
        announce_at = next(i for i, n in enumerate(names) if n == "Announce the published version")
        assert announce_at > publish_at
        step = steps[announce_at]
        assert "gh workflow run announce-release.yml" in step["run"]
        assert '-f tag="$TAG"' in step["run"]
        assert "steps.draft.outputs.published == 'true'" in step["if"]

    def test_published_release_is_reported_for_announcement(self, monkeypatch, tmp_path):
        out = tmp_path / "github_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setenv("TAG", "v2.3.4")
        monkeypatch.setenv("REPO", "o/r")
        monkeypatch.setattr(release_tag, "_gh_release",
                            lambda tag, repo: {"isDraft": False, "assets": []})
        monkeypatch.setattr("builtins.print", lambda *a, **k: None)
        assert release_tag.main(["draft"]) == 0
        written = out.read_text(encoding="utf-8")
        assert "ok=false" in written
        assert "published=true" in written


# ── Логика ожидания: гоняем сам скрипт на заглушке gh ────────

# ── Ожидание и теги проверяются на функциях, без bash ──────

class TestWaitLogic:
    """Та же функция, что исполняет воркфлоу, — без bash и заглушек gh."""

    @staticmethod
    def _run(exe_states, macos_states, attempts=2):
        queues = {"build-exe.yml": list(exe_states),
                  "build-macos.yml": list(macos_states)}
        logs = []

        def fetch(workflow):
            queue = queues.get(workflow) or []
            if not queue:
                return "missing "
            # Последняя строка повторяется: запуск «висит» в этом статусе.
            return queue.pop(0) if len(queue) > 1 else queue[0]

        ok, reason = wait_builds.wait_for_builds(
            fetch, "v2.3.4", attempts=attempts,
            log=logs.append, sleep=lambda _s: None)
        return ok, reason, "\n".join(logs)

    def test_both_green_lets_the_publication_pass(self):
        ok, reason, log = self._run(["completed success"], ["completed success"])
        assert ok and reason == "ok"
        assert "Обе сборки зелёные" in log

    def test_failed_build_blocks_the_publication(self):
        ok, reason, log = self._run(["completed success"], ["completed failure"])
        assert not ok and reason == "failure"
        assert "::error::" in log

    def test_second_build_finishing_later_still_publishes(self):
        """Первый билд завершился раньше — публикуем по завершению второго."""
        ok, _reason, log = self._run(["completed success"],
                                     ["in_progress", "completed success"])
        assert ok
        assert "Ждём ещё:" in log

    def test_never_green_times_out_without_publishing(self):
        ok, reason, log = self._run(["completed success"], ["in_progress"], attempts=2)
        assert not ok and reason == "timeout"
        assert "публикация отложена" in log

    def test_missing_run_is_treated_as_pending(self):
        """Сборка ещё не запускалась — это не успех и не провал."""
        ok, reason, log = self._run(["completed success"], [], attempts=1)
        assert not ok and reason == "timeout"
        assert "missing" in log


# ── Какие теги автоматика не трогает ──────────────────────────

class TestOnlyStableTags:
    """Стабильные теги публикуются, dev/rc и ветки — нет."""

    @pytest.mark.parametrize("tag", ["v2.3.4", "v2.2.1.1", "v10.0.0"])
    def test_stable_tags_are_published(self, tag):
        assert release_tag.is_release_tag(tag)

    @pytest.mark.parametrize("tag", ["v2.3.4-dev", "v2.3.4-rc1", "main",
                                     "2.3.4", "v2.3", "release-2.3.4"])
    def test_dev_and_other_tags_are_left_alone(self, tag):
        assert not release_tag.is_release_tag(tag)

    def test_dev_versions_cannot_be_auto_published(self):
        """Тег с суффиксом — не публичный релиз: автоматика его не публикует."""
        import config
        assert not release_tag.is_release_tag("v2.3.4-dev")
        assert not release_tag.is_release_tag("v" + str(config.APP_VERSION) + "-dev")


# ── Ручной ввод тега ─────────────────────────────────────────

class TestManualTagInput:
    """Человек называет версию без «v» — публикация всё равно находит тег."""

    @pytest.mark.parametrize("given,expected", [
        ("2.3.4", "v2.3.4"), ("v2.3.4", "v2.3.4"),
        ("V2.3.4", "v2.3.4"), (" 2.3.4 ", "v2.3.4"), ("2.2.1.1", "v2.2.1.1"),
    ])
    def test_manual_input_is_normalized_and_published(self, given, expected):
        tag, publish, error = release_tag.publish_decision(given, input_tag=given)
        assert error == ""
        assert publish is True
        assert tag == expected

    def test_manual_input_with_a_bad_tag_fails_loudly(self):
        """Ручной запуск — осознанное действие: молчаливое «нечего делать» врёт."""
        tag, publish, error = release_tag.publish_decision("2.3.4-rc1",
                                                           input_tag="2.3.4-rc1")
        assert publish is False
        assert error, "плохой ручной тег обязан давать внятную ошибку"
        assert "-rc" in error

    @pytest.mark.parametrize("branch", ["main", "v2.3.4-dev", "feature/x"])
    def test_a_push_to_a_non_release_tag_stays_a_quiet_noop(self, branch):
        """Пуш ветки/dev-тега ничего не публикует — но и не краснит конвейер."""
        _tag, publish, error = release_tag.publish_decision(branch)
        assert publish is False
        assert error == ""
