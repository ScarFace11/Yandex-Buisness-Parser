# -*- coding: utf-8 -*-
"""Общие фикстуры сквозных тестов интерфейса.

Приложение и браузер поднимаются один раз на весь прогон: запуск Chromium
занимает секунды, а тесты интерфейса (контраст, доступность, клавиатура)
идут один за другим и пользуются одним и тем же окном.

Оба ресурса возвращаются на место в любом исходе, включая skip: сквозные
тесты не должны менять состояние модулей для других тестов (от этого зависел
порядок файлов — см. tests/test_cdp_timeout.py, который ждёт исходный UA).
"""
import os
import sys

import pytest

from tests._browser import LiveApp, load_real_websocket


def pytest_collection_modifyitems(config, items):
    """Сетевые проверки — только по явному разрешению.

    Полный прогон запускают и без интернета: живая проба тогда не падает
    быстро, а висит на загрузке страницы Яндекса. Маркер `live` делает такие
    тесты пропускаемыми по умолчанию; осознанный запуск — YP_LIVE_TESTS=1.
    """
    if os.getenv("YP_LIVE_TESTS", "").strip().lower() in ("1", "true", "yes"):
        return
    skip = pytest.mark.skip(
        reason="живая сетевая проверка отключена; включите YP_LIVE_TESTS=1")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def live_app_url():
    """Живое приложение на свободном порту (тот же код, что и у пользователя)."""
    app = LiveApp()
    try:
        yield app.url
    finally:
        app.close()


@pytest.fixture(scope="session")
def browser_cdp():
    """Браузер пользователя под управлением CDP или явный skip.

    Тот же путь, что и при поиске: cdp_client выбирает любой Chromium в
    системе. Если браузера нет (чужой ноутбук, CI без Chrome), тесты
    интерфейса пропускаются с причиной — отсутствие браузера не означает,
    что интерфейс недоступен.
    """
    previous_ws = sys.modules.get("websocket")
    real_ws = load_real_websocket()
    if real_ws is None:
        pytest.skip("websocket-client не установлен — сквозная проверка интерфейса невозможна")
    sys.modules["websocket"] = real_ws
    try:
        from yandex_maps_parser import cdp_client

        if cdp_client._find_chrome() is None:
            pytest.skip("нет браузера на Chromium — сквозная проверка интерфейса невозможна")
        # init_browser подстраивает UA под реальную версию браузера (это нужно
        # поиску). Здесь UA возвращается как был, и сразу: он меняется ДО
        # создания вкладок, поэтому даже неудачный запуск его оставляет.
        original_ua = cdp_client._CDP_USER_AGENT
        started = cdp_client.init_browser(pool_size=1)
        cdp_client._CDP_USER_AGENT = original_ua
        if not started and not os.environ.get("YP_CHROME_FLAGS"):
            # В ограниченном окружении (песочница вокруг процесса) Chrome
            # выходит с 0x80000003 ещё до открытия CDP-порта. Повторяем запуск
            # без песочницы, но только для проверок: приложение по умолчанию
            # её не снимает (см. cdp_client._extra_chrome_flags).
            os.environ["YP_CHROME_FLAGS"] = "--no-sandbox"
            started = cdp_client.init_browser(pool_size=1)
            cdp_client._CDP_USER_AGENT = original_ua
        if not started:
            pytest.skip("браузер на Chromium не запустился — проверка интерфейса пропущена")
        try:
            yield cdp_client
        finally:
            cdp_client.close_browser()
            cdp_client._CDP_USER_AGENT = original_ua
    finally:
        if previous_ws is not None:
            sys.modules["websocket"] = previous_ws
        else:
            sys.modules.pop("websocket", None)
