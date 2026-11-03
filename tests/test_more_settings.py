"""Два шага в сайдборе и окно «Ещё настройки».

Пользователь видел пять разделов и десятки полей, не понимая, что обязательно,
а что «по вкусу». Теперь на первом экране только «Что и где ищем» и «Сколько
собирать», а технические разделы живут в окне с тремя вкладками.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates/index.html").read_text(encoding="utf-8")
JS = (ROOT / "static/js/14-more-settings.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static/css/11-redesign-sidebar.css").read_text(encoding="utf-8")


def test_sidebar_offers_volume_choices_and_a_counter():
    # Карточки рисует JS из сохранённого списка: четыре готовых варианта —
    # семена первого запуска, а не жёсткая разметка.
    assert 'id="effort-choices"' in TEMPLATE
    for name, note in (("Быстро", "первые 20 организаций с города"),
                       ("Обычный", "две страницы с города"),
                       ("Тщательно", "все страницы и полные карточки"),
                       ("Своё", "ваши настройки")):
        assert f"name: '{name}'" in JS, name
        assert note in JS, name
    assert 'id="effort-estimate"' in TEMPLATE
    assert "function renderEffortCards" in JS
    assert "function setSearchEffort" in JS and "function updateEffortEstimate" in JS
    assert "EFFORT_DEFAULTS" in JS
    # Выбор запоминается между запусками приложения.
    assert "search-effort" in JS
    # Счётчик объясняет объём словами, а не только числом.
    assert "организац" in JS
    # Для нескольких городов видно, сколько приходится на каждый.
    assert "на город" in JS


def test_more_settings_window_has_four_tabs():
    assert 'id="more-settings"' in TEMPLATE
    assert 'role="dialog" aria-modal="true"' in TEMPLATE
    for pane in ("effort", "work", "result"):
        assert f'data-ms-pane="{pane}"' in TEMPLATE, pane
    assert "function openMoreSettings" in JS
    assert "function setMoreSettingsTab" in JS
    assert "function closeMoreSettings" in JS
    # Окно закрывается и мышью по подложке, и клавишей Escape.
    assert 'onclick="closeMoreSettings()"' in TEMPLATE
    assert "event.key !== 'Escape'" in JS
    # Отдельной ссылки «Ещё настройки» больше нет: окно открывают шестерёнки.
    assert 'id="btn-more-settings"' not in TEMPLATE
    assert "openEffortVariant" in JS


def test_filter_presets_explain_what_they_keep():
    for name in ("Строгий", "Обычный", "Широкий"):
        assert f"<b>{name}</b>" in TEMPLATE, name
    assert 'id="filter-presets"' in TEMPLATE
    assert "function applyFilterPreset" in JS
    assert "FILTER_PRESETS" in JS
    # Пресет только выставляет существующие переключатели — не прячет их.
    for fn in ("setMinScore", "setParseMode", "setSocialMode"):
        assert fn in JS, fn
    assert ".flt-preset.active{" in STYLE


def test_module_is_loaded_last():
    assert "js/14-more-settings.js" in TEMPLATE
    assert TEMPLATE.index("js/13-spheres.js") < TEMPLATE.index("js/14-more-settings.js")


def test_setup_chips_open_the_window_on_the_right_tab():
    """Чип сводки «Объём»/«Тип»/«Форматы» ведёт в окно, а не в невидимую секцию."""
    setup = (ROOT / "static/js/12-setup-summary.js").read_text(encoding="utf-8")
    assert "openMoreSettings(tab)" in setup
    for section, tab in (("acc-tech", "work"), ("acc-filters", "result"),
                         ("acc-formats", "result")):
        assert f"'{section}': '{tab}'" in setup, section


def test_volume_cards_can_be_added_renamed_and_deleted():
    """Шестерёнка открывает настройки варианта в общем окне; карточку можно
    переименовать, добавить новую и удалить лишнюю."""
    assert "function openEffortVariant" in JS
    assert "function addEffortCard" in JS and "function deleteEffortCard" in JS
    assert 'onclick="addEffortCard()"' in TEMPLATE
    assert 'onclick="deleteEffortCard()"' in TEMPLATE
    assert 'id="ee-name"' in TEMPLATE and 'id="ee-note"' in TEMPLATE
    assert 'id="ee-pages"' in TEMPLATE and 'id="ee-candidates"' in TEMPLATE
    assert 'id="ee-delete"' in TEMPLATE
    # Свои варианты живут в браузере пользователя.
    assert "effort-cards" in JS
    assert "localStorage" in JS
    # Правка сохраняется сразу: отдельного диалога и кнопки «Сохранить» нет.
    assert "function saveEffortEditor" in JS
    assert 'id="effort-editor"' not in TEMPLATE


def test_more_settings_window_does_not_jump():
    """Окно больше не прыгает: у него фиксированная высота, а страница под ним
    не прокручивается."""
    assert "height:min(680px,88vh)" in STYLE
    assert "body.app-modal-open{overflow:hidden}" in STYLE
    assert "function lockPageScroll" in JS
    assert "lockPageScroll();" in JS

