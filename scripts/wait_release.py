"""Ожидание опубликованного релиза с windows-архивом.

Логика вынесена из bash в функции: тесты проверяют тот же код, который
исполняет воркфлоу, — без подпроцесса, заглушек `gh` и `tr`/`grep`.
"""
import json
import os
import subprocess
import sys
import time

from release_tag import WINDOWS_ASSET, should_skip

REQUIRED_HINT = f"нужен ОПУБЛИКОВАННЫЙ релиз с файлом {WINDOWS_ASSET}"


def release_verdict(payload, asset_suffix: str = WINDOWS_ASSET) -> str:
    """Что с релизом: «ok», «draft», «no-asset:<имена>» или «unreadable».

    Ответ `gh` без нужных полей не должен валить шаг трейсбеком: такой ответ
    всё равно не «готово».
    """
    if payload is None:
        return "unreadable"
    if payload.get("isDraft"):
        return "draft"
    names = [a.get("name", "") for a in (payload.get("assets") or [])]
    if any(name.endswith(asset_suffix) for name in names):
        return "ok"
    return "no-asset:" + (",".join(names) or "файлов нет")


def wait_for_release(fetch, tag: str, attempts: int = 15, pause: float = 10,
                     log=print, sleep=time.sleep) -> tuple[bool, str]:
    """Ждём релиз до `attempts` попыток. `fetch(tag)` бросает, если релиза нет."""
    reason = ""
    for attempt in range(1, attempts + 1):
        try:
            payload = fetch(tag)
        except Exception as exc:  # релиз ещё не создан, удалён или тег не тот
            payload = None
            reason = str(exc) or "неизвестная ошибка gh"
        else:
            reason = release_verdict(payload)
            if reason == "ok":
                log(f"Релиз {tag} опубликован и содержит windows-архив")
                return True, reason
        log(f"Ждём: {tag} — {reason}")
        if attempt < attempts:
            sleep(pause)
    log(f"::error::{tag} не объявлен ({reason or 'нет данных'}): "
        f"{REQUIRED_HINT} — version.json не тронут")
    return False, reason


def _gh_release(tag: str) -> dict:
    res = subprocess.run(["gh", "release", "view", tag, "--json", "isDraft,assets"],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    if res.returncode != 0:
        lines = (res.stderr or res.stdout or "").strip().splitlines()
        raise RuntimeError(lines[0] if lines else "release not found")
    return json.loads(res.stdout or "{}")


def _append(path_var: str, line: str) -> None:
    path = os.environ.get(path_var)
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    tag = os.environ.get("TAG", "")
    if "--tag" in argv:
        tag = argv[argv.index("--tag") + 1]
    announced = os.environ.get("ANNOUNCED", "")
    if should_skip(announced, tag):
        print(f"Версия {announced} уже объявлена — выходим.")
        _append("GITHUB_ENV", "SKIP=1")
        return 0
    attempts = int(os.environ.get("WR_ATTEMPTS", "15"))
    pause = float(os.environ.get("WR_SLEEP", "10"))
    ok, _reason = wait_for_release(_gh_release, tag, attempts=attempts, pause=pause)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
