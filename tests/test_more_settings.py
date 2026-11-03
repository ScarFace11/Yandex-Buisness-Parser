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
                       ("Тщательно", "все страницы и полные карточки"),
                       ("Своё", "ваши настройки")):
        assert f'<span class="effort-name" data-effort-name>{name}</span>' in TEMPLATE, name
        assert note in TEMPLATE, name
    assert 'id="effort-estimate"' in TEMPLATE
    assert "function setSearchEffort" in JS and "function updateEffortEstimate" in JS
    assert "EFFORT_DEFAULTS" in JS
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
    assert "event.key !== 'Escape'" in JS, "Escape закрывает окно и редактор"
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


def test_volume_cards_can_be_edited_and_renamed():
    """Шестерёнка в углу карточки открывает состав прогона и позволяет
    переписать название с описанием; «Своё» — такая же карточка."""
    cards = TEMPLATE[TEMPLATE.index('class="effort-choices"'):TEMPLATE.index('id="effort-estimate"')]
    # В описаниях не осталось технических слов про ВК: их место — в редакторе.
    assert "ВК" not in cards and "ВКонтакте" not in cards
    for key in ("fast", "normal", "thorough", "custom"):
        assert f'data-effort-edit="{key}"' in cards, key
        assert ("onclick=\"openEffortEditor('%s')\"" % key) in cards, key
    assert "function openEffortEditor" in JS
    assert "function saveEffortEditor" in JS
    assert 'id="ee-name"' in TEMPLATE and 'id="ee-note"' in TEMPLATE
    assert 'id="ee-pages"' in TEMPLATE and 'id="ee-candidates"' in TEMPLATE
    assert 'id="ee-save"' in TEMPLATE and ">Сохранить</button>" in TEMPLATE
    # Свои варианты живут в браузере пользователя.
    assert "effort-presets" in JS
    assert "localStorage" in JS


def test_more_settings_window_does_not_jump():
    """Окно больше не прыгает: у него фиксированная высота, а страница под ним
    не прокручивается."""
    assert "height:min(680px,88vh)" in STYLE
    assert "body.app-modal-open{overflow:hidden}" in STYLE
    assert "function lockPageScroll" in JS
    assert "lockPageScroll();" in JS

