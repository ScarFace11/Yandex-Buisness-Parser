# -*- coding: utf-8 -*-
"""Применить скачанное обновление после выхода приложения.

Запускается НОВОЙ сборкой из распакованного архива:

    YandexBusinessParser.exe --apply-update <путь к update_job.json>

Почему отдельный помощник, а не .bat: путь к папке приложения может содержать
кириллицу и пробелы, а cmd.exe в cp866 такие пути теряет. Python работает с
путями нативно и на любой локали. Помощник ждёт маркер app.exit, переносит
старые файлы в _update/_backup, копирует новые и запускает приложение. Если
что-то не получилось — возвращает старую версию на место и запускает её,
чтобы пользователь не остался без программы.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0)
CREATE_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
EXE_NAME = "YandexBusinessParser.exe"

# Данные пользователя и служебные метки: в архив обновления они не входят и
# рядом с программой живут только в portable-режиме. Помощник — это та же
# сборка, поэтому при своём старте она успевает создать здесь output/, logs/
# и app.log. Если зеркалить всё подряд, эти пустые папки заменят настоящие
# результаты поисков. Такие имена не трогаем ни в одну сторону.
USER_DATA_NAMES = frozenset({
    "output", "logs", ".env", "settings.json", "sender_config.json",
    "api_keys.json", "spheres.json", "app.log", "update.log",
    "_update", ".installed", ".portable", "portable.txt",
})


def _log(log: Path, text: str) -> None:
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    except OSError:
        pass


def _remove(path: Path) -> None:
    """Удалить файл/папку, если они есть; ошибки не прерывают обновление."""
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except OSError:
            pass


def _wait_marker(marker: Path, timeout: float = 60.0) -> bool:
    """Ждём, пока приложение запишет app.exit прямо перед os._exit()."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists():
            return True
        time.sleep(0.5)
    return False


def _move_with_retry(src: Path, dst: Path, attempts: int = 40) -> None:
    """Перенести файл/папку, пережидая блокировку антивирусом/процессом."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for _ in range(attempts):
        try:
            if dst.exists():
                _remove(dst)
            shutil.move(str(src), str(dst))
            return
        except OSError as exc:       # WinError 32/5: файл ещё открыт
            last = exc
            time.sleep(0.5)
    raise last or OSError(f"не удалось перенести {src}")


def _copy(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _entries(src: Path) -> list[Path]:
    return sorted(src.iterdir(), key=lambda p: p.name.lower())


def _swap(app: Path, src: Path, backup: Path, log: Path,
          moved: list[str], copied: list[str]) -> None:
    """Старые файлы — в backup, новые — в app. Трогаем только имена из архива.

    Данные пользователя (output/, logs/, .env, …) пропускаем: они не часть
    сборки, а помощник создаёт их в распакованной папке ещё до свапа.
    """
    backup.mkdir(parents=True, exist_ok=True)
    entries = [e for e in _entries(src) if e.name not in USER_DATA_NAMES]
    _log(log, f"swap: {src} -> {app}, файлов верхнего уровня: {len(entries)}")
    for entry in entries:
        target = app / entry.name
        if target.exists():
            _move_with_retry(target, backup / entry.name)
            moved.append(entry.name)
            _log(log, f"  old -> backup: {entry.name}")
    for entry in entries:
        copied.append(entry.name)
        _copy(entry, app / entry.name)
        _log(log, f"  new -> app: {entry.name}")
    if not (app / EXE_NAME).exists():
        raise RuntimeError(f"после копирования нет {EXE_NAME}")
    if not (app / "_internal").is_dir():
        raise RuntimeError("после копирования нет папки _internal")


def _rollback(app: Path, src: Path, backup: Path, log: Path,
              moved: list[str], copied: list[str]) -> None:
    """Вернуть файлы, которые были до обновления.

    `moved` — старые файлы, уже убранные в backup; `copied` — новые, которые
    начали копироваться. Файл, который не трогали, не удаляем: иначе сбой на
    первом же шаге стирал бы рабочую установку.
    """
    _log(log, "rollback: возвращаю предыдущую версию")
    touched = set(moved) | set(copied)
    for entry in _entries(src):
        if entry.name not in touched:
            continue
        old = backup / entry.name
        target = app / entry.name
        try:
            if entry.name in moved and old.exists():
                _remove(target)
                _move_with_retry(old, target)
                _log(log, f"  restored: {entry.name}")
            elif entry.name in copied:
                _remove(target)
                _log(log, f"  removed new: {entry.name}")
        except OSError as exc:
            _log(log, f"  rollback error {entry.name}: {exc}")


def _launch(app: Path, log: Path, attempts: int = 10) -> bool:
    exe = app / EXE_NAME
    for _ in range(attempts):
        try:
            subprocess.Popen(
                [str(exe)],
                cwd=str(app),
                creationflags=DETACHED | CREATE_GROUP,
                close_fds=True,
            )
            _log(log, f"started {exe}")
            return True
        except OSError as exc:
            _log(log, f"start failed: {exc}")
            time.sleep(1.0)
    return False


def run(job_path: str | os.PathLike) -> int:
    """Точка входа помощника. 0 — обновление применено."""
    job_file = Path(job_path)
    try:
        job = json.loads(job_file.read_text(encoding="utf-8"))
        app = Path(job["app_root"])
        src = Path(job["src"])
        backup = Path(job["backup"])
        marker = Path(job["marker"])
        log = Path(job["log"])
        zip_path = Path(job["zip_path"]) if job.get("zip_path") else None
    except Exception as exc:
        # Без журнала сообщать некуда — код выхода увидят только логи ОС.
        print(f"update job error: {exc}", file=sys.stderr)
        return 2

    _log(log, "updater helper started")
    if not _wait_marker(marker):
        _log(log, "no app.exit marker after 60s, proceeding anyway")
    time.sleep(2.0)                        # дать процессу отпустить exe/_internal

    moved: list[str] = []
    copied: list[str] = []
    try:
        _swap(app, src, backup, log, moved, copied)
    except Exception as exc:
        _log(log, f"FAILED: {exc}")
        try:
            _rollback(app, src, backup, log, moved, copied)
        finally:
            _write_result(job, False, str(exc), log)
            _launch(app, log)
        return 1

    _write_result(job, True, "", log)
    if not _launch(app, log):
        _log(log, "new version copied, but launch failed — попробуйте запустить вручную")
        return 1

    # Чистим только служебное: пользовательские данные лежат в AppData/exe-папке
    # и в backup не попадали.
    time.sleep(1.0)
    _remove(src)
    if zip_path:
        _remove(zip_path)
    _remove(backup)
    _remove(marker)
    try:
        job_file.unlink()
    except OSError:
        pass
    _log(log, "update completed")
    return 0


def _write_result(job: dict, ok: bool, error: str, log: Path) -> None:
    """Результат для экрана диагностики: даже если приложение не поднялось."""
    try:
        path = Path(job["log"]).with_name("update_result.json")
        path.write_text(json.dumps({
            "ok": ok,
            "error": error,
            "version": _bundled_version(job),
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        _log(log, f"result write failed: {exc}")


def _bundled_version(job: dict) -> str:
    try:
        path = Path(job["src"]) / "_internal" / "static" / "version.json"
        if not path.exists():
            path = Path(job["src"]) / "static" / "version.json"
        return str(json.loads(path.read_text(encoding="utf-8-sig")).get("version") or "")
    except Exception:
        return ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: updater_helper.py <update_job.json>", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(sys.argv[1]))
