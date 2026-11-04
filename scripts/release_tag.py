"""Нормализация и проверка тега релиза — один код для воркфлоу и тестов.

Раньше это был bash с `tr` и `grep`: на Windows без MSYS шаг не запускался, и
тесты не могли проверить логику иначе как через подпроцесс. Теперь воркфлоу
зовёт этот скрипт, а тесты — его функции.
"""
import json
import os
import re
import subprocess
import sys

# Стабильный релиз: v2.3.4 или v2.2.1.1. Суффиксы -dev/-rc не публикуются сами.
RELEASE_RE = re.compile(r"^v\d+(?:\.\d+){2,3}$")
# Объявить версию можно и для четырёхзначного тега вида v2.2.1.1.
ANNOUNCE_RE = re.compile(r"^v\d+(?:\.\d+){2,}$")

# Чего ждём на релизе, чтобы объявить версию.
WINDOWS_ASSET = "YandexBusinessParser-windows-x64.zip"

# Чего ждём на черновике, чтобы публиковать: ровно то, что собирают build-*.
# Список здесь один на всех — его же берёт scripts/verify_release_assets.py.
REQUIRED_ASSETS = (
    "YandexBusinessParser-windows-x64.zip",
    "YandexBusinessParser-windows-x64-setup.exe",
    "YandexBusinessParser-macos-arm64.dmg",
    "YandexBusinessParser-macos-x64.dmg",
    "CHANGELOG.md",
)


def normalize_tag(raw: str) -> str:
    """« 2.3.4 » → «v2.3.4»: пробелы убираем, регистр ровняем, «v» дописываем."""
    tag = re.sub(r"\s+", "", raw or "").lower()
    if tag and not tag.startswith("v"):
        tag = "v" + tag
    return tag


def is_release_tag(tag: str) -> bool:
    return bool(RELEASE_RE.match(tag or ""))


def is_announce_tag(tag: str) -> bool:
    return bool(ANNOUNCE_RE.match(tag or ""))


def resolve(release_tag: str = "", input_tag: str = "", latest: str = "") -> tuple[str, str]:
    """Тег для объявления версии: событие → ручной ввод → последний релиз.

    Возвращает (tag, error). Пустой error — тег годен.
    """
    raw = release_tag or input_tag or latest
    tag = normalize_tag(raw)
    if not is_announce_tag(tag):
        return tag, f"не понял тег '{tag}' — нужен вид v2.3.4 (можно и без «v»)"
    return tag, ""


def publish_decision(raw_tag: str = "", input_tag: str = "") -> tuple[str, bool, str]:
    """Публиковать ли черновик по этому тегу.

    Ручной запуск — осознанное действие, поэтому плохой тег там ошибка; пуш
    ветки или dev-тега — тихий пропуск без красного конвейера.
    """
    tag = normalize_tag(raw_tag)
    if is_release_tag(tag):
        return tag, True, ""
    if input_tag:
        return tag, False, (
            f"'{input_tag}' не похоже на релизный тег — нужен вид v2.3.4 "
            "(можно и без «v»), без суффиксов -dev/-rc")
    return tag, False, ""


def draft_decision(payload, required=REQUIRED_ASSETS) -> tuple[str, tuple[str, ...]]:
    """Публиковать ли черновик: «ok», «absent», «published» или «missing» + файлы.

    `payload` — ответ `gh release view --json isDraft,assets`; None — релиза нет
    (черновик создаёт отдельный job, и это не ошибка).
    """
    if payload is None:
        return "absent", ()
    if not payload.get("isDraft"):
        return "published", ()
    names = {a.get("name", "") for a in (payload.get("assets") or [])}
    missing = tuple(name for name in required if name not in names)
    if missing:
        return "missing", missing
    return "ok", ()


def should_skip(announced: str, tag: str) -> bool:
    """Версия уже объявлена в version.json — объявлять нечего."""
    if not announced or not tag:
        return False
    return announced == (tag[1:] if tag.startswith("v") else tag)


def _write(path_var: str, lines: list[str]) -> None:
    path = os.environ.get(path_var)
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.writelines(line + "\n" for line in lines)


def _gh_release(tag: str, repo: str) -> dict | None:
    """Черновик с ассетами; None — черновика нет."""
    res = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo, "--json", "isDraft,assets"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        return None
    try:
        return json.loads(res.stdout or "{}")
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv else "announce"

    if mode == "announce":
        latest = ""
        if "--latest" in argv:
            latest = argv[argv.index("--latest") + 1]
        tag, error = resolve(os.environ.get("RELEASE_TAG", ""),
                             os.environ.get("INPUT_TAG", ""), latest)
        if error:
            print(f"::error::{error}")
            return 1
        _write("GITHUB_ENV", [f"TAG={tag}"])
        print(f"TAG={tag}")
        print(f"Объявляем версию {tag}")
        return 0

    if mode == "publish":
        tag, publish, error = publish_decision(os.environ.get("RAW_TAG", ""),
                                              os.environ.get("INPUT_TAG", ""))
        print(f"Тег: '{os.environ.get('RAW_TAG', '')}' → '{tag}'")
        if error:
            print(f"::error::{error}")
            return 1
        if not publish:
            print("Не стабильный релизный тег — публиковать нечего, выходим.")
            _write("GITHUB_OUTPUT", ["publish=false"])
            return 0
        _write("GITHUB_OUTPUT", [f"tag={tag}", "publish=true"])
        print(f"tag={tag}")
        print("publish=true")
        return 0

    if mode == "draft":
        tag = os.environ.get("TAG", "")
        payload = _gh_release(tag, os.environ.get("REPO", ""))
        verdict, missing = draft_decision(payload)
        if verdict == "absent":
            print(f"Черновика {tag} нет (его создаёт job release-draft) — "
                  "публиковать нечего.")
            _write("GITHUB_OUTPUT", ["ok=false", "published=false"])
            return 0
        if verdict == "published":
            print(f"Релиз {tag} уже опубликован — объявляем версию без повторной публикации.")
            _write("GITHUB_OUTPUT", ["ok=false", "published=true"])
            return 0
        if verdict == "missing":
            print(f"::error::на черновике {tag} нет файлов: {', '.join(missing)} — "
                  "публикация отложена.")
            return 1
        print(f"Черновик {tag} готов к публикации: все файлы на месте.")
        _write("GITHUB_OUTPUT", ["ok=true", "published=false"])
        return 0

    print(f"::error::неизвестный режим '{mode}'")
    return 2


if __name__ == "__main__":
    sys.exit(main())
