# -*- coding: utf-8 -*-
"""In-app updater: реальный свап файлов на диске (Windows).

Тест дёргает НАСТОЯЩИЙ view /update/apply: тот распаковывает архив, пишет
задание и запускает помощника, а помощник ждёт маркер выхода приложения и
меняет файлы, пока «старые» заняты (запущенный exe нельзя ни удалить, ни
перезаписать). С включённым YP_UPDATER_E2E=1 помощник поднимается отдельным
процессом и свап идёт по-настоящему. Проверяется:

  * новая версия встаёт на место, новый exe запускается;
  * данные пользователя (.env, logs/, output/) свап НЕ трогает — помощник
    сам является сборкой и создаёт эти папки у себя, их нельзя зеркалить;
  * старые файлы уходят в _update/_backup для отката;
  * устаревший архив (версия внутри ниже объявленной) ОТВЕРГАЕТСЯ и удаляется
    — баг «обновлятор ставит предыдущий опубликованный релиз»;
  * адрес архива привязан к ОБЪЯВЛЕННОЙ версии: алиас
    `releases/latest/download/...` отдаёт предыдущий релиз, пока новый —
    черновик (или удалён), и использовать его нельзя.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parent.parent

REAL_SWAP = os.environ.get("YP_UPDATER_E2E") == "1"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A fake frozen-Windows installation: exe + _internal + user data."""
    app_root = tmp_path / "app"
    (app_root / "_internal").mkdir(parents=True)
    shutil.copy(r"C:\Windows\System32\where.exe", app_root / "YandexBusinessParser.exe")
    (app_root / "_internal" / "core.txt").write_text("OLD", encoding="utf-8")
    (app_root / ".env").write_text("API_KEY=1", encoding="utf-8")
    (app_root / "logs").mkdir()
    (app_root / "logs" / "run.log").write_text("keep me", encoding="utf-8")

    from routes import update as update_mod
    monkeypatch.setattr(update_mod, "_is_frozen", lambda: True)
    monkeypatch.setattr(update_mod, "_self_update_supported", lambda: True)
    monkeypatch.setattr(update_mod, "_app_root", lambda: app_root)
    monkeypatch.setattr(update_mod, "_work_dir", lambda: _ensure(app_root / "_update"))
    # os._exit would kill the test process — record the call instead. The
    # view MUST schedule it: without the hard exit the running exe stays
    # locked and the updater rolls back to the old version.
    state = {"exited": False}

    def _fake_exit(code):
        state["exited"] = True

    monkeypatch.setattr(os, "_exit", _fake_exit)

    app = Flask(__name__)
    app.register_blueprint(update_mod.bp)
    return {"client": app.test_client(), "app_root": app_root,
            "work": app_root / "_update", "update": update_mod,
            "state": state}


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _make_zip(tmp_path: Path, version: str) -> Path:
    """A release zip the way CI builds it: exe + _internal at the top level."""
    stage = tmp_path / "stage"
    (stage / "_internal" / "static").mkdir(parents=True)
    shutil.copy(r"C:\Windows\System32\robocopy.exe", stage / "YandexBusinessParser.exe")
    (stage / "_internal" / "core.txt").write_text("NEW", encoding="utf-8")
    (stage / "_internal" / "static" / "version.json").write_text(
        '{"version": "%s"}' % version, encoding="utf-8")
    zip_path = tmp_path / "update.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for p in sorted(stage.rglob("*")):
            z.write(p, p.relative_to(stage))
    return zip_path


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="updater.bat is Windows-only")
class TestRealSwap:
    @pytest.mark.skipif(
        not REAL_SWAP,
        reason="реальный свап поднимает помощника отдельным процессом и стартует exe "
               "— включается вручную: YP_UPDATER_E2E=1")
    def test_swap_installs_the_new_version_and_keeps_user_data(self, env, tmp_path, monkeypatch):
        client, app_root, work = env["client"], env["app_root"], env["work"]
        zip_path = _make_zip(tmp_path, "9.9.9")
        monkeypatch.setattr(env["update"], "_state",
                            lambda: {"latest": "9.9.9",
                                     "download": {"file": str(zip_path)}})

        #В сборке помощник — это НОВЫЙ exe приложения с --apply-update.
        # В тесте «новая сборка» — чужие exe (where.exe/robocopy.exe), а они
        # флаг не понимают, поэтому помощник запускается тем же модулем, но
        # отдельным процессом: свап идёт по-настоящему, файлы и блокировки —
        # настоящие. Что /update/apply передаёт флаг и путь к заданию,
        # проверяет test_apply_spawns_the_python_helper_with_a_job_file.
        real_popen = subprocess.Popen

        def spawn(cmd, **kw):
            job = cmd[2]
            kw.pop("cwd", None)          # у помощника свой рабочий каталог
            return real_popen([sys.executable, "-m", "updater_helper", job],
                              cwd=str(ROOT), **kw)

        monkeypatch.setattr(env["update"].subprocess, "Popen", spawn)

        # Simulate the running app: lock the exe and a file inside _internal
        # for a few seconds (the window before the process exits). The real
        # app exits ~1 s after writing the marker; the helper's retry loop
        # must ride out exactly this kind of short lock.
        lock1 = open(app_root / "YandexBusinessParser.exe", "rb")
        lock2 = open(app_root / "_internal" / "core.txt", "rb")
        try:
            r = client.post("/update/apply")
            assert r.status_code == 200
            assert r.get_json()["ok"] is True
            time.sleep(4)          # the «application is still shutting down» window
        finally:
            lock1.close()
            lock2.close()
        # The hard exit was scheduled (os._exit ~1s after the response).
        exit_deadline = time.time() + 5
        while time.time() < exit_deadline and not env["state"]["exited"]:
            time.sleep(0.1)
        assert env["state"]["exited"], "update_apply must os._exit to release the exe lock"

        # A CI runner is heavily loaded: the bat's ping-based waits and the
        # start of the new exe can take tens of seconds — give it 90s.
        deadline = time.time() + 90
        core = app_root / "_internal" / "core.txt"
        while time.time() < deadline:
            if core.exists() and core.read_text(encoding="utf-8") == "NEW":
                break
            time.sleep(0.5)

        # New version installed...
        log = ""
        try:
            log = (work / "update.log").read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
        assert (app_root / "_internal" / "core.txt").read_text(
            encoding="utf-8") == "NEW", f"swap failed; updater log:\n{log}"
        assert (app_root / "YandexBusinessParser.exe").exists()
        # ...user data untouched...
        assert (app_root / ".env").read_text(encoding="utf-8") == "API_KEY=1"
        assert (app_root / "logs" / "run.log").read_text(encoding="utf-8") == "keep me"
        # ...the old version kept for rollback, and the run is logged.
        assert (work / "_backup" / "YandexBusinessParser.exe").exists()
        # «update completed» is written by the DETACHED bat — under heavy load
        # it may still be finishing (starting the exe, cleaning up) when the
        # assertions above already see the new files. Wait a little; what the
        # swap guarantees synchronously is: no rollback was performed.
        deadline = time.time() + 20
        while time.time() < deadline:
            log = (work / "update.log").read_text(encoding="utf-8", errors="replace")
            if "update completed" in log or "rollback" in log:
                break
            time.sleep(0.5)
        assert "rollback" not in log, f"updater rolled back; log:\n{log}"
        assert "update completed" in log, f"updater did not finish; log:\n{log}"
        # The exit marker is cleaned up after a successful swap.
        assert not (work / "app.exit").exists()

    def test_apply_spawns_the_python_helper_with_a_job_file(
            self, env, tmp_path, monkeypatch):
        """Вместо updater.bat — помощник из новой сборки и JSON-задание.

        .bat писался в cp866 и терял путь с кириллицей: обновление
        скачивалось, приложение закрывалось, файлы не менялись. Помощник
        получает пути нативно, поэтому кириллица и пробелы ему не мешают.
        """
        zip_path = _make_zip(tmp_path, "9.9.9")
        monkeypatch.setattr(env["update"], "_state",
                            lambda: {"latest": "9.9.9",
                                     "download": {"file": str(zip_path)}})
        spawned = {}
        monkeypatch.setattr(env["update"].subprocess, "Popen",
                            lambda cmd, **kw: spawned.setdefault("cmd", cmd))
        assert env["client"].post("/update/apply").status_code == 200
        cmd = spawned["cmd"]
        assert cmd[1] == "--apply-update", cmd
        job_path = Path(cmd[2])
        assert job_path == env["work"] / "update_job.json"
        job = json.loads(job_path.read_text(encoding="utf-8"))
        assert job["app_root"] == str(env["app_root"])
        assert job["src"].endswith("extracted")
        assert not (env["work"] / "updater.bat").exists()
        # Дождаться потока ЖЁСТКОГО завершения, пока os._exit ещё подменён.

        deadline = time.time() + 3
        while time.time() < deadline and not env["state"]["exited"]:
            time.sleep(0.05)
        assert env["state"]["exited"], "view must schedule the hard exit"

    def test_helper_swaps_files_and_keeps_user_data(self, env, tmp_path, monkeypatch):
        """Сам помощник: старые файлы — в backup, новые — на место, данные целы."""
        import updater_helper
        zip_path = _make_zip(tmp_path, "9.9.9")
        monkeypatch.setattr(env["update"], "_state",
                            lambda: {"latest": "9.9.9",
                                     "download": {"file": str(zip_path)}})
        monkeypatch.setattr(env["update"].subprocess, "Popen",
                            lambda cmd, **kw: None)
        assert env["client"].post("/update/apply").status_code == 200
        job = env["work"] / "update_job.json"
        monkeypatch.setattr(updater_helper, "_launch", lambda *a, **k: True)
        assert updater_helper.run(job) == 0
        assert (env["app_root"] / "_internal" / "core.txt").read_text(
            encoding="utf-8") == "NEW"
        assert (env["app_root"] / ".env").read_text(encoding="utf-8") == "API_KEY=1"
        assert (env["app_root"] / "logs" / "run.log").read_text(
            encoding="utf-8") == "keep me"
        assert (env["work"] / "update_result.json").exists()
        assert not (env["work"] / "app.exit").exists()

    def test_helper_rolls_back_when_copying_fails(self, env, tmp_path, monkeypatch):
        """Сбой копирования не оставляет пользователя без рабочей версии."""
        import updater_helper
        zip_path = _make_zip(tmp_path, "9.9.9")
        monkeypatch.setattr(env["update"], "_state",
                            lambda: {"latest": "9.9.9",
                                     "download": {"file": str(zip_path)}})
        monkeypatch.setattr(env["update"].subprocess, "Popen",
                            lambda cmd, **kw: None)
        assert env["client"].post("/update/apply").status_code == 200
        job = env["work"] / "update_job.json"
        monkeypatch.setattr(updater_helper, "_launch", lambda *a, **k: True)
        real_copy = updater_helper._copy

        def broken(src, dst):
            if src.name == "_internal":
                raise OSError("диск занят")
            return real_copy(src, dst)

        monkeypatch.setattr(updater_helper, "_copy", broken)
        assert updater_helper.run(job) == 1
        assert (env["app_root"] / "_internal" / "core.txt").read_text(
            encoding="utf-8") == "OLD"
        result = json.loads((env["work"] / "update_result.json").read_text(encoding="utf-8"))
        assert result["ok"] is False
        assert "диск занят" in result["error"]


    def test_stale_zip_is_refused_and_deleted(self, env, tmp_path, monkeypatch):
        client = env["client"]
        zip_path = _make_zip(tmp_path, "9.9.9")
        monkeypatch.setattr(env["update"], "_state",
                            lambda: {"latest": "10.0.0",          # advertised newer
                                     "download": {"file": str(zip_path)}})
        r = client.post("/update/apply")
        assert r.status_code == 409
        body = r.get_json()
        assert body["ok"] is False
        assert "не опубликован" in body["error"]
        # The stale zip is gone so the next attempt re-downloads.
        assert not zip_path.exists()

class TestHelperKeepsUserData:
    """Помощник не должен трогать данные пользователя в папке программы.

    Помощник — это новая сборка приложения, и при своём старте она создаёт
    output/, logs/ и app.log рядом с exe (в portable-режиме это и есть папка
    программы). Если зеркалить в приложение ВСЁ содержимое распакованной
    папки, то пустые папки помощника заменят настоящие результаты поисков,
    а старые уйдут в _backup и будут удалены вместе с ним.
    """

    def _setup(self, tmp_path, monkeypatch):
        app = tmp_path / "app"
        (app / "_internal").mkdir(parents=True)
        (app / "_internal" / "core.txt").write_text("OLD", encoding="utf-8")
        (app / "output").mkdir()
        (app / "output" / "keep.xlsx").write_bytes(b"results")
        (app / "logs").mkdir()
        (app / "logs" / "run.log").write_text("keep me", encoding="utf-8")
        (app / ".env").write_text("VK_TOKEN=1", encoding="utf-8")
        (app / "app.log").write_text("старый старт", encoding="utf-8")

        src = tmp_path / "extracted"
        (src / "_internal").mkdir(parents=True)
        (src / "_internal" / "core.txt").write_text("NEW", encoding="utf-8")
        (src / "YandexBusinessParser.exe").write_bytes(b"MZ")
        # Следы старта самого помощника в распакованной папке:
        (src / "output").mkdir()
        (src / "logs").mkdir()
        (src / "app.log").write_text("старт помощника", encoding="utf-8")

        work = tmp_path / "work"
        work.mkdir()
        (work / "app.exit").write_text("exit", encoding="ascii")
        job = work / "update_job.json"
        job.write_text(json.dumps({
            "app_root": str(app), "src": str(src),
            "backup": str(work / "_backup"),
            "marker": str(work / "app.exit"),
            "log": str(work / "update.log"),
        }, ensure_ascii=False), encoding="utf-8")

        import updater_helper
        monkeypatch.setattr(updater_helper, "_launch", lambda *a, **k: True)
        return app, job

    def test_swap_keeps_results_logs_and_env(self, tmp_path, monkeypatch):
        import updater_helper
        app, job = self._setup(tmp_path, monkeypatch)
        assert updater_helper.run(job) == 0
        # Программа обновилась…
        assert (app / "_internal" / "core.txt").read_text(encoding="utf-8") == "NEW"
        # …а данные пользователя остались на месте.
        assert (app / "output" / "keep.xlsx").read_bytes() == b"results"
        assert (app / "logs" / "run.log").read_text(encoding="utf-8") == "keep me"
        assert (app / ".env").read_text(encoding="utf-8") == "VK_TOKEN=1"
        assert (app / "app.log").read_text(encoding="utf-8") == "старый старт"

    def test_user_data_is_not_even_touched_by_the_swap(self, tmp_path, monkeypatch):
        """В журнале свапа нет ни output/, ни logs/, ни app.log."""
        import updater_helper
        app, job = self._setup(tmp_path, monkeypatch)
        assert updater_helper.run(job) == 0
        log = (tmp_path / "work" / "update.log").read_text(encoding="utf-8")
        for name in ("output", "logs", "app.log", ".env"):
            assert f"-> backup: {name}" not in log, log
            assert f"-> app: {name}" not in log, log
        assert "-> app: _internal" in log



class TestDownloadTarget:
    """Архив берётся только той версии, которую приложение объявило.

    Регресс 2.3.0 → 2.3.1: version.json штамповался ссылкой
    `releases/latest/download/...`, а этот алиас не видит черновики — пока
    новый релиз был черновиком (а потом был удалён из GitHub), он отдавал
    ПРЕДЫДУЩИЙ релиз. Обновлятор скачивал ту же версию, что уже стояла:
    «скачал обновление, консоль закрылась, версия та же».
    """

    ALIAS = ("https://github.com/o/r/releases/latest/download/"
             "YandexBusinessParser-windows-x64.zip")
    PINNED = ("https://github.com/o/r/releases/download/v2.3.1/"
              "YandexBusinessParser-windows-x64.zip")

    # ── адрес, привязанный к версии ───────────────────────────

    def test_alias_is_rejected_the_pinned_url_is_kept(self):
        from routes import update as update_mod
        assert update_mod._versioned_asset_url("2.3.1", self.ALIAS) == ""
        assert update_mod._versioned_asset_url("2.3.1", self.PINNED) == self.PINNED
        # адрес другого тега — тоже не то, что нужно
        assert update_mod._versioned_asset_url("2.3.2", self.PINNED) == ""

    def test_pinned_url_needs_no_network(self, monkeypatch):
        from routes import update as update_mod
        monkeypatch.setattr(update_mod, "_release_asset_url",
                            lambda *a, **k: pytest.fail("сеть не нужна"))
        url, why = update_mod._download_target("2.3.1", self.PINNED)
        assert url == self.PINNED and why == ""

    # ── фолбэк: точный тег через API ───────────────────────────

    def _patch_api(self, monkeypatch, *, status_code=200, payload=None):
        import requests
        seen = {}

        class _Resp:
            def __init__(self):
                self.status_code = status_code

            def json(self):
                return payload or {}

        def _get(url, *a, **k):
            seen["url"] = url
            return _Resp()

        monkeypatch.setattr(requests, "get", _get)
        from routes import update as update_mod
        monkeypatch.setattr(update_mod, "_state", lambda: {})
        monkeypatch.setattr(update_mod, "_save_state", lambda **k: None)
        return seen

    def test_exact_tag_is_resolved_through_the_api(self, monkeypatch):
        from routes import update as update_mod
        seen = self._patch_api(monkeypatch, payload={
            "draft": False,
            "assets": [{"name": update_mod.ZIP_ASSET_NAME,
                        "browser_download_url": self.PINNED}]})
        assert update_mod._release_asset_url("9.9.9", use_cache=False) == self.PINNED
        assert "/releases/tags/v9.9.9" in seen["url"]
        assert "/releases/latest" not in seen["url"]

    def test_draft_release_is_not_offered(self, monkeypatch):
        from routes import update as update_mod
        self._patch_api(monkeypatch, status_code=404)
        assert update_mod._release_asset_url("9.9.9", use_cache=False) == ""

    def test_pinned_url_must_point_at_the_asset_we_need(self):
        """version.json штампуется windows-ссылкой — но на macOS нужен .dmg.

        Привязанный к версии адрес годится, только если он ведёт на ТОТ файл,
        который нужен системе: иначе «скачать для macOS» отдавало .exe.
        """
        from routes import update as update_mod
        mac = ("https://github.com/o/r/releases/download/v2.3.1/"
               "YandexBusinessParser-macos-arm64.dmg")
        assert update_mod._versioned_asset_url("2.3.1", mac) == ""
        assert update_mod._versioned_asset_url(
            "2.3.1", mac, "YandexBusinessParser-macos-arm64.dmg") == mac
        assert update_mod._versioned_asset_url(
            "2.3.1", self.PINNED,
            "YandexBusinessParser-windows-x64.zip") == self.PINNED

    def test_asset_name_follows_the_platform(self, monkeypatch):
        import sys
        from routes import update as update_mod
        monkeypatch.setattr(sys, "platform", "win32")
        assert update_mod._release_asset_name(install=True) == update_mod.ZIP_ASSET_NAME
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(update_mod, "_mac_arch", lambda: "arm64")
        assert update_mod._release_asset_name(install=True).endswith("macos-arm64.dmg")
        assert update_mod._release_asset_name(install=False).endswith("macos-arm64.zip")

    def test_api_resolution_asks_for_the_requested_asset(self, monkeypatch):
        from routes import update as update_mod
        mac_asset = "YandexBusinessParser-macos-x64.dmg"
        mac_url = "https://github.com/o/r/releases/download/v9.9.9/" + mac_asset
        self._patch_api(monkeypatch, payload={
            "draft": False,
            "assets": [{"name": update_mod.ZIP_ASSET_NAME,
                        "browser_download_url": self.PINNED},
                       {"name": mac_asset, "browser_download_url": mac_url}]})
        assert update_mod._release_asset_url("9.9.9", mac_asset,
                                             use_cache=False) == mac_url

    def test_unpublished_version_gets_an_explanation(self, monkeypatch):
        from routes import update as update_mod
        monkeypatch.setattr(update_mod, "_release_asset_url", lambda *a, **k: "")
        url, why = update_mod._download_target("9.9.9", self.ALIAS)
        assert url == ""
        assert "не опубликован" in why

    # ── эндпоинт скачивания ────────────────────────────────────

    def test_download_refuses_an_unpublished_version(self, monkeypatch, tmp_path):
        from flask import Flask
        from routes import update as update_mod
        monkeypatch.setattr(update_mod, "_is_frozen", lambda: True)
        monkeypatch.setattr(update_mod, "_self_update_supported", lambda: True)
        monkeypatch.setattr(update_mod, "_user_dir", lambda: tmp_path)
        monkeypatch.setattr(update_mod, "_state", lambda: {})
        monkeypatch.setattr(update_mod, "_save_state", lambda **k: None)
        monkeypatch.setattr(update_mod, "_remote_meta",
                            lambda: {"version": "9.9.9",
                                     "download_url": self.ALIAS})
        monkeypatch.setattr(update_mod, "_release_asset_url", lambda *a, **k: "")
        app = Flask(__name__)
        app.register_blueprint(update_mod.bp)
        r = app.test_client().post("/update/download")
        assert r.status_code == 400
        assert "не опубликован" in r.get_json()["error"]


class TestLastUpdateResult:
    """Сбой помощника виден при следующем старте.

    Помощник ставит файлы, когда приложение уже закрыто: если он вернул
    старую версию, сообщить об этом некому — причина должна всплыть после
    перезапуска, иначе «нажал Обновить, окно закрылось, версия та же».
    """

    def _write(self, env, **kw):
        env["work"].mkdir(parents=True, exist_ok=True)
        (env["work"] / "update_result.json").write_text(
            json.dumps(kw, ensure_ascii=False), encoding="utf-8")

    def _status(self, env):
        return env["client"].get("/update/status").get_json()

    def test_a_failed_install_is_reported(self, env, monkeypatch):
        self._write(env, ok=False, error="диск занят",
                    version="9.9.9", at="2026-10-25 10:00:00")
        monkeypatch.setattr(env["update"], "_is_frozen", lambda: False)
        data = self._status(env)
        assert data["last_update"]["ok"] is False
        assert "диск занят" in data["last_update"]["error"]
        assert data["last_update"]["log"].endswith("update.log")

    def test_a_successful_install_of_the_running_version_is_not_noise(
            self, env, monkeypatch):
        from config import APP_VERSION
        self._write(env, ok=True, version=APP_VERSION)
        monkeypatch.setattr(env["update"], "_is_frozen", lambda: False)
        assert self._status(env)["last_update"] == {}

    def test_a_broken_result_file_does_not_break_the_status(self, env, monkeypatch):
        env["work"].mkdir(parents=True, exist_ok=True)
        (env["work"] / "update_result.json").write_text("{oops", encoding="utf-8")
        monkeypatch.setattr(env["update"], "_is_frozen", lambda: False)
        assert env["client"].get("/update/status").status_code == 200
