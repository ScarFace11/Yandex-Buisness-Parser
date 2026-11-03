# -*- coding: utf-8 -*-
"""Сбор без интерфейса: `app.py --run` (headless.py).

Проверяем то, что нельзя увидеть глазами до запуска: какие параметры реально
уйдут в движок, что dry-run ничего не запускает и что код возврата отличает
«собралось» от «не смогло».

Настоящий сбор здесь не запускается: `runner.run_web` подменяется. Это
принципиально — тест не должен ни открывать браузер, ни ходить в Яндекс.

Запуск: python -m pytest tests/test_headless.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import headless


@pytest.fixture()
def run_web(monkeypatch):
    """Подмена движка: запоминаем параметры и возвращаем «файлы»."""
    calls = []
    from yandex_maps_parser import runner

    def fake(params, log):
        calls.append(params)
        return ["results.xlsx"]

    monkeypatch.setattr(runner, "run_web", fake)
    return calls


def test_dry_run_sends_nothing_to_the_engine(capsys, run_web):
    assert headless.main(["--queries", "кафе", "--cities", "Уфа", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "кафе" in out and "Уфа" in out
    assert "сбор не запускался" in out
    assert run_web == [], "dry-run не должен доходить до движка"


def test_parameters_go_to_the_engine_as_the_form_builds_them(run_web):
    code = headless.main(["--queries", "кафе, бар", "--cities", "Уфа",
                          "--pages", "3", "--workers", "4", "--max", "50",
                          "--formats", "csv,map"])
    assert code == 0
    params = run_web[0]
    assert params["queries"] == ["кафе", "бар"]
    assert params["cities"] == ["Уфа"]
    assert params["max_pages"] == 3
    assert params["max_workers"] == 4
    assert params["max_candidates"] == 50
    assert params["output_csv"] is True and params["output_map"] is True
    assert params["output_excel"] is False and params["output_json"] is False


def test_defaults_are_the_same_as_the_form(capsys, run_web):
    assert headless.main(["--queries", "кафе", "--cities", "Уфа"]) == 0
    params = run_web[0]
    assert params["max_pages"] == 1
    assert params["max_workers"] == 20
    assert params["max_candidates"] == 200
    assert params["output_excel"] and params["output_json"]
    assert params["pipeline"] == "raw" and params["fetch_detail"] is True


def test_queries_and_cities_are_required():
    """Без городов сбор бессмысленен: argparse отвергает запуск до движка."""
    with pytest.raises(SystemExit):
        headless.main(["--queries", "кафе"])


def test_unknown_flag_is_refused(capsys):
    assert headless.main(["--queries", "кафе", "--cities", "Уфа", "--nope"]) == 2
    assert "Незнакомые аргументы" in capsys.readouterr().err


def test_failure_of_the_engine_is_reported(monkeypatch, capsys):
    from yandex_maps_parser import runner

    def boom(params, log):
        raise RuntimeError("нет браузера")

    monkeypatch.setattr(runner, "run_web", boom)
    code = headless.main(["--queries", "кафе", "--cities", "Уфа"])
    assert code == 1
    assert "нет браузера" in capsys.readouterr().err


def test_presets_are_gone_from_the_cli():
    """Пресеты удалены: старые флаги должны отвергаться, а не молча игнорироваться."""
    with pytest.raises(SystemExit):
        headless._parser().parse_args(["--preset", "старый", "--list-presets"])
