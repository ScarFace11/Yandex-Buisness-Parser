"""Нормализация и проверка тега релиза — один код для воркфлоу и тестов.

Раньше это был bash с `tr` и `grep`: на Windows без MSYS шаг не запускался, и
тесты не могли проверить логику иначе как через подпроцесс. Теперь воркфлоу
зовёт этот скрипт, а тесты — его функции.
"""
import os
import re
import sys

# Стабильный релиз: v2.3.4 или v2.2.1.1. Суффиксы -dev/-rc не публикуются сами.
RELEASE_RE = re.compile(r"^v\d+(?:\.\d+){2,3}$")
# Объявить версию можно и для четырёхзначного тега вида v2.2.1.1.
ANNOUNCE_RE = re.compile(r"^v\d+(?:\.\d+){2,}$")

# Чего ждём на релизе, чтобы объявить версию.
WINDOWS_ASSET = "YandexBusinessParser-windows-x64.zip"


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

    print(f"::error::неизвестный режим '{mode}'")
    return 2


if __name__ == "__main__":
    sys.exit(main())
