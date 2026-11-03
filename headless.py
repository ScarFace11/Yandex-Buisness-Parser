# -*- coding: utf-8 -*-
"""Сбор из консоли без интерфейса: `app.py --run --queries … --cities …`."""
import argparse
import re
import sys
import time

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# Уровни, которые в консоли не нужны: sys/tech — отладка, progress — пинги квоты (их десятки на город).
_QUIET_LEVELS = {"sys", "tech", "progress"}


def _strip(text: str) -> str:
    return _ANSI_RE.sub("", str(text or ""))


def make_logger(verbose: bool = False):
    """log_fn для run_web: строки с понятным префиксом, без ANSI и мусора."""
    prefixes = {"ok": "✔ ", "warn": "▲ ", "error": "✖ ", "result": "• "}

    def log(level: str, msg: str) -> None:
        if not verbose and level in _QUIET_LEVELS:
            return
        line = _strip(msg).replace("\r", " ").strip()
        if not line:
            return
        try:
            print(prefixes.get(level, "  ") + line, flush=True)
        except (OSError, ValueError):
            pass          # закрытая консоль не должна убивать прогон

    return log


def describe(params: dict) -> str:
    """Человеческая сводка того, что будет запущено (для --dry-run и шапки)."""
    formats = [name for name, key in (("Excel", "output_excel"), ("JSON", "output_json"),
                                      ("CSV", "output_csv"), ("HTML-карта", "output_map"))
               if params.get(key)]
    cities = params.get("cities") or []
    queries = params.get("queries") or []
    lines = [
        f"Запросы ({len(queries)}): {', '.join(queries) or '—'}",
        f"Города ({len(cities)}): {', '.join(cities) or '—'}",
        f"Форматы: {', '.join(formats) or '—'}",
        f"Страниц на точку: {params.get('max_pages')} · потоков: {params.get('max_workers')}"
        f" · лимит организаций: {params.get('max_candidates')}",
        f"Режим: {'только без сайтов' if params.get('parse_mode') == 'without_website' else 'все организации'}"
        f" · соцсети: {params.get('social_mode')}"
        + (" · сетка точек" if params.get("use_grid") else ""),
    ]
    if params.get("blacklist_words"):
        lines.append(f"Исключить слова: {', '.join(params['blacklist_words'])}")
    if params.get("continue_cities"):
        lines.append("Непрерывный режим: после выбранных городов — следующие по каталогу")
    return "\n".join(lines)


def _as_int(value, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_list(value) -> list[str]:
    """Строка «кафе, кофейня» / переносы строк → список строк."""
    parts = str(value or "").replace(chr(13), chr(10)).replace(",", chr(10)).split(chr(10))
    return [part.strip() for part in parts if part.strip()]


def build_params(args) -> dict:
    """Параметры run_web из флагов командной строки (значения — как в форме)."""
    formats = {f.strip().lower() for f in
               str(args.formats or "").replace(";", ",").split(",") if f.strip()}
    return {
        "queries": _as_list(args.queries),
        "cities": _as_list(args.cities),
        "output_excel": not formats or bool(formats & {"excel", "xlsx"}),
        "output_json": not formats or "json" in formats,
        "output_csv": "csv" in formats,
        "output_map": bool(formats & {"map", "html"}),
        "max_pages": max(1, _as_int(args.pages, 1)),
        "max_workers": max(1, _as_int(args.workers, 20)),
        "max_candidates": max(0, _as_int(args.max_candidates, 200)),
        # Двухэтапный сбор — как в интерфейсе: сначала raw, потом фильтры.
        "pipeline": "raw",
        "parse_mode": "without_website",
        "social_mode": "all",
        "fetch_detail": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app.py --run",
        description="Сбор без запуска интерфейса: запросы и города — флагами.",
    )
    parser.add_argument("--run", action="store_true",
                        help="выполнить сбор и выйти (флаг для app.py)")
    parser.add_argument("--queries", required=True,
                        help="запросы через запятую")
    parser.add_argument("--cities", required=True,
                        help="города через запятую")
    parser.add_argument("--pages", type=int, default=None, help="страниц на точку")
    parser.add_argument("--workers", type=int, default=None, help="потоков на карточки")
    parser.add_argument("--max", dest="max_candidates", type=int, default=None,
                        help="максимум организаций на город")
    parser.add_argument("--formats", default="",
                        help="форматы выгрузки через запятую: excel,json,csv,map")
    parser.add_argument("--dry-run", action="store_true",
                        help="только показать, что будет запущено")
    parser.add_argument("--verbose", action="store_true",
                        help="печатать технические строки лога")
    return parser


def main(argv: list[str] | None = None) -> int:
    args, unknown = _parser().parse_known_args(argv or [])
    if unknown:
        print(f"Незнакомые аргументы: {' '.join(unknown)}", file=sys.stderr)
        return 2

    params = build_params(args)
    if not params["queries"] or not params["cities"]:
        print("Нужны запросы и города: --queries «кафе» --cities «Уфа».", file=sys.stderr)
        return 2

    print("═" * 62)
    print("  Сбор без интерфейса — параметры командной строки")
    print("═" * 62)
    print(describe(params))
    print("─" * 62)

    if args.dry_run:
        print("Проверка параметров: сбор не запускался (--dry-run).")
        return 0

    started = time.time()
    try:
        from yandex_maps_parser import runner
        files = runner.run_web(params, make_logger(args.verbose))
    except KeyboardInterrupt:
        print("\nОстановлено пользователем — собранное сохранено.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nСбор не выполнился: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    elapsed = time.time() - started
    print("─" * 62)
    print(f"Готово за {int(elapsed // 60)} мин {int(elapsed % 60):02d} с · файлов: {len(files or [])}")
    for name in (files or []):
        print(f"  • {name}")
    try:
        from paths import results_root
        print(f"Папка результатов: {results_root()}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
