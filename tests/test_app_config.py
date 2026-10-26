# -*- coding: utf-8 -*-
"""Конфигурация запуска и состав сборки: порты и то, чего в сборке быть не должно."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


class TestAppPort:
    def test_release_listens_on_the_public_port(self, monkeypatch):
        import config
        monkeypatch.delenv("YP_PORT", raising=False)
        monkeypatch.setattr(config.sys, "platform", "win32")
        assert config.app_port() == 5000

    def test_macos_release_avoids_the_airplay_port(self, monkeypatch):
        """На macOS 5000 занят системным AirPlay Receiver."""
        import config
        monkeypatch.delenv("YP_PORT", raising=False)
        monkeypatch.setattr(config.sys, "platform", "darwin")
        assert config.app_port() == config.MAC_PORT == 5050

    def test_env_variable_wins_and_garbage_is_ignored(self, monkeypatch):
        import config
        monkeypatch.setattr(config.sys, "platform", "win32")
        monkeypatch.setenv("YP_PORT", "5080")
        assert config.app_port() == 5080
        monkeypatch.setenv("YP_PORT", "не-порт")
        assert config.app_port() == 5000
        monkeypatch.setenv("YP_PORT", "70000")     # вне диапазона портов
        assert config.app_port() == 5000
        monkeypatch.setattr(config.sys, "platform", "darwin")
        assert config.app_port() == 5050           # fallback тоже platform-aware


class TestPackaging:
    def test_windows_spec_drops_browser_automation(self):
        """Playwright и curl_cffi исключены из Windows-сборки: страницы читает
        только настоящий Chrome по CDP, а встроенный Chromium (~300 МБ) и
        подмена TLS-отпечатка вместе с прямыми HTTP-запросами убраны."""
        spec = (ROOT / "parser.spec").read_text(encoding="utf-8")
        for excluded in ("'playwright'", "'curl_cffi'", "'greenlet'"):
            assert excluded in spec, excluded
        # Модуля HTTP/Playwright-движка в проекте больше нет.
        assert not (ROOT / "yandex_maps_parser" / "browser_client.py").exists()
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        assert "browser_client" not in app

    def test_sender_removed_from_app(self):
        """Массовая рассылка удалена по юридическим соображениям:
        ни blueprint, ни модуля, ни упоминаний в спеках сборки."""
        assert not (ROOT / "routes" / "sender.py").exists()
        assert not (ROOT / "vk_sender").exists()
        for spec in ("parser.spec", "parser-mac.spec"):
            text = (ROOT / spec).read_text(encoding="utf-8")
            assert "vk_sender" not in text, spec
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        assert "sender_bp" not in app
        # Соглашение при входе: серверная фиксация согласия в settings.json.
        api = (ROOT / "routes" / "api.py").read_text(encoding="utf-8")
        assert "terms/status" in api and "terms/accept" in api
        assert "TERMS_VERSION" in api


DEV_BUILD_MARKERS = (
    "is_dev_build", "DEV_BUILD", "YP_DEV", "DEV_PORT",
    "YandexBusinessParserDev", "app-dev", "build-dev", "dist-dev",
)


class TestNoDevBuild:
    """Сборки разработчика в проекте больше нет: ни отдельного порта, ни имени,
    ни метки в шапке, ни обхода авто-обновления."""

    FILES = (
        "config.py", "app.py", "paths.py", "build-mac.sh",
        "parser.spec", "parser-mac.spec",
        "static/js/09-ui-extras.js", "templates/index.html",
        ".github/workflows/build-exe.yml", ".github/workflows/build-manual.yml",
        ".gitignore",
    )

    @pytest.mark.parametrize("name", FILES)
    def test_the_markers_are_gone(self, name):
        text = (ROOT / name).read_text(encoding="utf-8")
        for marker in DEV_BUILD_MARKERS:
            assert marker not in text, f"{name}: остался след dev-сборки «{marker}»"

    def test_the_dev_test_file_is_gone(self):
        assert not (ROOT / "tests" / "test_dev_build.py").exists()
