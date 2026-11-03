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


def test_sidebar_offers_three_volume_choices_and_a_counter():
    for name, note in (("Быстро", "первые 20 организаций с города"),
                       ("Обычный", "две страницы с города"),
                       ("Тщательно", "проверка активности ВК")):
        assert f'<span class="effort-name">{name}</span>' in TEMPLATE, name
        assert note in TEMPLATE, name
    assert 'id="effort-estimate"' in TEMPLATE
    assert "function setSearchEffort" in JS and "function updateEffortEstimate" in JS
    assert "EFFORT_PRESETS" in JS
    # Выбор запоминается между запусками приложения.
    assert "search-effort" in JS
    # Счётчик объясняет объём словами, а не только числом.
    assert "организац" in JS


def test_more_settings_window_has_three_tabs():
    assert 'id="more-settings"' in TEMPLATE
    assert 'role="dialog" aria-modal="true"' in TEMPLATE
    for pane in ("data", "filters", "files"):
        assert f'data-ms-pane="{pane}"' in TEMPLATE, pane
    assert "function openMoreSettings" in JS
    assert "function setMoreSettingsTab" in JS
    assert "function closeMoreSettings" in JS
    # Окно закрывается и мышью по подложке, и клавишей Escape.
    assert 'onclick="closeMoreSettings()"' in TEMPLATE
    assert "event.key === 'Escape'" in JS
    # Ссылка «Ещё настройки» — маленькая и под счётчиком, а не раздел сайдбора.
    assert 'id="btn-more-settings"' in TEMPLATE
    assert 'class="more-settings-link"' in TEMPLATE


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
    for section, tab in (("acc-tech", "data"), ("acc-filters", "filters"),
                         ("acc-formats", "files")):
        assert f"'{section}': '{tab}'" in setup, section

