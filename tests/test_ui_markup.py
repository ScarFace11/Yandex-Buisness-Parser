"""Разметка и CSS: проверки по тексту шаблона и стилей.

Дешёвые, но злые тесты. Логику ловят node-тесты в tests/ui, а здесь —
то, что живёт только в разметке: исчезнувшие кнопки, вернувшаяся
сортировка по «#», «ядовитые» цвета тёмной темы и автосохранение
отметок «Просмотрено».
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
from tests._appjs import read_app_js
from tests._css import css_files, read_css
APP_JS = read_app_js()
API_PY = (ROOT / "routes" / "api.py").read_text(encoding="utf-8")
STYLE = read_css()

DARK_MARKER = '[data-theme="dark"]'
DARK_TOKEN_BLOCK = STYLE[STYLE.index(DARK_MARKER + "{"):]


def dark_rule_lines() -> str:
    """Только строки правил `[data-theme="dark"] …{…}` (без комментариев).

    Так палитра проверяется именно там, где она работает: светлая тема
    трогать не должна, а комментарии — тем более.
    """
    keep, inside, depth = [], False, 0
    for line in STYLE.split("\n"):
        if not inside and line.startswith(DARK_MARKER):
            inside, depth = True, 0
        if inside:
            if not line.strip().startswith("/*"):
                keep.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                inside = False
    return "\n".join(keep)


class TestDedupButtonRemoved:
    """«⊘ Дубли» дублировала «Объединять филиалы сетей» — кнопки больше нет."""

    def test_button_is_gone_from_the_toolbar(self):
        assert "btn-dedup" not in TEMPLATE
        assert "⊘ Дубли" not in TEMPLATE

    def test_handler_and_styles_are_gone_too(self):
        assert "function deduplicateResults" not in APP_JS
        assert "btn-dedup" not in APP_JS
        assert "btn-dedup" not in STYLE

    def test_chain_merging_stays_in_the_filter_accordion(self):
        assert 'id="f-collapse-chains"' in TEMPLATE
        assert 'id="f-chain-key"' in TEMPLATE


class TestNumberColumnNotSortable:
    """«#» — порядковый номер строки, а не поле данных."""

    def test_header_has_no_sort_handler(self):
        assert 'onclick="sortTable(1)"' not in TEMPLATE
        assert re.search(r'<th class="nosort"[^>]*>#</th>', TEMPLATE)

    def test_style_kills_cursor_and_arrows(self):
        assert "#results-table th.nosort{cursor:default}" in STYLE
        assert '#results-table th.nosort::after{content:""}' in STYLE

    def test_js_ignores_the_number_column(self):
        assert "const NOSORT_COLS = new Set([0, 1]);" in APP_JS
        assert "if (NOSORT_COLS.has(col)) return;" in APP_JS
        # сортировка по «#» тянула индекс строки в компараторе
        assert "filteredRows.indexOf(a)" not in APP_JS


class TestReviewedAutosave:
    """Отметки «Просмотрено» не должны теряться без ручной кнопки."""

    def test_status_indicator_exists(self):
        assert 'id="reviewed-save-status"' in TEMPLATE

    def test_manual_button_is_renamed(self):
        assert 'id="bulk-persist-btn"' in TEMPLATE
        assert "Сохранить сейчас</button>" in TEMPLATE
        assert "💾 Отметки в файлы" not in TEMPLATE

    def test_js_wires_every_autosave_trigger(self):
        for needle in ("REVIEWED_AUTOSAVE_MS", "markReviewedDirty",
                       "autoPersistReviewed", "persistReviewedOnLeave"):
            assert needle in APP_JS, needle
        assert "window.addEventListener('pagehide'" in APP_JS
        assert "visibilitychange" in APP_JS
        assert "navigator.sendBeacon" in APP_JS or "nav.sendBeacon" in APP_JS

    def test_debounce_is_five_seconds(self):
        assert "const REVIEWED_AUTOSAVE_MS = 5000;" in APP_JS


class TestThemeInit:
    """Тёмная тема ставится до первой отрисовки и не мигает."""

    def test_theme_is_applied_in_the_head_before_the_stylesheet(self):
        head = TEMPLATE[:TEMPLATE.index("</head>")]
        assert "yp_theme_v1" in head, "тема должна ставиться до загрузки CSS"
        assert "document.documentElement.setAttribute('data-theme'" in head
        assert head.index("yp_theme_v1") < head.index('"00-tokens.css"')

    def test_switch_is_animated_for_a_quarter_second(self):
        assert "theme-anim" in STYLE

    def test_dark_section_is_parsed_at_all(self):
        assert dark_rule_lines().count("[data-theme=") > 100


class TestDarkPalette:
    def test_token_block_defines_the_soft_palette(self):
        block = DARK_TOKEN_BLOCK[:DARK_TOKEN_BLOCK.index("\n}")]
        for token in ("--bg:", "--card:", "--panel:", "--field:", "--term:",
                      "--bdr:", "--bdr-h:", "--txt:", "--sub:", "--muted:",
                      "--hdr:", "--c:", "--row-alt:", "--row-hover:"):
            assert token in block, token

    def test_background_is_not_black_and_text_is_not_white(self):
        """Тёмная тема — графит и мягкий светлый текст, а не #000/#fff.

        Значения менялись (2026-09: фон стал ровнее, без синего уклона),
        но правило осталось: чистого чёрного и чистого белого в теме нет.
        """
        block = DARK_TOKEN_BLOCK[:DARK_TOKEN_BLOCK.index("\n}")]
        assert "--bg:#101216" in block
        assert "--txt:#E6E9EF" in block

    def test_no_acid_colours_left_in_the_dark_rules(self):
        rules = dark_rule_lines()
        for bad in ("#14B8A6", "#14b8a6", "#0F1419", "#0f1419", "#11161b",
                    "#1A1F24", "#1F2937", "#F3F4F6", "#9CA3AF", "#007E8C",
                    "#374151", "#4B5563", "#EF4444", "#F59E0B", "#10B981"):
            assert bad not in rules, f"{bad} вернулся в тёмную тему — нужен var(--…)"

    def test_dark_rules_pull_from_tokens(self):
        rules = dark_rule_lines()
        assert rules.count("var(--") > 200, "тёмная тема должна жить на токенах"

    def test_stylesheet_braces_balance(self):
        css = re.sub(r"/\*.*?\*/", "", STYLE, flags=re.S)
        assert css.count("{") == css.count("}"), "CSS сломан: фигурные скобки не сходятся"


class TestFileHistoryBulkActions:
    """История файлов: массовое удаление, массовый архив и снятие выбора.

    Все три кнопки появляются вместе с первым отмеченным файлом. Иконки в
    карточках — инлайновые SVG (эмодзи 🗑 рисовалось монохромно и пропадало
    на тёмном фоне), а «Удалить выбранные» в тёмной теме не должно сливаться
    с панелью."""
    IDS = ("btn-files-bulk-delete", "btn-files-bulk-archive", "btn-files-bulk-cancel")

    def test_three_bulk_buttons_exist_and_are_wired(self):
        for bid in self.IDES if hasattr(self, "IDES") else self.IDS:
            assert f'id="{bid}"' in TEMPLATE, bid
        for handler in ("bulkDeleteSelected()", "bulkArchiveSelected()", "clearFileSelection()"):
            assert f'onclick="{handler}"' in TEMPLATE, handler

    def test_js_exposes_the_archive_and_clear_handlers(self):
        for fn in ("function bulkArchiveSelected(", "function clearFileSelection(",
                   "function onFileSelect("):
            assert fn in APP_JS, fn
        assert "action: 'archive'" in APP_JS, "массовый архив идёт батчем через /files/action"

    def test_card_actions_are_theme_aware_svg_not_emoji(self):
        assert "const FILE_ACT_ICONS = {" in APP_JS
        assert "stroke=\"currentColor\"" in APP_JS
        assert '>🗑</button>' not in APP_JS, "эмодзи-мусорка не наследует цвет темы"
        assert "📥</button>" not in APP_JS

    def test_danger_icon_has_a_colour_in_both_themes(self):
        assert ".file-btn.danger{color:var(--err-strong)}" in STYLE
        assert '[data-theme="dark"] .file-btn.danger{color:var(--err-txt)}' in STYLE
        assert '[data-theme="dark"] .file-btn.danger:hover' in STYLE

    def test_bulk_delete_is_red_in_the_dark_theme_too(self):
        dark = dark_rule_lines()
        assert '[data-theme="dark"] .btn-sm.danger,[data-theme="dark"] .files-bulk-btn{' in dark
        rule = dark[dark.index('[data-theme="dark"] .btn-sm.danger,[data-theme="dark"] .files-bulk-btn{'):]
        rule = rule[: rule.index("}")]
        assert "border-color:var(--red)" in rule
        assert "color:var(--err-txt)" in rule
        # Полупрозрачный --err-bdr (*.45) делал кнопку серой — его тут быть не должно.
        assert "--err-bdr" not in rule


class TestFocusIsVisibleInBothThemes:
    """Рамка фокуса: раньше кольцо брали из --c-soft (8%) — на тёмном поле
    его не видно, а часть правил использовала светлый литерал."""

    def test_focus_ring_token_is_defined_in_both_themes(self):
        light = STYLE[STYLE.index(":root{"):]
        light = light[: light.index("\n}")]
        dark = DARK_TOKEN_BLOCK[: DARK_TOKEN_BLOCK.index("\n}")]

        def alpha(block):
            m = re.search(r"--focus-ring:rgba\([^)]*,\s*([0-9.]+)\)", block)
            assert m, "--focus-ring объявлен не через rgba"
            return float(m.group(1))

        assert alpha(light) >= 0.1, "в светлой теме кольцо не должно исчезнуть"
        # В светлой теме плотность оставляем прежней (как до появления токена):
        # заметность там даёт бирюзовая обводка поля, а плотное свечение
        # читалось как лишнее выделение.
        assert alpha(light) <= 0.2, "в светлой теме кольцо не должно бросаться в глаза"
        assert alpha(dark) > alpha(light) * 3, "на тёмном поле кольцо обязано быть плотнее"

    def test_focus_rules_use_the_token(self):
        """Правила, которые РИСУЮТ рамку фокуса, обязаны брать её из токена."""
        css = re.sub(r"/\*.*?\*/", "", STYLE, flags=re.S)
        for rule in re.finditer(r"([^{}]*(?:focus|focus-within|focus-visible)[^{}]*)\{([^}]*)\}", css):
            selector, body = rule.group(1), rule.group(2)
            where = selector.strip()[-60:]
            assert "rgba(26,122,138" not in body, f"светлый литерал в правиле фокуса: {where}"
            # Строка вида `.stepper input:focus{outline:none;box-shadow:none}`
            # НЕ рисует фокус — рамку рисует .stepper:focus-within, поэтому
            # такие правила пропускаем.
            visible = [d for d in body.split(";")
                       if d.split(":")[0].strip() in ("box-shadow", "outline", "border-color")
                       and d.split(":", 1)[1].strip() not in ("none", "0", "0px")]
            if not visible or "var(--" in body:
                continue
            raise AssertionError(f"фокус без токена: {where} → {body.strip()}")

    def test_range_and_tiles_get_a_focus_state(self):
        assert "input[type=range]:focus-visible" in STYLE
        tiles = (".soc-tile", ".parse-mode-opt", ".social-mode-opt",
                 ".vk-mode-opt", ".source-mode-opt", ".grid-mode-opt")
        for tile in tiles:
            assert f"{tile}:has(input:focus-visible)" in STYLE, tile
        # Регресс: `:focus-within` обводил плитку по клику мышью (фокус уходил
        # в скрытое радио) — подсветка, которой пользователь не просил.
        for tile in tiles:
            assert f"{tile}:focus-within" not in STYLE, tile

    def test_checkboxes_and_radios_get_a_keyboard_focus_ring(self):
        """На коробке 14px свечение токена не различить, а в светлой теме
        у сфокусированного чекбокса не было видимого состояния вообще."""
        # Чекбокс — обычное видимое поле (рамка и по клику мышью).
        assert "input[type=checkbox]:focus{" in STYLE
        # Радио спрятаны в плитках: рамка только для клавиатуры, иначе она
        # светилась бы у всей плитки при клике — то самое лишнее выделение.
        assert "input[type=radio]:focus-visible{" in STYLE
        assert "input[type=radio]:focus{" not in STYLE

    def test_closed_reveal_does_not_leak_a_strip(self):
        """Закрытая секция (grid-template-rows:0fr) не показывает полоску
        контента: верхний отступ живёт только у открытого блока."""
        for rule in re.finditer(r"([^{}]*\.tiles-inner[^{}]*)\{([^}]*)\}", STYLE):
            selector, body = rule.group(1), rule.group(2)
            if "padding-top" in body:
                assert ".open" in selector, f"отступ у закрытого блока: {selector.strip()}"
        rule = re.search(r"#output-advanced \.tiles-inner\{([^}]*)\}", STYLE)
        assert rule, "нет правила #output-advanced .tiles-inner"
        assert "padding-top" not in rule.group(1), "padding даёт утечку в закрытом виде"
        assert "#output-advanced.open .tiles-inner{padding-top:8px}" in STYLE


class TestOutputFolderSettings:
    """«Куда сохранять»: одна папка (или своя на каждый этап) вместо output/."""

    def test_form_has_the_folder_field_and_buttons(self):
        for needle in ('id="f-output-dir"', 'id="btn-output-browse"', 'id="btn-output-save"',
                       'id="btn-output-default"', 'id="btn-output-open"',
                       'id="f-output-advanced"',
                       'id="f-output-raw"', 'id="f-output-processed"', 'id="f-output-archive"',
                       'id="output-dir-hint"', 'id="output-dir-err"'):
            assert needle in TEMPLATE, needle

    def test_handlers_exist(self):
        for fn in ("function loadOutputDir(", "function saveOutputDir(", "function resetOutputDir(",
                   "function pickOutputDir(", "function openOutputDir(",
                   "function onOutputAdvancedToggle(",
                   "function applyOutputDirState("):
            assert fn in APP_JS, fn
        assert "'/output-dir'" in APP_JS and "'/folder-picker'" in APP_JS
        assert "'/output/open'" in APP_JS, "кнопка «Открыть» не зовёт сервер"

    def test_hint_explains_that_service_files_stay_put(self):
        assert "Ключи, кэш найденного и история остаются" in APP_JS

    def test_server_side_routes_exist(self):
        api = (ROOT / "routes" / "api.py").read_text(encoding="utf-8")
        assert '@bp.route("/output-dir", methods=["GET"])' in api
        assert '@bp.route("/output-dir", methods=["POST"])' in api
        assert '@bp.route("/folder-picker", methods=["POST"])' in api
        assert '@bp.route("/output/open", methods=["POST"])' in api, "нет кнопки «Открыть папку» на сервере"


class TestNotificationSettings:
    """Попап настроек уведомлений: главный тумблер + два типа, два разных звука.

    Логику (черновик, откат, гейт по типам) проверяют node-тесты в
    tests/ui/notifications.test.mjs — здесь только разметка, стили и то,
    что звук перестал зависеть от разрешения браузера.
    """

    def test_header_button_keeps_ids_and_opens_the_popover(self):
        # id кнопки/иконки/подписи — контракт: их читает updateNotifyBtn.
        for needle in ('id="btn-notify"', 'id="notify-icon"', 'id="notify-txt"'):
            assert needle in TEMPLATE, needle
        assert 'onclick="toggleNotifyPopover(event)"' in TEMPLATE
        assert 'aria-haspopup="dialog"' in TEMPLATE

    def test_popover_has_master_and_two_type_switches(self):
        for needle in ('id="notify-pop"', 'id="notify-master"', 'id="notify-city"',
                       'id="notify-search"', 'id="notify-save"', 'id="notify-perm-hint"'):
            assert needle in TEMPLATE, needle
        assert TEMPLATE.count('role="switch"') == 3
        assert TEMPLATE.count('aria-checked=') == 3
        assert 'role="dialog"' in TEMPLATE

    def test_save_button_starts_disabled(self):
        """Пока ничего не изменено — сохранять нечего."""
        assert re.search(r'id="notify-save"[^>]*\bdisabled', TEMPLATE)

    def test_ios_switch_styles(self):
        start = STYLE.index('.tgl{')
        block = STYLE[start:start + 400]
        assert 'width:44px' in block and 'height:24px' in block
        assert '.tgl.on{' in STYLE, 'нет включённого состояния'
        assert '.tgl::after' in STYLE, 'нет ползунка'
        assert '.tgl:disabled' in STYLE, 'подтумблеры должны гаснуть с мастером'

    def test_switch_colours_live_in_tokens_for_both_themes(self):
        light = STYLE[STYLE.index(':root{'):]
        light = light[: light.index('\n}')]
        dark = DARK_TOKEN_BLOCK[: DARK_TOKEN_BLOCK.index('\n}')]
        for token in ('--tgl-off', '--tgl-on', '--knob'):
            assert token + ':' in light, f'{token} не объявлен в светлой теме'
            assert token + ':' in dark, f'{token} не объявлен в тёмной теме'
        # «Вкл» остаётся зелёным, но не неоновым: эмеральд #10B981 из макета был
        # самым насыщенным пятном на нейтральном экране. Проверяем сам смысл:
        # зелёный канал ведёт, а разброс каналов умеренный.
        for block in (light, dark):
            hexv = re.search(r'--tgl-on:\s*(#[0-9a-fA-F]{6})', block).group(1)
            r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
            assert g > r and g > b, f'тумблер «вкл» должен быть зелёным: {hexv}'
            assert max(r, g, b) - min(r, g, b) < 140, f'«вкл» слишком насыщенный: {hexv}'

    def test_popover_has_fixed_width_and_mobile_layout(self):
        assert 'width:320px' in STYLE
        assert '.notify-pop{position:fixed' in STYLE, 'нет раскладки на узком экране'
        # Кнопка остаётся доступной на узком экране — иначе попап не открыть.
        assert '#btn-notify{display:none}' not in STYLE
        assert '#notify-txt{display:none}' in STYLE

    def test_sounds_are_distinct_and_not_gated_by_notification_permission(self):
        for fn in ('function playCityDoneSound(', 'function playDoneSound('):
            assert fn in APP_JS, fn
        for fn in ('playCityDoneSound', 'playDoneSound'):
            body = APP_JS[APP_JS.index('function ' + fn + '('):]
            body = body[: body.index('\n}')]
            assert 'Notification' not in body, f'{fn} всё ещё зависит от разрешения'
        # Один общий контекст вместо нового на каждый сигнал.
        assert 'function audioCtx(' in APP_JS
        assert APP_JS.count('new (window.AudioContext') == 0
        assert "[[880, 1760]]" in APP_JS, 'звук города'
        assert '[523, 659, 784, [1047, 2093]]' in APP_JS, 'финальная мелодия'

    def test_settings_key_and_per_type_gate(self):
        assert "const NOTIFY_KEY = 'notifications_settings'" in APP_JS
        assert 'function notifyAllowed(' in APP_JS
        assert 'function notifyCityComplete(' in APP_JS
        assert 'function notifySearchComplete(' in APP_JS
        # Триггеры больше не смотрят на общий флаг напрямую.
        assert 'notifyCityComplete({ name, idx, total, status, records })' in APP_JS
        assert 'notifySearchComplete({' in APP_JS
        assert APP_JS.count("notificationsEnabled && Notification") == 0

    def test_sound_pickers_and_volume_slider_are_in_the_popover(self):
        for needle in ('id="notify-sound-city"', 'id="notify-sound-search"',
                       'id="notify-play-city"', 'id="notify-play-search"',
                       'id="notify-volume"', 'id="notify-vol-val"'):
            assert needle in TEMPLATE, needle
        assert 'type="range"' in TEMPLATE, 'нет ползунка громкости'
        # Кнопка «Прослушать» на каждый тип события.
        assert TEMPLATE.count('onclick="previewNotifySound(') == 2
        assert 'onchange="notifySoundChanged(\'city\')"' in TEMPLATE
        assert 'onchange="notifySoundChanged(\'search\')"' in TEMPLATE
        assert 'oninput="notifyVolumeInput()"' in TEMPLATE
        assert 'onchange="notifyVolumeCommit()"' in TEMPLATE

    def test_presets_live_in_one_registry_and_stay_pure_code(self):
        """Пресеты — только тоны Web Audio: ни .mp3, ни base64 в разметке."""
        assert 'const SOUND_PRESETS = {' in APP_JS
        assert 'const SOUND_DEFAULTS' in APP_JS
        assert 'const VOLUME_DEFAULT' in APP_JS
        for fn in ('_fillSoundSelect', 'previewNotifySound', 'notifySoundChanged',
                   'playNotifySound', 'notifyVolumeInput', 'notifyVolumeCommit'):
            assert 'function ' + fn + '(' in APP_JS, fn
        # Звук синтезируется кодом: ни файлов, ни base64-вложений.
        assert 'data:audio' not in APP_JS
        assert 'new Audio(' not in APP_JS
        # Пресетов несколько и подписи — в реестре, а не в разметке.
        assert APP_JS.count('label:') >= 4
        assert 'id="notify-sound-city" aria-label' in TEMPLATE

    def test_volume_and_preset_are_persisted_with_the_type_flags(self):
        for key in ('volume:', 'sound_city:', 'sound_search:'):
            assert key in APP_JS, key
        # Громкость 0 — валидная настройка: exponentialRamp от нуля уронил бы звук.
        assert 'Math.max(0.0001' in APP_JS
        assert 'function _notifyVolume(' in APP_JS
        assert 'function _notifySound(' in APP_JS

    def test_header_button_base_does_not_leak_into_the_popover(self):
        """Попап живёт ВНУТРИ .hdr-right, и базовый стиль кнопок шапки
        (прозрачный фон + белая рамка) перебивал его содержимое: тумблеры
        теряли фон, «Сохранить» становился белым на белом в светлой теме,
        «▶» — белой стрелкой на белой карточке. Селектор шапки теперь только
        по прямым детям.
        """
        assert '.hdr-right > button,' in STYLE
        assert '.hdr-right .notify-wrap > button' in STYLE, 'кнопка уведомлений потеряла вид'
        assert '.hdr-right button{' not in STYLE, 'базовое правило снова ловит попап'
        assert '.hdr-right button,' not in STYLE.replace('.hdr-right > button,', '')

    def test_popover_controls_declare_their_own_look(self):
        """Фон, рамка и цвет у тумблера, «Сохранить» и «▶» — свои."""
        for sel in ('.notify-save{', '.notify-play{', '.tgl{', '.notify-snd select{'):
            block = STYLE[STYLE.index(sel) + len(sel):]
            block = block[: block.index('}')]
            assert 'background' in block, sel
            assert 'font-family:inherit' in block or sel == '.tgl{', sel
        for sel in ('.notify-save{', '.notify-play{'):
            block = STYLE[STYLE.index(sel) + len(sel):]
            block = block[: block.index('}')]
            assert 'color:var' in block, sel

    def test_sound_row_styles_use_theme_tokens(self):
        assert '.notify-snd{' in STYLE and '.notify-play{' in STYLE
        assert '.notify-row-vol input[type="range"]' in STYLE
        assert '.notify-vol-val{' in STYLE
        assert 'accent-color:var(--c)' in STYLE


class TestFilterAccordionGroups:
    """«Фильтрация результата»: группы вместо одиннадцати блоков подряд.

    Аккордеон читался как один длинный список, редкие настройки тонули в
    середине, а кнопка «Применить фильтры заново» уезжала за нижнюю кромку
    сайдбора. Теперь это группы с подзаголовками, «Дополнительно»
    свёрнуто по умолчанию, а действие — в sticky-футере.
    """

    def _section(self) -> str:
        """Разметка одного аккордеона «03. Фильтрация результата»."""
        body = TEMPLATE[TEMPLATE.index('id="acc-filters"'):]
        return body[: body.index("</section>")]

    def _rule(self, selector: str) -> str:
        assert selector in STYLE, f"нет правила {selector}"
        block = STYLE[STYLE.index(selector) + len(selector):]
        return block[: block.index("}")]

    @staticmethod
    def _title(name: str) -> str:
        """Подзаголовок группы — без значков: эмодзи ушли из подписей."""
        return f'<div class="flt-group-title">{name}</div>'

    def test_groups_with_subtitles(self):
        sec = self._section()
        for name in ("Качество", "Тип компании", "Оценка лида", "Активность",
                     "Обработка", "Исключить по словам"):
            assert self._title(name) in sec, name
        assert sec.count('class="flt-group"') == 6
        # Порядок — от частого к редкому: оценка лида идёт ПЕРЕД активностью ВК.
        assert sec.index(self._title("Оценка лида")) < sec.index(self._title("Активность"))
        # «Тип компании» — про самого клиента, а не про качество данных:
        # стоит сразу после соцсетей и до оценки лида.
        assert sec.index(self._title("Тип компании")) < sec.index(self._title("Оценка лида"))

    def test_every_control_survived_the_regrouping(self):
        sec = self._section()
        for needle in ('id="parse-mode-hint"', 'id="social-mode-hint"',
                       'id="social-network-filter"', 'id="social-net-chk-grid"',
                       'id="social-net-hint"', 'id="f-vk-check"', 'id="vk-check-hint"',
                       'id="vk-filter-block"', 'id="f-vk-max-days"', 'id="f-vk-min-followers"',
                       'id="f-sort-score"', 'id="f-min-score"', 'id="score-presets"',
                       'id="score-hint"', 'id="f-collapse-chains"', 'id="f-chain-key"',
                       'id="f-raw-mode"', 'id="btn-refilter"'):
            assert needle in sec, f"{needle} потерялся при перегруппировке"
        for needle in ('name="parse_mode"', 'name="social_mode"', 'name="vk_mode"'):
            assert needle in sec, needle
        # Режимы свёрнутых блоков обрабатывает тот же appendLog/JS — id плиток
        # и грид соцсетей читает initSocialNetCheckboxes.
        assert 'class="parse-mode-opt active"' in sec
        assert 'class="score-preset active"' in sec

    def test_socials_are_one_block_with_nested_tiles(self):
        """«Соцсети в результате» + «Обязательные соцсети» — один блок."""
        sec = self._section()
        social = sec.index("Соцсети в результате")
        vk = sec.index("Проверять активность ВКонтакте")
        tiles = sec.index('id="social-network-filter"')
        next_group = sec.index(self._title("Оценка лида"))
        assert social < tiles < next_group < vk, "плитки обязательных соцсетей оторвались от режима"
        # Между режимом и плитками нет границы группы — это ОДИН блок.
        assert "flt-group-title" not in sec[social:tiles], "соцсети снова стали двумя пунктами"
        assert "Обязательные соцсети" in sec[tiles:next_group]
        # Плитки по-прежнему раскрываются классом .open из setSocialMode.
        assert 'class="tiles-reveal"' in sec[tiles:next_group]
        assert '<div class="tiles-grid" id="social-net-chk-grid"></div>' in sec[tiles:next_group]
        assert "netFilter.classList.toggle('open', mode === 'with_socials')" in APP_JS

    def test_company_type_group(self):
        """«🎯 Тип компании»: одиночки, новые с периодом и счётчик «подойдёт»."""
        sec = self._section()
        group = sec[sec.index(self._title("Тип компании")): sec.index(self._title("Оценка лида"))]
        for needle in ('id="f-only-single"', 'id="f-only-new"', 'id="f-new-months"',
                       'id="company-type-new-row"', 'id="company-type-count"'):
            assert needle in group, needle
        assert 'onchange="onCompanyTypeChange()"' in group
        # Чекбоксы стилизованы как везде в аккордеоне (класс .chk).
        assert group.count('<label class="chk">') == 2
        # Периоды — только из серверного реестра COMPANY_TYPE_MONTHS, дефолт 6.
        import re as _re
        values = _re.findall(r'<option value="(\d+)"', group)
        assert values == ["1", "3", "6", "12", "24"], values
        assert '<option value="6" selected>' in group
        assert 'role="status"' in group, "счётчик озвучивается скринридером"
        # Тексты объясняют, что именно фильтруется и что данные могут быть
        # неполными (даты добавления у Яндекса нет вовсе).
        assert "Компании с 1 филиалом" in group
        assert "Дата появления карточки в каталоге" in group and "даты нет" in group

    def test_company_type_group_styles(self):
        """Период гаснет без своего чекбокса, счётчик читается в обеих темах."""
        row = self._rule(".ct-new-row{")
        assert "opacity:.4" in row and "pointer-events:none" in row
        assert "opacity:1" in self._rule(".ct-new-row.on{")
        count = self._rule(".ct-count{")
        assert "var(--bdr)" in count and "var(--row-alt)" in count
        assert ".ct-count.on{" in STYLE
        # Мобильная версия ≤860px: строка периода не сдвигается вправо и
        # растягивается на всю ширину сайдбора.
        assert ".ct-new-row{margin-left:0}" in STYLE
        assert ".ct-new-row select{flex:1 1 100%}" in STYLE

    def test_company_type_counter_is_wired(self):
        """Счётчик ленивый, а оба фильтра уезжают и в запуск, и в рефильтр."""
        for fn in ("onlySingleChecked", "newMonthsValue", "newMonthsPeriod",
                   "companyTypeOn", "syncCompanyTypeUi", "onCompanyTypeChange",
                   "scheduleCompanyTypePreview", "previewCompanyType",
                   "companyTypeCountHTML"):
            assert f"function {fn}(" in APP_JS, fn
        assert "'/preview-company-type'" in APP_JS
        # Два пути: обычный запуск (getParams) и «Применить фильтры заново».
        assert APP_JS.count("only_single_branch: onlySingleChecked()") == 2
        assert APP_JS.count("only_new_months:    newMonthsValue()") == 2
        # Как и чёрный список — только при открытии раздела.
        assert "scheduleCompanyTypePreview();" in APP_JS
        # Реестр периодов в браузере совпадает с серверным COMPANY_TYPE_MONTHS.
        import re as _re
        decl = _re.search(r"const COMPANY_TYPE_PERIODS = \{(.*?)\};\n", APP_JS, _re.S)
        assert decl, "нет реестра периодов в app.js"
        assert [int(n) for n in _re.findall(r"(\d+):", decl.group(1))] == [1, 3, 6, 12, 24]

    def test_group_title_looks_like_the_sidebar_group_title(self):
        rule = self._rule(".flt-group-title{")
        assert "font-size:12px" in rule
        assert "text-transform:uppercase" in rule
        assert "color:var(--muted)" in rule
        assert "border-left:3px solid var(--c)" in rule
        assert "padding:0 0 8px 9px" in rule, "16/8 из макета: сверху группу отбивает .flt-group"
        body = self._rule(".flt-group-body{")
        assert "gap:12px" in body
        assert ".flt-group{padding-top:16px}" in STYLE
        assert ".flt-group+.flt-group{border-top:1px solid var(--bdr);margin-top:16px}" in STYLE

    def test_rare_settings_are_collapsed_by_default(self):
        sec = self._section()
        assert '<details class="flt-extra" id="filters-extra">' in sec
        # Подпись без эмодзи: значки в подписях и кнопках — инлайновый SVG
        # (.ico), эмодзи рисовались цветными на Windows и монохромно на macOS.
        assert "Дополнительно</summary>" in sec
        assert "<summary><svg class=\"ico\"" in sec
        # Свёрнуто: атрибута open у <details> нет (разметка, а не CSS).
        at = sec.index('id="filters-extra"')
        tag = sec[sec.rindex("<details", 0, at): sec.index(">", at) + 1]
        assert "open" not in tag, f"«Дополнительно» должно быть свёрнуто: {tag}"
        assert sec.count('id="filters-extra"') == 1
        box = sec[sec.index('id="filters-extra"'):]
        box = box[: box.index("</details>")]
        for needle in ('id="f-chain-key"', 'id="f-raw-mode"'):
            assert needle in box, f"{needle} должен жить в «⚙️ Дополнительно»"
        # Значения селектов — контракт для refilterNow/preset-ов.
        assert '<option value="name_city" selected>' in box
        assert '<option value="keep" selected>' in box
        rule = self._rule(".flt-extra-body{")
        assert "padding:11px" in rule

    def test_footer_is_the_last_block_and_carries_the_action(self):
        sec = self._section()
        footer = sec.index('class="flt-footer"')
        assert sec.index('</details>') < footer, "футер должен идти после «Дополнительно»"
        assert 'id="btn-refilter"' in sec[footer:]
        assert 'onclick="refilterNow()"' in sec[footer:]
        assert "Применить фильтры заново</button>" in sec[footer:]
        assert "refilterNow()" in sec[footer:]
        # Футер — последний блок аккордеона: после него ни групп, ни настроек.
        assert "flt-group-title" not in sec[footer:]
        assert sec.count('class="flt-footer"') == 1

    def test_sticky_footer_parks_above_the_dock(self):
        rule = self._rule(".flt-footer{")
        assert "position:sticky" in rule
        assert "bottom:calc(var(--dock-h" in rule
        assert "z-index:5" in rule
        assert "background:var(--card)" in rule
        assert "box-shadow:0 -4px 12px" in rule
        assert "margin:16px -13px 0" in rule, "футер должен быть во всю ширину аккордеона"
        assert "width:100%" in self._rule(".flt-footer #btn-refilter{")
        # Запасное значение токена + ноль на телефоне (там док статичный).
        assert ":root{--dock-h:62px}" in STYLE
        assert "@media(max-width:860px){:root{--dock-h:0px}}" in STYLE
        assert "@media(max-width:860px){#run-dock{position:static}}" in STYLE

    def test_sticky_needs_clip_where_hidden_would_kill_it(self):
        """overflow:hidden у предка делает его скролл-портом: футер «прилипал» бы
        к самому аккордеону и не сдвинулся бы ни на пиксель."""
        assert "#acc-filters{overflow:clip}" in STYLE
        assert "#acc-filters .acc-body>.acc-inner{overflow:clip}" in STYLE
        assert "#acc-filters{overflow:hidden}" not in STYLE
        assert "#acc-filters .acc-body>.acc-inner{overflow:hidden}" not in STYLE
        # Ритм групп задаёт сам аккордеон, а не flex-gap (иначе разделитель
        # получал бы 13px сверху и 13px снизу вместо 16/16).
        assert "#acc-filters .acc-inner{gap:0;padding-bottom:0}" in STYLE

    def test_js_measures_the_dock_instead_of_hard_coding_it(self):
        assert "function syncDockHeight()" in APP_JS
        assert "root.style.setProperty('--dock-h'" in APP_JS
        assert "dock.offsetHeight" in APP_JS
        assert "syncDockHeight();" in APP_JS
        assert "addEventListener('resize', syncDockHeight)" in APP_JS
        assert "new ResizeObserver(syncDockHeight).observe(_dockEl)" in APP_JS


class TestBlacklistChips:
    """«🚫 Исключить по словам»: чипы, шаблоны и счётчик в аккордеоне 03.

    Логику (валидация, storage, debounce, шаблоны) ловят node-тесты в
    tests/ui/blacklist.test.mjs, а здесь — то, что живёт только в разметке
    и стилях: id-контракты обработчиков, отсутствие обрезки на поле и
    токены темы.
    """

    def _section(self) -> str:
        body = TEMPLATE[TEMPLATE.index('id="acc-filters"'):]
        return body[: body.index("</section>")]

    def _rule(self, selector: str) -> str:
        assert selector in STYLE, f"нет правила {selector}"
        block = STYLE[STYLE.index(selector) + len(selector):]
        return block[: block.index("}")]

    def test_block_has_its_own_group_and_every_control(self):
        sec = self._section()
        assert '<div class="flt-group-title">Исключить по словам</div>' in sec
        for needle in ('id="blacklist-chips"', 'id="f-blacklist-input"',
                       'id="btn-blacklist-add"', 'id="btn-blacklist-save"',
                       'id="btn-blacklist-clear"', 'id="blacklist-template"',
                       'id="blacklist-count"', 'id="blacklist-err"'):
            assert needle in sec, needle
        for handler in ('onclick="addBlacklistFromField()"', 'onkeydown="onBlacklistKey(event)"',
                        'onclick="openBlacklistSaveModal()"', 'onclick="clearBlacklist()"',
                        'onclick="toggleBlacklistDropdown(event)"'):
            assert handler in sec, handler

    def test_block_sits_before_the_advanced_box_and_the_footer(self):
        """Список — обычная группа: редкое живёт в «Дополнительно», а действие — в
        футере, поэтому исключения не должны оказаться после них."""
        sec = self._section()
        block = sec.index('id="blacklist-chips"')
        assert block < sec.index('id="filters-extra"')
        assert block < sec.index('class="flt-footer"')
        # и после групп качества/оценки/активности/обработки
        assert block > sec.index('<div class="flt-group-title">Обработка</div>')

    def test_copy_and_limits_live_in_the_markup(self):
        sec = self._section()
        assert 'Добавьте слова, которые исключат компанию' in sec
        assert 'Добавьте слово и нажмите Enter или +' in sec
        assert 'Слова ищутся в названии и категории. Регистр не важен.' in sec
        # Кнопки списка — с SVG-значками вместо эмодзи.
        assert 'Сохранить список</button>' in sec and 'Очистить список</button>' in sec
        assert 'Загрузить шаблон</button>' in sec
        assert sec.count('<svg class="ico"') >= 3, "у кнопок списка должны быть значки"
        # Поле НЕ ограничивает длину: maxlength обрезал бы вставленный список
        # слов до 50 символов. Лимит на одно слово проверяет JS
        # (BLACKLIST_MAX_LEN), а не атрибут поля.
        assert 'maxlength=' not in sec
        assert 'Таблица и файлы обновятся после «Применить фильтры заново».' in sec

    def test_template_options_are_built_from_the_registry(self):
        """Дропдаун — кастомный (у select не бывает кнопок в опциях): в разметке
        только кнопка и пустая панель, содержимое строит JS из реестра."""
        sec = self._section()
        dd = sec[sec.index('id="blacklist-dd"'):]
        dd = dd[: dd.index('id="blacklist-tpl-hint"')]
        assert 'id="blacklist-dd-panel" hidden' in dd
        assert '<option' not in dd, "опции рисует JS — в разметке их нет"
        assert "const BLACKLIST_TEMPLATES = {" in APP_JS
        assert "function fillBlacklistTemplateSelect(" in APP_JS
        assert "function toggleBlacklistDropdown(" in APP_JS
        assert "function closeBlacklistDropdown(" in APP_JS
        assert "function renderBlacklistListManage(" in APP_JS
        assert 'data-act="edit"' in APP_JS and 'data-act="del"' in APP_JS

    def test_chips_follow_the_design_and_the_theme_tokens(self):
        chips = self._rule(".bl-chips{")
        assert "flex-wrap:wrap" in chips
        assert "max-height:150px" in chips
        assert "overflow-y:auto" in chips
        chip = self._rule(".bl-chip{")
        assert "border-radius:6px" in chip
        assert "background:var(--chip-bg)" in chip
        assert "color:var(--chip-txt)" in chip
        # Анимация — только у свежедобавленных чипов (.bl-new): базовый чип
        # сам не анимируется, иначе перерисовка списка прыгала бы целиком.
        assert "animation:" not in chip, "базовый .bl-chip не анимируется сам"
        assert "animation:bl-chip-in .15s" in self._rule(".bl-chip.bl-new{"), \
            "появление нового чипа — scale + fade (0.15s)"
        assert "@keyframes bl-chip-in{" in STYLE
        assert "scale(.9)" in STYLE
        assert ".bl-chip .bl-chip-x:hover{color:var(--err-strong)}" in STYLE
        assert ".bl-chip.bl-out{opacity:0;transform:translateX(-6px)}" in STYLE
        # Ни одного hex-литерала в правилах — цвет переключается токенами темы.
        for rule in (".bl-chips{", ".bl-chip{", ".bl-chip .bl-chip-x{"):
            assert not re.search(r"#[0-9a-fA-F]{3,8}\b", self._rule(rule)), rule

    def test_chip_tokens_are_declared_for_both_themes(self):
        light = STYLE[STYLE.index(":root{"):]
        light = light[: light.index("\n}")]
        dark = DARK_TOKEN_BLOCK[: DARK_TOKEN_BLOCK.index("\n}")]
        for token in ("--chip-bg:", "--chip-txt:"):
            assert token in light, f"{token} не объявлен в светлой теме"
            assert token in dark, f"{token} не объявлен в тёмной теме"
        # Плашка из макета (#F3F4F6 / #374151) — светлая тема; в тёмной
        # нейтральный Gray-700 выбивался бы из графитовой палитры.
        assert "--chip-bg:#F3F4F6" in light and "--chip-txt:#374151" in light

    def test_storage_key_and_handlers_are_wired(self):
        assert "const BLACKLIST_KEY = 'blacklist_words'" in APP_JS
        assert "version: BLACKLIST_VERSION" in APP_JS
        assert "updated_at: new Date().toISOString()" in APP_JS
        for fn in ("normalizeBlacklist", "parseBlacklistInput", "addBlacklistWords",
                   "removeBlacklistWord", "clearBlacklist", "applyBlacklistTemplate",
                   "loadBlacklistWords", "setBlacklistWords", "previewBlacklist",
                   "saveBlacklistNow"):
            assert f"function {fn}(" in APP_JS, fn
        assert "'/preview-blacklist'" in APP_JS
        assert "function onBlacklistChipKey(" in APP_JS, "крестик доступен с клавиатуры"
        assert 'onkeydown="onBlacklistChipKey(event,' in APP_JS
        # Живой счётчик исключений ленивый: на загрузке — только число слов,
        # запрос уходит при открытии раздела (acc-filters).
        assert "scheduleBlacklistPreview" in APP_JS
        assert "loadBlacklistWords();" in APP_JS
        assert "renderBlacklistChips({preview: false})" in APP_JS
        assert "sec.id === 'acc-filters'" in APP_JS
        assert "_blAnimateWords" in APP_JS


class TestMessageTemplates:
    """«📝 Шаблоны»: вкладка, панель, модалка и интеграции в разметке.

    Логику (подстановка, карточки, очередь, импорт) ловят node-тесты в
    tests/ui/templates.test.mjs, а здесь — id-контракты обработчиков,
    порядок вкладки и стили/тема.
    """

    def _panel(self) -> str:
        return TEMPLATE[TEMPLATE.index('id="p-templates"'):]

    def test_tab_sits_after_history(self):
        assert 'id="t-templates"' in TEMPLATE
        assert 'onclick="showTab(\'templates\')"' in TEMPLATE
        assert TEMPLATE.index('id="t-history"') < TEMPLATE.index('id="t-templates"')
        assert 'id="p-templates"' in TEMPLATE
        # Вкладка «Форматы вывода» удалена: выбор полей переехал в аккордеон
        # «02 · Что парсить», а экспорт/импорт данных — в «05 · Форматы результата».
        assert 'id="t-excel"' not in TEMPLATE
        assert 'id="p-excel"' not in TEMPLATE

    def test_panel_has_every_control(self):
        sec = self._panel()
        for needle in ('id="tpl-list"', 'id="tpl-var-list"', 'id="tpl-show-missing"',
                       'id="btn-tpl-import"', 'id="btn-tpl-export"', 'id="btn-tpl-reset"',
                       'id="btn-tpl-add"', 'id="tpl-import-file"'):
            assert needle in sec, needle
        for handler in ('filterTemplatesByCategory(', 'importTemplates(', 'exportTemplates()',
                        'resetTemplates()', 'openTemplateModal()', 'onShowMissingChange()'):
            assert handler in sec, handler

    def test_edit_modal_has_fields_and_variable_insert(self):
        for needle in ('id="tpl-modal"', 'id="tpl-name"', 'id="tpl-category"',
                       'id="tpl-text"', 'id="tpl-var-insert"', 'id="tpl-preview-body"',
                       'id="tpl-modal-err"'):
            assert needle in TEMPLATE, needle
        assert 'onclick="saveTemplateFromModal()"' in TEMPLATE
        assert 'onclick="closeTemplateModal()"' in TEMPLATE
        # Ввод живёт в onTemplateTextInput: он и превью обновляет,
        # и автодополнение открывает.
        assert 'oninput="onTemplateTextInput()"' in TEMPLATE

    def test_category_filter_covers_four_networks(self):
        sec = self._panel()
        for cat in ('all', 'vk', 'telegram', 'whatsapp', 'instagram'):
            assert 'data-cat="' + cat + '"' in sec, cat

    def test_table_bulk_pickers_exist(self):
        assert 'id="tbl-template"' in TEMPLATE
        assert 'id="bulk-template"' in TEMPLATE
        assert 'id="bulk-queue"' in TEMPLATE
        # Автоматическая рассылка удалена (ст. 18 ФЗ «О рекламе»):
        # ни панели, ни VK-токена для отправки в разметке быть не должно.
        assert 'id="s-template"' not in TEMPLATE
        assert 'p-sender' not in TEMPLATE

    def test_terms_gate_blocks_first_entry(self):
        """При входе показывается соглашение: модал скрыт по умолчанию,
        кнопка «Продолжить» неактивна до чекбокса, отказ даёт заглушку."""
        assert 'id="terms-overlay"' in TEMPLATE
        tag = TEMPLATE[TEMPLATE.rindex('<div', 0, TEMPLATE.index('id="terms-overlay"')):
                       TEMPLATE.index('>', TEMPLATE.index('id="terms-overlay"')) + 1]
        assert 'hidden' in tag, "оверлей должен быть скрыт до проверки /terms/status"
        assert 'id="terms-accept-chk"' in TEMPLATE
        assert 'onchange="onTermsCheckbox()"' in TEMPLATE
        assert 'id="terms-accept-btn"' in TEMPLATE
        assert 'disabled' in TEMPLATE[TEMPLATE.index('id="terms-accept-btn"'):
                                      TEMPLATE.index('</button>', TEMPLATE.index('id="terms-accept-btn"'))]
        assert 'onclick="declineTerms()"' in TEMPLATE
        assert 'id="terms-declined"' in TEMPLATE
        # Юридические ориентиры в тексте соглашения.
        assert '152-ФЗ' in TEMPLATE
        assert '«О рекламе»' in TEMPLATE

    def test_terms_spell_out_the_operator_duties(self):
        """Соглашение должно называть обязанности, а не только законы."""
        body = TEMPLATE[TEMPLATE.index('id="terms-title"'):TEMPLATE.index('id="terms-declined"')]
        # Обязанности оператора персональных данных и запрет рассылок.
        for needle in ('оператором персональных данных', 'согласие субъекта',
                       'уведомление Роскомнадзора', 'ст. 272.1 УК РФ',
                       'ч. 4.1 ст. 14.3 КоАП РФ', 'массовых рассылок',
                       'третьим лицам', 'защит намеренно не обходит'):
            assert needle in body, needle
        # Данные остаются у пользователя, автору не уходят.
        assert 'Автору эти данные не передаются' in body

    def test_terms_version_bumped_for_the_new_edition(self):
        """Новая редакция должна переспрашиваться у пользователей."""
        assert 'TERMS_VERSION = "2.0"' in API_PY

    def test_sender_removed_entirely(self):
        """Массовая рассылка не должна остаться нигде в разметке."""
        for needle in ('s-token', 's-message', 's-excel-file',
                       'startSend', 'btn-send-run', 'sender-stats-bar'):
            assert needle not in TEMPLATE, needle

    def test_client_wires_handlers_and_endpoints(self):
        for fn in ('loadTemplates', 'renderTemplates', 'openTemplateModal', 'saveTemplateFromModal',
                   'substituteTemplate', 'usedVariables', 'importTemplates', 'exportTemplates',
                   'resetTemplates', 'uiChoose', 'onSocialBadgeClick', 'renderBulkQueue',
                   'bulkCopyNext', 'getActiveTemplateFor', 'setActiveTemplate', 'onShowMissingChange'):
            assert f'function {fn}(' in APP_JS, fn
        assert "'/templates'" in APP_JS
        assert "'/templates/reset'" in APP_JS
        assert 'data-act="edit"' in APP_JS

    def test_substitution_supports_cyrillic_alias(self):
        # \w в JS не покрывает кириллицу — {название_бизнеса} иначе не заменится.
        assert 'А-Яа-я' in APP_JS
        assert "'название_бизнеса': 'name'" in APP_JS

    def test_cards_and_queue_are_styled(self):
        for rule in ('.template-card{', '.template-actions{', '.bulk-queue{', '.tpl-modal{'):
            assert rule in STYLE, rule
        assert '.template-card:hover .template-actions' in STYLE
        assert 'white-space:pre-wrap' in STYLE
        assert '[data-theme="dark"] .template-card' in STYLE
        assert '[data-theme="dark"] .bulk-queue' in STYLE

    def test_server_endpoints_and_module_exist(self):
        api = (ROOT / "routes" / "api.py").read_text(encoding="utf-8")
        assert '@bp.route("/templates", methods=["GET"])' in api
        assert '@bp.route("/templates", methods=["POST"])' in api
        assert '@bp.route("/templates/reset", methods=["POST"])' in api
        mod = (ROOT / "yandex_maps_parser" / "message_templates.py").read_text(encoding="utf-8")
        for fn in ('def substitute(', 'def normalize_templates(', 'def normalize_active_ids(',
                   'def migrate_templates(', 'def load_templates(', 'def save_templates('):
            assert fn in mod, fn
        assert 'active_template_ids' in mod

    def test_bulk_delete_controls_in_markup_and_js(self):
        sec = self._panel()
        assert 'id="btn-tpl-del-selected"' in sec
        assert 'deleteSelectedTemplates()' in sec
        assert 'toggleSelectAllTemplates()' in sec
        for fn in ('deleteSelectedTemplates', 'toggleTemplateSelected',
                   'toggleSelectAllTemplates', 'pruneTemplateSelection'):
            assert f'function {fn}(' in APP_JS, fn
        assert "data-tpl-check" in APP_JS

    def test_autocomplete_in_markup_and_js(self):
        sec = self._panel()
        assert 'id="tpl-autocomplete"' in sec
        assert 'oninput="onTemplateTextInput()"' in TEMPLATE
        assert 'onkeydown="onTemplateTextKeydown(event)"' in TEMPLATE
        for fn in ('onTemplateTextInput', 'onTemplateTextKeydown',
                   'renderTemplateAutocomplete', 'applyTemplateAutocomplete',
                   'closeTemplateAutocomplete', 'allTemplateVars'):
            assert f'function {fn}(' in APP_JS, fn

    def test_custom_vars_subtab_and_modal(self):
        sec = self._panel()
        # Переключатель подвкладок и панель переменных.
        assert "showTplSubtab('vars')" in sec
        assert 'id="tpl-pane-vars"' in sec
        assert 'id="tpl-var-cards"' in sec
        assert 'openVarModal()' in sec
        # Модалка переменной: имя, источник (текст/столбец), описание.
        for needle in ('id="tpl-var-modal"', 'id="tpl-var-name"', 'id="tpl-var-source"',
                       'id="tpl-var-value"', 'id="tpl-var-column"', 'id="tpl-var-desc"'):
            assert needle in TEMPLATE, needle
        for fn in ('openVarModal', 'saveVarFromModal', 'closeVarModal',
                   'deleteCustomVar', 'onVarSourceChange'):
            assert f'function {fn}(' in APP_JS, fn

    def test_custom_vars_styled(self):
        for rule in ('.tpl-subtab{', '.tpl-var-card{', '.tpl-ac-box{',
                     '.tpl-card-chk{', '.tpl-var-name-row{'):
            assert rule in STYLE, rule
        assert '.tpl-ac-box[hidden]' in STYLE
        assert '[data-theme="dark"] .tpl-var-card' in STYLE

    def test_server_round_trips_custom_variables(self):
        api = (ROOT / "routes" / "api.py").read_text(encoding="utf-8")
        assert 'custom_variables' in api
        mod = (ROOT / "yandex_maps_parser" / "message_templates.py").read_text(encoding="utf-8")
        assert 'def normalize_custom_variables(' in mod
        assert 'custom_variables' in mod

    def test_special_variables_in_both_mirrors(self):
        # Служебные переменные живут в Python и JS-зеркале синхронно.
        mod = (ROOT / "yandex_maps_parser" / "message_templates.py").read_text(encoding="utf-8")
        for needle in ('SPECIAL_VARIABLES = ("дата", "время", "приветствие")',
                       'def _special_value(', '_GREETING_PARTS'):
            assert needle in mod, needle
        for needle in ('const TEMPLATE_SPECIAL_VARS',
                       'function specialTemplateValue(',
                       'const TEMPLATE_GREETING_PARTS'):
            assert needle in APP_JS, needle

    def test_export_import_carry_custom_variables(self):
        assert 'custom_variables: customVariables' in APP_JS, "экспорт без переменных"
        assert 'function importCustomVariables(' in APP_JS
        assert 'function normalizeCustomVariablesClient(' in APP_JS
        assert 'parsed.custom_variables' in APP_JS

    def test_save_warns_about_unknown_variables(self):
        assert 'Неизвестные переменные' in APP_JS
        assert 'saveVarFromModal._varsWarned' in APP_JS


class TestBulkCrawlOrder:
    """«Массовый обход» открывает профили в том же порядке, что и таблица.

    Регрессия: сервер отдавал записи в порядке файла, поэтому очередь
    начиналась не с самых горячих, хотя таблица отсортирована по оценке.
    """

    def test_panel_tells_the_user_the_order(self):
        assert 'id="bulk-order-note"' in TEMPLATE
        assert 'function bulkOrderLabel(' in APP_JS
        assert 'function bulkSortSpec(' in APP_JS
        assert '.bulk-order{' in STYLE

    def test_client_sends_the_table_sort_to_the_server(self):
        assert 'sort_col: sort.col,' in APP_JS
        assert 'sort_asc: sort.asc,' in APP_JS
        assert 'sort_col: p.sort_col, sort_asc: p.sort_asc' in APP_JS

    def test_server_sorts_records_the_way_the_table_shows_them(self):
        api = (ROOT / "routes" / "api.py").read_text(encoding="utf-8")
        for fn in ('def _sort_like_table(', 'def _lead_score_num('):
            assert fn in api, fn
        assert '_sort_like_table(_collect_records(' in api
        assert 'sort_col' in api and 'sort_asc' in api
        # 6 — оценка лида, 2..5 — название/категория/адрес/телефон (sortTable).
        assert '_VIEW_SORT_KEYS = {2: "name", 3: "category", 4: "address", 5: "phone"}' in api

    def test_refiltering_drops_a_stale_column_sort(self):
        body = APP_JS[APP_JS.index('function filterTable('):]
        body = body[: body.index('function minScoreThreshold(')]
        assert 'sortCol = -1;' in body, 'стрелка в шапке разошлась бы с порядком строк'
        assert 'sortAsc = true;' in body


class TestDiagnosticsPanel:
    """«🩺 Диагностика»: кнопка в шапке, панель и защита от чужого сайта.

    Панель — ответ на «ничего не работает» для десктопной сборки, где нет
    консоли. Разметка тут проверяется целиком: кнопка, три вида проверок,
    предупреждение про квоту и то, что эндпоинт в JS совпадает с flask-роутом.
    """

    ROUTES = (ROOT / "routes" / "diagnostics.py").read_text(encoding="utf-8")

    def test_button_lives_between_logs_and_updates(self):
        logs = TEMPLATE.index('id="btn-logs"')
        diag = TEMPLATE.index('id="btn-diag"')
        updates = TEMPLATE.index('id="btn-updates"')
        assert logs < diag < updates
        assert 'onclick="showDiagnostics()"' in TEMPLATE

    def test_panel_offers_four_scopes(self):
        """Четыре кнопки: всё, только ключи, без запросов к API, живая проба.

        История прогонов («runs») входит в «всё» и в «без запросов к API»:
        именно она отвечает на «а вчера сбор шёл?» без чтения логов.
        """
        for needle in ("runDiagnostics(['keys','files','data','runs','env'], this)",
                       "runDiagnostics(['keys'], this)",
                       "runDiagnostics(['files','data','runs','env'], this)",
                       "runDiagnostics(['engines'], this, true)"):
            assert needle in APP_JS, needle

    def test_live_check_warning_is_shown_before_the_click(self):
        # Живая проверка ровно одна (токен ВК) — предупреждение об этом стоит
        # в панели до нажатия, а не после.
        assert "один живой запрос к ВКонтакте" in APP_JS
        assert "onclick=\"closeDiagnostics()\"" in APP_JS

    def test_js_endpoint_matches_the_flask_route(self):
        assert "fetch('/diagnostics/run'" in APP_JS
        assert '@bp.route("/diagnostics/run", methods=["POST"])' in self.ROUTES

    def test_only_the_app_itself_can_run_it(self):
        """Живая проверка обращается к внешнему сервису от имени пользователя:
        чужая страница нажать эту кнопку за него не может."""
        assert "def _only_from_our_ui(" in self.ROUTES
        assert '@bp.before_request' in self.ROUTES
        assert "request.is_json" in self.ROUTES

    def diagnostics_css(self) -> str:
        """Только блок правил панели — от первого .diag- до общей модалки."""
        block = STYLE[STYLE.index(".diag-modal{"):]
        return block[: block.index(".ui-modal p{")]

    def test_styles_cover_statuses_and_the_phone(self):
        css = self.diagnostics_css()
        for needle in (".diag-modal{", ".diag-summary-error{", ".diag-group-title{",
                       '.diag-row[data-status="error"]{'):
            assert needle in css, needle
        assert "@media(max-width:860px){" in css
        assert ".diag-actions .diag-run{flex:1 1 100%}" in css, "на телефоне кнопки в столбик"

    def test_no_hardcoded_colours_in_the_panel(self):
        css = self.diagnostics_css()
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", css), "тёмная тема сломается"
        assert "rgba(" not in css, "тёмная тема сломается"


class TestDesignSystem:
    """Визуальная система: шрифт рядом с приложением, значки вместо эмодзи.

    Это не вкусовщина, а два измеримых свойства: (1) интерфейс обязан
    выглядеть одинаково на машине без доступа к Google Fonts, (2) в элементах
    управления не должно остаться эмодзи — на Windows они цветные и разной
    ширины, на macOS монохромные, из-за чего ряд кнопок разъезжался.
    """

    # Комментарии из разметки убираем: в них значки упоминаются словами.
    RENDERED = re.sub(r"<!--.*?-->", "", TEMPLATE, flags=re.S)
    HEADER = RENDERED[RENDERED.index("<header"):RENDERED.index("</header>")]
    # Верхняя панель лога — все кнопки журнала в одном месте.
    LOGBAR = RENDERED[RENDERED.index('class="term-top"'):RENDERED.index('class="log-empty"')]
    EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")
    # Значок = ссылка на символ спрайта: одна форма на всю страницу.
    ICON = '<svg class="ico" aria-hidden="true"><use href="#i-'

    def test_font_ships_with_the_app(self):
        """Шрифт лежит рядом: без сети интерфейс не должен «уезжать»."""
        assert "fonts.googleapis" not in TEMPLATE
        assert "fonts.gstatic" not in TEMPLATE
        fonts = ROOT / "static" / "fonts"
        for name in ("manrope-cyrillic.woff2", "manrope-latin.woff2", "OFL.txt"):
            assert (fonts / name).is_file(), f"нет {name}"
        assert (fonts / "manrope-cyrillic.woff2").stat().st_size > 5000

    def test_font_faces_point_at_the_local_files(self):
        assert '@font-face{' in STYLE
        assert 'url("../fonts/manrope-cyrillic.woff2")' in STYLE
        assert 'url("../fonts/manrope-latin.woff2")' in STYLE
        assert STYLE.count('font-display:swap') >= 2, "текст не должен ждать шрифт"
        assert "font-family:var(--font-ui);" in STYLE

    def test_welcome_screen_does_not_inherit_the_monospace_log(self):
        """Первый экран живёт внутри #log-output, а тот моноширинный."""
        rule = STYLE[STYLE.index("#onboarding-screen,.onboarding,.flow-step{"):]
        assert "font-family:var(--font-ui)" in rule[:80]

    def test_icon_class_is_one_place(self):
        assert ".ico{" in STYLE
        rule = STYLE[STYLE.index(".ico{"):]
        rule = rule[: rule.index("}")]
        assert "stroke:currentColor" in rule, "значки должны наследовать цвет темы"
        assert "fill:none" in rule
        assert ".hdr-right .ico{" in STYLE

    def test_header_buttons_carry_svg_not_emoji(self):
        for bid in ("btn-logs", "btn-diag", "btn-updates"):
            start = self.HEADER.index(f'id="{bid}"')
            button = self.HEADER[start: self.HEADER.index("</button>", start)]
            assert self.ICON in button, f"{bid}: значок должен быть инлайновым SVG"
            assert not self.EMOJI.search(button), f"{bid}: вернулся эмодзи"

    def test_log_toolbar_carries_svg_not_emoji(self):
        for bid in ("btn-log-save", "btn-log-copy", "btn-clear-log"):
            assert self.ICON in self.LOGBAR, f"{bid}: нет значка"
        assert not self.EMOJI.search(self.LOGBAR), "в панели лога остались эмодзи"

    def test_eyebrow_labels_lost_their_emoji(self):
        for title in ("Сбор данных", "Вывод и фильтрация"):
            assert f'<div class="group-title">{title}</div>' in TEMPLATE
        # Ни один подзаголовок фильтров не начинается со значка.
        blocks = re.findall(r'<div class="(?:group-title|flt-group-title)">([^<]*)</div>',
                            self.RENDERED)
        assert blocks, "подзаголовки не найдены"
        for text in blocks:
            assert not self.EMOJI.search(text), f"эмодзи вернулся в подзаголовок: {text}"

    def test_js_built_chrome_uses_the_same_icon_map(self):
        assert "const UI_ICONS = {" in APP_JS
        for key in ("search", "pause", "bell", "sun", "moon"):
            assert f"{key}:" in APP_JS, key
        # Подписи, которые JS восстанавливает сам, тоже с иконкой.
        assert "const REFILTER_LABEL = UI_ICONS.refresh" in APP_JS
        assert "const UPDATE_BTN_IDLE = UI_ICONS.refresh" in APP_JS

    def test_narrow_phone_keeps_only_icons_in_the_header(self):
        """Шапка растягивала страницу вбок на телефоне (242px прокрутки).

        До 620px подписи второстепенных кнопок скрыты, но у каждой кнопки есть
        aria-label — иначе от кнопки остался бы безымянный значок.
        """
        for bid, label in (("btn-logs", "Логи"), ("btn-diag", "Диагностика"),
                           ("btn-updates", "Обновления")):
            start = self.HEADER.index(f'id="{bid}"')
            button = self.HEADER[start: self.HEADER.index("</button>", start)]
            assert f'<span class="hdr-lbl">{label}</span>' in button, bid
            assert f'aria-label="{label}"' in button, f"{bid}: подпись скрыта — нужен aria-label"
        assert "@media(max-width:620px){" in STYLE
        assert ".hdr-right > button .hdr-lbl{display:none}" in STYLE
        assert ".hdr-right > button .hdr-lbl{display:inline}" not in STYLE

    def test_js_labels_use_the_same_hidden_wrapper(self):
        """Кнопку «Обновления» рисует JS — обёртку .hdr-lbl он тоже обязан ставить."""
        assert '\'<span class="hdr-lbl">Обновления</span>\'' in APP_JS
        assert "'<span class=\"hdr-lbl\">Проверяю…</span>'" in APP_JS


class TestResultsTableDesign:
    """Таблица результатов держится на ролих палитры, а не на своих цветах.

    Здесь ловится регресс, который уже случался: липкая шапка была отдельной
    чёрной плитой со своими правилами для тёмной темы, зебра была почти
    неотличима от белого, а просмотренная строка гасла через opacity —
    и вместе с текстом гасла зебра под ней.
    """

    def _rule(self, selector: str) -> str:
        assert selector in STYLE, f"нет правила {selector}"
        block = STYLE[STYLE.index(selector) + len(selector):]
        return block[: block.index("}")]

    def test_header_is_sticky_and_painted_with_roles(self):
        head = self._rule("#results-table th{")
        assert "position:sticky" in head and "top:0" in head
        assert "z-index:2" in head, "шапку перекрывают бейджи строк"
        # Непрозрачный --card, а не --panel/--row-alt: под шапку уезжают
        # строки, и полупрозрачный или совпадающий с зеброй тон её терял.
        assert "background:var(--card)" in head and "color:var(--muted)" in head
        # Чёрная плита со белым текстом: была отдельная тема для тёмной.
        assert "--hdr" not in head and "--on-accent" not in head

    def test_header_tone_differs_from_the_zebra(self):
        """Регресс, который уже случался: --panel и --row-alt были одним тоном
        (#f7f8fa), и липкая шапка сливалась с чётными строками."""
        for start in (":root{", DARK_MARKER + "{"):
            block = STYLE[STYLE.index(start):]
            block = block[: block.index("\n}")]
            vals = dict(re.findall(r"(--card|--row-alt|--panel)\s*:\s*([^;]+);", block))
            assert vals["--card"] != vals["--row-alt"], vals
            assert vals["--panel"] != vals["--row-alt"], vals

    def test_header_needs_no_dark_override(self):
        assert '#results-table th{' not in dark_rule_lines()

    def test_zebra_and_hover_live_on_their_own_tokens(self):
        assert "#results-table tr:nth-child(even) td{background:var(--row-alt)}" in STYLE
        assert "#results-table tr:nth-child(even):hover td{background:var(--row-hover)}" in STYLE
        # Полоса, подсветка и сама карточка — три разных тона в каждой теме:
        # иначе зебра и курсор сливаются с фоном (так уже было: #fafbfc на #fff).
        for start in (":root{", DARK_MARKER + "{"):
            block = STYLE[STYLE.index(start):]
            block = block[: block.index("\n}")]
            vals = dict(re.findall(r"(--row-alt|--row-hover|--card)\s*:\s*([^;]+);", block))
            assert len(vals) == 3, vals
            assert len(set(vals.values())) == 3, f"тона совпали: {vals}"

    def test_reviewed_row_dims_by_colour_not_opacity(self):
        # --sub, а не --muted: на зебре и под курсором тихий --muted уходит
        # ниже 4.5:1 (см. PAIRS в tests/test_theme_contrast.py).
        assert "#results-table tr.is-reviewed td{color:var(--sub)}" in STYLE
        assert "opacity" not in self._rule("#results-table tr.is-reviewed td{")

    def test_table_needs_no_dark_theme_rules_at_all(self):
        """Таблица читает роли — значит, в тёмной теме у неё нет своих правил."""
        assert "#results-table" not in dark_rule_lines()

    def test_row_text_uses_classes_not_inline_colours(self):
        assert 'class="tbl-link"' in APP_JS and 'class="tbl-cat"' in APP_JS
        assert "style=\"color:var(--g)" not in APP_JS
        assert ".tbl-link{color:var(--c);font-weight:600" in STYLE
        # Служебный текст строки — --sub: на тонированной поверхности зебры
        # и наведения --muted не добирает контраста.
        assert ".tbl-cat{color:var(--sub)}" in STYLE
        assert ".score-na{color:var(--sub)}" in STYLE

    def test_density_keeps_service_columns_readable(self):
        cell = self._rule("\n#results-table td{")
        assert "vertical-align:top" in cell and "border-bottom:1px solid var(--bdr-soft)" in cell
        # Бейджи строки выровнены по центру, а не по верхней кромке.
        # Колонки адресуются по data-col, а не по номеру: их можно
        # переставлять («Столбцы» → перетаскивание).
        assert '#results-table td[data-col="score"],#results-table td[data-col="socials"]' in STYLE
        assert '#results-table td[data-col="phone"]{white-space:nowrap}' in STYLE

    def test_site_column_is_a_link_without_stretching_the_row(self):
        """«Сайт» — витрина ссылки: домен в ячейке, полный адрес — в подсказке.

        Без ограничения ширины длинный taplink-адрес тянул колонку вширь и
        уводил остальные за край экрана (так уже было с телефонами).
        """
        assert 'data-col="website"' in TEMPLATE
        assert "Сайт" in TEMPLATE
        rule = self._rule('#results-table th[data-col="website"],#results-table td[data-col="website"]')
        assert "max-width:170px" in rule
        assert ".site-link{display:block;max-width:170px" in STYLE
        assert ".site-na{color:var(--muted)}" in STYLE

    def test_one_scrim_for_every_modal(self):
        """Четыре модалки — одно затемнение: раньше у каждой был свой rgba."""
        for overlay in (".skip-modal-overlay{", ".logs-modal-overlay{",
                        ".ui-modal-overlay{", ".tpl-modal-overlay{"):
            assert "background:var(--scrim)" in self._rule(overlay), overlay

    def test_popups_share_the_radius_and_shadow_ladder(self):
        for sel in (".tpl-modal{", ".city-dropdown{", "#col-dropdown{", ".tpl-ac-box{"):
            rule = self._rule(sel)
            assert "var(--r-" in rule, f"{sel}: радиус вне лестницы токенов"
        assert "box-shadow:var(--sh-lg)" in self._rule(".tpl-ac-box{")

    def test_dropdown_items_hover_on_the_same_surface(self):
        """Одна подсветка курсора на все меню, а не «где --cl, где --c-soft»."""
        assert ".city-option:hover{background:var(--row-hover)}" in STYLE
        assert ".col-item:hover{background:var(--row-hover)}" in STYLE
        assert ".tpl-ac-item:hover,.tpl-ac-item.active{background:var(--row-hover)}" in STYLE

    def test_cards_keep_the_same_radius_ladder(self):
        for sel in (".hist-card{", ".stat-city-card{", ".template-card{", ".file-card{"):
            assert "var(--r-" in self._rule(sel), f"{sel}: радиус вне лестницы токенов"


class TestIconSprite:
    """Один спрайт на все значки: разметка и app.js ссылаются на <symbol>.

    Эмодзи в кнопках убраны не из эстетики: на Windows они рисовались цветными
    и разной ширины, на macOS — монохромными, а часть (⏸ ⏹ 🔤) подменялась
    чужим глифом или пропадала совсем, и ряд кнопок разъезжался. Спрайт —
    один набор форм на страницу, поэтому кнопка из шаблона и кнопка, которую
    собирает JS, выглядят одинаково.
    """

    # Пиктограммы (эмодзи и символьные значки). Стрелки и дефисы в прозе
    # (→ ← ·) намеренно не входят: это типографика, а не иконки — они
    # наследуют цвет текста и есть в любом шрифте.
    EMOJI = re.compile(
        "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u23F0-\u23FF"
        "\u21BA]"
    )

    def _slug(self, name: str) -> str:
        assert name in APP_JS, f"нет UI_ICONS.{name}"
        return name

    def test_every_referenced_symbol_is_defined(self):
        defined = set(re.findall(r'<symbol id="(i-[a-z0-9-]+)"', TEMPLATE))
        used = set(re.findall(r'href="#(i-[a-z0-9-]+)"', TEMPLATE + APP_JS))
        assert defined, "спрайт #icon-sprite пуст"
        assert not (used - defined), f"ссылки на несуществующие значки: {sorted(used - defined)}"
        assert not (defined - used), f"значки без ссылок (мёртвые): {sorted(defined - used)}"

    def test_ui_icons_point_at_the_sprite(self):
        block = APP_JS[APP_JS.index("const UI_ICONS = {"):]
        block = block[: block.index("\n};")]
        keys = re.findall(
            r"^  ([A-Za-z]+): +'<svg class=\"ico\" aria-hidden=\"true\">"
            r"<use href=\"#(i-[a-z0-9-]+)\"/></svg>',$",
            block, re.M,
        )
        assert len(keys) >= 30, f"UI_ICONS читается не полностью: {len(keys)}"
        assert "UI_ICONS.busy" in APP_JS and "UI_ICONS.gear" in APP_JS

    def test_no_emoji_in_rendered_markup(self):
        rendered = re.sub(r"<!--.*?-->", "", TEMPLATE, flags=re.S)
        left = sorted(set(self.EMOJI.findall(rendered)))
        assert not left, f"в разметке остались эмодзи: {left}"

    def test_controls_carry_icons_not_emoji(self):
        """В текстах журнала и тостах эмодзи — содержание (их пишет и Python),
        а подписи кнопок и заголовки модалок обязаны быть значками."""
        for bad in ("'🗑 Удалить", "'💾 Сохранить", "'🔄 Сбросить", "'📁 Обзор…'",
                    "'⏳ Открываем…'", "'✅ Все просмотрены'", "'🚀 Открыть",
                    "'✏️ Редактировать", "'➕ Новая переменная'", "'📊 Выбрано: ",
                    "'📂 Импорт'", "'⚙️ Настроить выбор'", "'👁 Превью",
                    "'📋 Скопировать все'", "'📖 Доступные переменные", "'🔤 Переменные",
                    "'🎲 Случайный выбор", "(on ? '☑' : '☐')",
                    "'⚠ ' + msg", "'⚠ ' + escape", "'✓ ' : '✕ ", "'💾 Сохранить как есть'",
                    "'🏪 Франшизы", "'🛵 Доставка", "'🛵 Доставка и тёмные",
                    "txt = `✅ Готово", "txt = `⚠️", "txt = `❌ 0/", '">✎<', '">✕<'):
            assert bad not in APP_JS, f"эмодзи в подписи управления: {bad}"
        # И то, чем они заменены — тоже часть контракта.
        for good in ("UI_ICONS.trash + 'Удалить выбранные",
                     "const REFILTER_LABEL = UI_ICONS.refresh + 'Применить фильтры заново'",
                     "UI_ICONS.checkSquare : UI_ICONS.square",
                     "UI_ICONS.check + 'Все просмотрены'",
                     "UI_ICONS.gear + 'Столбцы'",
                     "+ UI_ICONS.pencil + '</button>'",
                     "badge.innerHTML = txt"):
            assert good in APP_JS, good

    def test_icon_gap_lives_in_the_rule_not_in_markup(self):
        """Пробел в разметке терялся у кнопок, которые собирает JS: значок
        слипался с подписью. Зазор — в правиле .ico, поэтому он есть везде."""
        rule = STYLE[STYLE.index("\n.ico{"):]
        rule = rule[: rule.index("}")]
        assert "margin-right" in rule
        # Кнопки-иконки без подписи: зазор сдвинул бы значок от центра.
        assert ".file-btn .ico,.ub-close .ico,.bulk-reset .ico" in STYLE
        assert "</svg> " not in TEMPLATE, "пробел в разметке ломает единый зазор"

    def test_status_badge_uses_an_icon_not_a_glyph_in_the_text(self):
        """Пилюля состояния рисует значок по классу состояния, а подпись
        приходит без эмодзи — иначе один и тот же смысл оформлялся тремя
        разными наборами глифов (⏳ эмодзи, ⏹ и ✔ — символы)."""
        assert 'id="status-badge" role="status"' in TEMPLATE
        assert '<use href="#i-check"/>' in TEMPLATE.split('id="status-badge"')[1][:160]
        assert "const STATUS_ICONS = {" in APP_JS
        for state in ("running", "queued", "paused", "stopped", "error", "done"):
            assert re.search(rf"^  {state}: +UI_ICONS\.", APP_JS, re.M), state
        for bad in ("'⏸ Пауза'", "'⏳ Выполняется'", "'⏳ В очереди'", "'⏹ Остановлено'",
                    "'✔ Готово'", "'✖ Ошибка'", "'✖ Соединение прервано'"):
            assert bad not in APP_JS, f"эмодзи в подписи состояния: {bad}"
        assert "STATUS_ICONS[cls]" in APP_JS


class TestDailyDynamics:
    """«Динамика по дням» — дашборд вкладки «Статистика».

    Блок считается по файлам на диске (а не по записям текущей сессии),
    поэтому он живёт в своём контейнере и рисуется до KPI-карточек.
    """

    def test_container_is_the_first_block_of_the_stats_panel(self):
        stats = TEMPLATE.index('id="p-stats"')
        body = TEMPLATE.index('id="stats-body"', stats)
        daily = TEMPLATE.index('id="stats-daily"', stats)
        assert stats < daily < body, "динамика должна стоять перед KPI-карточками"
        assert 'id="stats-daily"' not in TEMPLATE[body:], "контейнер только один"

    def test_panel_scrolls_as_a_whole(self):
        """Прокручивался только #stats-body — блок над ним висел бы полосой.
        display меняется ТОЛЬКО у .active: иначе перебился бы
        `.tab-panel{display:none}` и скрытая вкладка была бы видна."""
        assert "#p-stats.active{display:block;overflow-y:auto;padding:20px}" in STYLE
        assert "#p-stats .stats-body{flex:none;overflow:visible;padding:0}" in STYLE
        assert "#p-stats{display:block}" not in STYLE

    def test_data_comes_from_the_server_by_day(self):
        assert "fetch('/stats/daily?' + _dailyQuery())" in APP_JS
        assert "function _dailyQuery()" in APP_JS
        assert "@bp.route(\"/stats/daily\")" in (
            ROOT / "routes" / "api.py").read_text(encoding="utf-8")

    def test_period_is_not_limited_to_the_quick_segments(self):
        """7/14/30 дней мало: период задаётся ещё календарным месяцем и
        диапазоном «с … по …», и каждый режим уходит своим параметром."""
        assert "DAILY_SEGMENTS" in APP_JS
        assert "{days: 1, label: 'Сегодня'}" in APP_JS, "статистика за сутки — окно в один день"
        assert "month=" in APP_JS and "'from=' +" in APP_JS and "&to=" in APP_JS
        assert 'type="month"' in APP_JS, "месяц — нативный пикер, а не список из 12 пунктов"
        assert 'type="date"' in APP_JS
        assert "setDailyMonth" in APP_JS and "applyDailyCustom" in APP_JS
        # Даты полей приходят из ответа сервера: клиент и сервер не могут
        # разойтись в том, какой период показан.
        assert "_dailyPayload = payload" in APP_JS

    def test_native_period_fields_follow_the_theme(self):
        """Пикер даты рисует браузер, поэтому тему ему сообщает color-scheme,
        а не токены цвета."""
        assert ".dyn-month,.dyn-date{" in STYLE
        assert "color-scheme:light" in STYLE
        assert '[data-theme="dark"] .dyn-month,[data-theme="dark"] .dyn-date{color-scheme:dark}' in STYLE

    def test_unanswered_marks_are_explained_on_the_chart(self):
        """Отметки старого формата — просто `true`, без даты. В график они не
        попадают, но «просмотрено 0» при сотне отмеченных строк выглядит как
        поломка счётчика, поэтому о них пишут прямо под графиком."""
        assert '"undated": undated' in (ROOT / "routes" / "api.py").read_text(encoding="utf-8")
        assert "_dailyNoteHTML" in APP_JS
        assert "в динамике по дням они не участвуют" in APP_JS
        assert ".dyn-note{" in STYLE

    def test_heading_uses_a_sprite_icon_not_an_emoji(self):
        assert "${UI_ICONS.chart}Динамика по дням" in APP_JS
        assert "'📊 Динамика" not in APP_JS
        assert '<symbol id="i-chart"' in TEMPLATE

    def test_chart_styles_read_theme_tokens(self):
        """Столбцы, шкала и легенда — на токенах: хекс в правиле не
        переключился бы вместе с темой (см. test_theme_contrast)."""
        block = STYLE[STYLE.index(".dyn-head{"):STYLE.index("@media(max-width:620px){", STYLE.index(".dyn-head{"))]
        assert "var(--c)" in block and "var(--grn)" in block
        assert "--brand" in block, "активный период — плотная плашка под белый текст"
        assert re.search(r"\.dyn-bar\.is-zero\{[^}]*height:2px", block), "ноль — насечка, не пропуск"

    def test_chart_has_entrance_animation(self):
        """Столбики вырастают волной (задержка --d по колонкам), цифры
        проявляются следом; reduced-motion всё отключает."""
        assert "@keyframes bar-in{from{height:0}}" in STYLE
        assert "@keyframes vlab-in{from{opacity:0}}" in STYLE
        assert "animation-delay:var(--d,0ms)" in STYLE
        assert "--d:" in APP_JS, "задержка волны ставится инлайном на колонку"
        reduced = STYLE[STYLE.index("@media (prefers-reduced-motion:reduce)"):]
        reduced = reduced[:reduced.index("animation:none}") + len("animation:none}")]
        assert ".dyn-bar,.dyn-vlab{animation:none}" in reduced

    def test_plot_geometry_leaves_room_for_the_numbers(self):
        """Три полосы по вертикали: запас под цифру над столбцом (16),
        шкала (112) и подписи дней (30). Если колонка станет ниже суммы,
        подпись самого высокого столбца срежется ее краем."""
        stack = int(re.search(r"\.dyn-stack\{[^}]*height:(\d+)px", STYLE).group(1))
        cols = int(re.search(r"\.dyn-cols\{[^}]*height:(\d+)px", STYLE).group(1))
        day = int(re.search(r"\.dyn-day\{height:(\d+)px", STYLE).group(1))
        margin = int(re.search(r"\.dyn-stack\{[^}]*margin-top:(\d+)px", STYLE).group(1))
        assert cols == margin + stack + day, "высота колонки = запас + шкала + подписи"
        assert margin >= 14, "под число над столбцом нужно ~12px"
        # Ось и сетка натянуты на ту же шкалу, что и столбцы: top — запас,
        # bottom — полоса подписей, иначе линии уедут от высоты столбцов.
        for sel in (".dyn-grid", ".dyn-yaxis"):
            rule = STYLE[STYLE.index(sel + "{"):]
            rule = rule[:rule.index("}")]
            assert f"top:{margin}px" in rule and f"bottom:{day}px" in rule, sel

    def test_numbers_are_on_the_chart_not_only_in_the_tooltip(self):
        """Просьба «пусть хотя бы цифры показывает» — про сам график: подписи
        над столбцами, подписанная ось и сетка по тем же делениям."""
        assert ".dyn-vlab{" in STYLE and ".dyn-tick{" in STYLE
        assert ".dyn-grid i{" in STYLE
        # Плотный ряд прячет подписи (числа остаются в подсказке и на оси).
        assert ".dyn-chart.is-dense .dyn-vlab{display:none}" in STYLE
        assert "dyn-vlab" in APP_JS and "dyn-tick" in APP_JS
        assert "class=\"dyn-vlab" in APP_JS

    def test_tooltip_is_not_clipped_by_the_scrolling_row(self):
        """Подсказку резали и .dyn-cols (overflow-x:auto), и сама панель
        статистики: у высокого столбца карточка над ним уезжала за верх
        панели. Поэтому она живёт в <body> и позиционируется position:fixed."""
        tip_pos = STYLE.index(".dyn-tip{")
        rule = STYLE[tip_pos:STYLE.index("}", tip_pos)]
        assert "position:fixed" in rule
        assert "transform:" not in rule, "сдвиг через transform не складывается с краями окна"
        assert "_dailyTip.className = 'dyn-tip'" in APP_JS
        assert "document.body.appendChild(_dailyTip)" in APP_JS
        assert 'class="dyn-tip"' not in APP_JS, "в разметке графика подсказки больше нет"
        # Позиция — из геометрии колонки в CSS-пикселях окна (те же единицы,
        # что и у fixed): при масштабировании страницы она не уезжает.
        assert "col.getBoundingClientRect()" in APP_JS
        assert "window.innerWidth" in APP_JS and "window.innerHeight" in APP_JS
        assert "chart.getBoundingClientRect()" not in APP_JS, "расчёт от родителя больше не нужен"

    def test_tooltip_hides_when_the_boxes_move_without_the_cursor(self):
        """Прокрутка и смена масштаба двигают столбцы без mousemove: подсказку
        надо спрятать, а не оставить висеть в устаревшей точке."""
        assert "addEventListener('scroll', _hideDailyTip" in APP_JS
        assert "addEventListener('resize', _hideDailyTip)" in APP_JS
        # Позиция пересчитывается на каждом mousemove, а не только при смене дня.
        assert "if (col) _showDailyTip(col); else _hideDailyTip();" in APP_JS

    def test_tooltip_goes_below_when_there_is_no_room_above(self):
        assert "function _dailyTipBounds(" in APP_JS
        assert "function _placeDailyTip(" in APP_JS
        assert "tip.classList.toggle('is-below', below)" in APP_JS
        assert "const below = top < minTop;" in APP_JS
        assert "const maxTop = Math.max(minTop, b.bottom - size.height - pad);" in APP_JS, \
            "нижняя граница не должна перебивать верхнюю"

    def test_today_is_a_hourly_chart(self):
        """«Сегодня» — график по часам: время поиска пишется в имя raw-файла
        (`raw_2026-09-30_14-01_…`), поэтому 14:01 и 14:50 попадают в колонку
        «14». Без файлов с часом дневной столбец честнее пустых суток."""
        assert "function dailyHoursChartHTML(" in APP_JS
        assert "payload.hours && payload.hours.some(h => h.found)" in APP_JS
        assert "def _file_parse_hour(" in API_PY
        assert "_DATETIME_IN_NAME" in API_PY
        assert "'&hours=1'" in APP_JS, "запрос просит почасовой разворот"
        assert "a.get(\"hours\", type=int) == 1" in API_PY

    def test_columns_fill_the_chart_width(self):
        """7 дней растягиваются на всю ширину графика, а не занимают узкую
        ленту слева. Единственный дневной столбец («Сегодня» без почасовых
        данных) ограничивается отдельно."""
        assert "max-width:72px" not in STYLE, "лента колонок + пустое место справа"
        assert re.search(r"\.dyn-col\{[^}]*flex:1 1 0", STYLE)
        assert ".dyn-cols.is-single .dyn-col{max-width:120px}" in STYLE

    def test_results_table_phones_and_socials_columns(self):
        """Телефоны: десяток номеров через запятую растягивал таблицу за
        горизонт. Соцсети наоборот — колонке задаём минимум."""
        assert "function phoneHTML(" in APP_JS
        assert 'class="tbl-phone"' in APP_JS
        assert re.search(r'#results-table td\[data-col="phone"\]\{max-width:\d+px\}', STYLE)
        assert re.search(r'#results-table th\[data-col="socials"\],#results-table td\[data-col="socials"\]\{min-width:\d+px', STYLE)
        assert ".tbl-phone{" in STYLE and ".tbl-phone span{display:block" in STYLE

    def test_stats_breakdowns_use_donut_and_cards(self):
        """Соцсети — кольцо с долями, каждый разбор — своя карточка сеткой:
        длинная колонка секций читалась как один сплошной список."""
        assert "function donutHTML(" in APP_JS
        assert "donutHTML(socialCounts" in APP_JS
        assert ".stats-grid{" in STYLE and ".stats-panel{" in STYLE
        assert "grid-template-columns:repeat(3,minmax(0,1fr))" in STYLE
        assert ".donut{" in STYLE
        assert ".donut-legend-row{" in STYLE

    def test_cities_panel_scrolls_after_two_cards(self):
        """С десятком городов панель тянула всю вкладку: видно две карточки,
        остальные листаются внутри панели — высоту берём по самим карточкам."""
        assert ".stats-panel-cities .stat-city-grid.is-scroll{" in STYLE
        assert "overflow-y:auto" in STYLE
        assert "'.stats-panel-cities .stat-city-grid'" in APP_JS
        assert "cityGrid.children.length > 2" in APP_JS
        assert "cityGrid.style.maxHeight = two + 'px'" in APP_JS

    def test_score_badge_has_no_hover_tooltip(self):
        """Разбор оценки открывается кликом: всплывающая подсказка дублировала
        его и висела поверх таблицы. Окно разбора получает свою рамку."""
        assert "function scoreWhyText(" not in APP_JS
        # Всплывающий title в бейдже — только у рейтинга и отзывов, не у оценки.
        badge = APP_JS[APP_JS.index("function scoreHTML("):APP_JS.index("let _scorePop")]
        assert "title=" not in badge
        assert "нажмите, чтобы увидеть разбор" in badge
        assert ".score-pop.hot{border-top-color:var(--ok-strong)}" in STYLE

    def test_stats_tab_has_no_service_analytics(self):
        """RPS, задержки и кэш — служебные числа: в статистике их больше нет."""
        assert "${UI_ICONS.bolt}Аналитика" not in APP_JS
        assert "RPS (факт.)" not in APP_JS
        assert "fetch('/cache/stats')" not in APP_JS

    def test_results_have_one_source_and_no_raw_processed_toggle(self):
        """После обработки «Сырые» и «Обработанные» совпадали — переключатель
        убран, таблица сразу показывает итог этапа 2."""
        assert "results-toggle" not in TEMPLATE
        assert 'id="results-toggle"' not in APP_JS
        assert "let _resultsView = 'processed';" in APP_JS
        assert "Сырые данные</button>" not in TEMPLATE
        assert "Обработанные</button>" not in TEMPLATE

    def test_dashboard_facts_are_readable(self):
        """Итоги периода — не сноска: средний темп крупнее, лучший день
        подсвечен зелёным, доля разобранного — жирным значением."""
        assert 'class="dyn-fact dyn-fact-avg"' in APP_JS
        assert 'class="dyn-fact dyn-fact-best"' in APP_JS
        assert 'class="dyn-fact dyn-fact-share"' in APP_JS
        assert ".dyn-fact-avg{font-size:13px}" in STYLE
        assert ".dyn-fact-best b{color:var(--grn)}" in STYLE
        assert ".dyn-fact-share b{font-weight:800}" in STYLE

    def test_done_status_is_neutral_not_green(self):
        """«Готово» — приглушённая пилюля в тоне шапки: поиск закончен,
        и самое яркое пятно на экране не должно молчать про это."""
        start = STYLE.index("#status-badge.done{")
        rule = STYLE[start:STYLE.index("}", start)]
        assert "var(--grn)" not in rule and "var(--ok-bg)" not in rule, rule
        for dark in ("[data-theme=\"dark\"] #status-badge.done{",):
            rule_d = STYLE[STYLE.index(dark) + len(dark):]
            rule_d = rule_d[:rule_d.index("}")]
            assert "var(--grn)" not in rule_d, rule_d

    def test_no_quota_card_left_in_the_interface(self):
        """Платных API в приложении нет — счётчика квоты и ручного ввода
        расхода тоже быть не должно (ни разметки, ни стилей)."""
        assert "quota-manual" not in APP_JS
        assert "quota-card" not in APP_JS and ".quota-card{" not in STYLE
        assert "setTwogisQuotaManual" not in APP_JS
        # Классы «громких» строк лога остались: ими подсвечиваются лимиты
        # внешних сервисов, если они когда-нибудь появятся.
        assert ".ll.quota-warn{" in STYLE

    def test_social_badges_have_full_names(self):
        """VK/TG/WA в таблице расшифровываются при наведении."""
        assert 'SNAMES[p] || SLABELS[p]' in APP_JS

    def test_donut_is_clean_ring_without_inner_labels(self):
        """Кольцо без подписей внутри секторов: они сливались с соседней
        дугой и наезжали на край; точные значения — в легенде рядом."""
        assert "donut-pct" not in APP_JS
        assert "donut-pct" not in STYLE
        assert 'class="donut-arc"' in APP_JS
        # Анимация появления: дуга вырастает из нуля, остаток дуги -- в переменной.
        assert ".donut .donut-arc{animation:donut-in" in STYLE
        assert "--dash-rest" in APP_JS and "--dash-rest" in STYLE

    def test_columns_button_is_visible_and_dropdown_aligned(self):
        """«Столбцы» заметнее соседей; список — ровные колонки
        чекбокс|подпись; фильтр соцсетей прячется вместе с колонкой."""
        assert "#btn-cols{\n  /* Кнопка заметнее" in STYLE
        assert ".col-item{\n  display:grid;grid-template-columns:14px 1fr" in STYLE
        assert "col-hidden" in APP_JS and ".tbl-social-row.col-hidden" in STYLE
        # Фильтр соцсетей также исчезает, когда их не собирали (socials-off).
        assert ".tbl-social-row.socials-off{display:none}" in STYLE

    def test_data_export_import_is_in_ui(self):
        """Экспорт/импорт отметок и настроек — в аккордеоне «Форматы результата»
        (бывшая вкладка «Форматы вывода» удалена: выбор полей живёт в «Что парсить»)."""
        assert 'id="data-import-file"' in TEMPLATE
        assert "exportAppData" in APP_JS and "importAppData" in APP_JS
        assert '@bp.route("/data/export")' in API_PY
        assert '@bp.route("/data/import", methods=["POST"])' in API_PY
        assert "_backup_reviewed" in API_PY

    def test_issue_api_send_and_screenshot_copy_are_in_ui(self):
        """Окно «Сообщить о проблеме»: отправка через API и копирование скриншота.

        GitHub API не создаёт issue анонимно — в окне обязана быть запасная
        кнопка формы (она работает и без токена); у картинки, выбранной
        файлом, есть кнопка «в буфер», иначе вставка в форме GitHub
        не работает. Поле токена в окне больше НЕТ: его заменил вход
        по коду — device flow (test_issue_window_offers_github_login_instead_of_token).
        """
        for needle in ("sendReportIssue", "rep-issue", "Создать issue",
                       "has_token", "Открыть форму на GitHub"):
            assert needle in APP_JS, needle
        assert "copyReportShot" in APP_JS
        assert "Скопировать скриншот в буфер" in APP_JS
        assert "_shotPngBlob" in APP_JS, "для буфера нужен именно PNG"
        # Серверская сторона того же окна.
        routes = (ROOT / "routes" / "diagnostics.py").read_text(encoding="utf-8")
        assert '@bp.route("/report/issue", methods=["POST"])' in routes
        assert "GITHUB_TOKEN" in routes

    def test_issue_window_offers_github_login_instead_of_token(self):
        """Поля токена больше нет — вместо него вход в GitHub ссылкой.

        Токен вводить не требуется: его роль приняла авторизация по коду
        (device flow) на сервере (.env, GITHUB_TOKEN получает сам), а без
        токена сообщение уходит заполненной формой. Кнопки «Скопировать
        текст» и «Закрыть» тоже убраны: закрывает крестик и «Отменить»
        (с подтверждением, если что-то введено).
        """
        assert "rep-token" not in APP_JS, "поле токена вернулось в окно"
        assert "ghp_" not in APP_JS, "плейсхолдер токена вернулся"
        assert "copyReportBody" not in APP_JS, "«Скопировать текст» убрана"
        assert "github.com/login" in APP_JS, "нет ссылки на вход в GitHub"
        assert "rep-gh-login" in APP_JS, "нет блока входа в GitHub"
        # Вход — device flow: кнопка, показ кода и поллинг сервера.
        for needle in ("startGitHubDeviceLogin", "rep-gh-login-btn",
                       "device/start", "device/poll", "rep-gh-usercode"):
            assert needle in APP_JS, needle
        # Серверские маршруты того же входа.
        routes = (ROOT / "routes" / "diagnostics.py").read_text(encoding="utf-8")
        for route in ('@bp.route("/report/github/device/start", methods=["POST"])',
                      '@bp.route("/report/github/device/poll", methods=["POST"])'):
            assert route in routes, route
        # Кнопка входа показывается только если client_id зашит в сборку:
        # иначе обычному пользователю предлагают лишь заполненную форму,
        # без единого упоминания OAuth Apps.
        assert "can_device" in APP_JS, "нет признака доступности входа"
        assert "can_device" in routes, "сервер не сообщает can_device"
        assert "GH_DEVICE_CLIENT_ID_DEFAULT" in routes, "client_id не зашит в сборку"
        # Выбор меток и контекста запоминается между открытиями окна.
        for needle in ("yp_report_choices_v1", "_reportSaveChoices",
                       "_reportRestoreChoices"):
            assert needle in APP_JS, needle
        for needle in ("cancelReportModal", "Отменить", "rep-x",
                       "_reportSnapshot", "_reportDirty"):
            assert needle in APP_JS, needle
        # Окно выше экрана не бывает: у базовой модалки есть прокрутка.
        assert "max-height:calc(100vh - 32px)" in STYLE
        assert "overflow-y:auto" in STYLE

    def test_issue_window_labels_are_a_colored_dropdown(self):
        """Метки GitHub — выпадающий список с цветными пилями, как на GitHub.

        Раньше это был список из пяти галочек на всю высоту окна; теперь
        поле раскрывается в список, а цвета меток берутся из палитры GitHub.
        """
        for needle in ("rep-label-field", "rep-label-menu", "rep-label-pills",
                       "gh-pill", "_ghPillCss", "_repRenderPills",
                       "aria-multiselectable"):
            assert needle in APP_JS, needle
        # Цвета меток заданы и совпадают с палитрой GitHub.
        for color in ("#d73a49", "#a2eeef", "#d876e3", "#0075ca", "#8250df"):
            assert color in APP_JS, color
        assert ".rep-label-menu{" in STYLE
        assert ".gh-pill{" in STYLE

    def test_settings_export_button_sits_next_to_reset(self):
        """«Экспорт настроек» — ровно перед «Сбросить настройки» (зеркало справа)."""
        assert 'id="btn-export-settings"' in TEMPLATE
        assert "exportAppSettings()" in TEMPLATE
        assert "Экспорт настроек" in TEMPLATE
        assert TEMPLATE.index('id="btn-export-settings"') \
            < TEMPLATE.index('id="btn-reset-settings"'), "экспорт стоит перед сбросом"
        assert "function exportAppSettings" in APP_JS
        # И обратный путь: импорт принимает browser.json из архива.
        assert "browser.json" in API_PY
        assert "applyImportedBrowserSettings" in APP_JS
        # Кнопка копирования скриншота живёт вне rep-shot (там роль button —
        # кнопка внутри была бы вложенным элементом управления).
        assert ".rep-shot-actions{display:flex" in STYLE
        assert 'id="rep-shot-actions"' in APP_JS

    def test_hidden_attribute_always_wins(self):
        """Оверлеи задают display:flex — без глобального правила для [hidden]
        скрытый экран оставался поверх интерфейса и перехватывал все клики:
        приложение выглядело полностью заблокированным. Это правило —
        фундамент для «работа невозможна» и гейта устаревшей версии."""
        assert "[hidden]{display:none!important}" in STYLE
        for overlay in ('id="terms-declined"', 'id="version-gate"'):
            assert overlay in TEMPLATE

    def test_every_day_carries_its_own_numbers(self):
        """Колонка несёт данные для подсказки: иначе карточка при наведении
        показывала бы не тот день, на который наведён курсор."""
        for attr in ("data-wd", "data-dm", "data-found", "data-review", "data-files", "data-pct"):
            assert attr in APP_JS, attr
        assert "const axis = dailyAxis(maxFound)" in APP_JS
        assert "function dailyAxis(" in APP_JS


class TestParseFieldsAccordion:
    """Аккордеон «02 · Что парсить»: обычные и персональные данные.

    Выбор полей заменил вкладку «Форматы вывода» и управляет сбором соцсетей.
    """

    def test_accordion_numbering_is_sequential(self):
        # 01 Основные → 02 Что парсить → 03 Глубина → 04 Фильтрация → 05 Форматы.
        order = ['acc-basic', 'acc-parse', 'acc-tech', 'acc-filters', 'acc-formats']
        pos = [TEMPLATE.index(f'id="{a}"') for a in order]
        assert pos == sorted(pos), "аккордеоны идут не по порядку"
        for a, num in zip(order, ['01', '02', '03', '04', '05']):
            start = TEMPLATE.index(f'id="{a}-hdr"')
            seg = TEMPLATE[start:start + 400]
            assert f'>{num}</span>' in seg, f"{a} должен быть под номером {num}"

    def test_parse_grid_has_both_groups(self):
        assert 'id="acc-parse"' in TEMPLATE
        assert 'id="parse-regular-grid"' in TEMPLATE
        assert 'id="parse-personal-grid"' in TEMPLATE
        assert 'Обычные данные' in TEMPLATE
        assert 'Персональные данные' in TEMPLATE
        # Персональные данные предупреждают про 152-ФЗ.
        assert '152-ФЗ' in TEMPLATE

    def test_gating_hooks_exist(self):
        # Соцсети/массовый обход/статистика прячутся, когда соцсети не собираются.
        for needle in ('id="social-mode-block"', 'id="vk-activity-group"',
                       'id="bulk-panel"', 'id="retention-block"',
                       'id="f-retention-days"'):
            assert needle in TEMPLATE, needle
        for fn in ('renderParseFields', 'toggleParseField', 'updateSocialUI',
                   'updateVkGate', 'socialsEnabled', 'onRetentionChange',
                   'initRetention', 'getExcelCols'):
            assert f'function {fn}(' in APP_JS, fn
        # Карточку грузим, если в «Что парсить» отмечено хотя бы одно «карточное»
        # поле, а не только соцсети: телефон/сайт есть ТОЛЬКО на карточке, и при
        # выключенных соцсетях они молча пропадали из таблицы.
        assert 'fetch_detail:    detailFetchEnabled()' in APP_JS
        assert 'function detailFetchEnabled(' in APP_JS
        assert 'CARD_FIELDS' in APP_JS and "'phone'" in APP_JS

    def test_retention_routes_exist(self):
        assert '@bp.route("/retention/status")' in API_PY
        assert '@bp.route("/retention/set", methods=["POST"])' in API_PY


class TestLiveSetupSummary:
    """Живая сводка настройки: главное видно без раскрытия аккордеонов.

    Сайдбар — длинная форма из пяти разделов, и «что я запускаю» приходилось
    собирать глазами по всей панели. Сводка показывает запрос, города, тип
    организаций, соцсети и форматы, а каждый чип ведёт в свой раздел.
    """

    def test_container_and_script_are_wired(self):
        assert 'id="setup-summary"' in TEMPLATE
        assert 'aria-label="Текущие настройки поиска"' in TEMPLATE
        # Модуль подключён ПОСЛЕ остальных: он пользуется их функциями
        # (toggleAccordion, escapeHtml) и самодостаточен по инициализации.
        assert TEMPLATE.index("js/12-setup-summary.js") > TEMPLATE.index("js/11-app-init.js")
        assert "js/12-setup-summary.js" in APP_JS or "buildSetupSummary" in APP_JS

    def test_module_lists_stay_in_sync_with_the_template(self):
        """Склейка для тестов обязана включать новые модули.

        Функции из неподключённого модуля не найдёт ни grab() в node-тестах,
        ни текстовая проверка в pytest — сводка молча «исчезала» бы из
        покрытия, оставаясь в интерфейсе.
        """
        assert "12-setup-summary.js" in (ROOT / "tests" / "_appjs.py").read_text(encoding="utf-8")
        assert "12-setup-summary.js" in (ROOT / "tests" / "ui" / "_src.mjs").read_text(encoding="utf-8")

    def test_summary_covers_the_five_things(self):
        for key in ("queries", "cities", "type", "socials", "formats"):
            assert f"{key}:" in APP_JS, key
        # Каждый чип знает свой раздел — иначе клик никуда не ведёт.
        assert "SETUP_SUM_TARGETS" in APP_JS
        assert "acc-basic" in APP_JS and "acc-formats" in APP_JS

    def test_missing_values_are_marked_not_just_empty(self):
        """Пустой запрос/город/формат — предупреждение, а не тихий прочерк."""
        assert "is-missing" in APP_JS
        assert ".setup-chip.is-missing{" in STYLE
        assert "var(--warn-bg)" in STYLE[STYLE.index(".setup-chip.is-missing{"):][:200]

    def test_redraw_is_throttled_to_one_frame(self):
        """Сводка пересобирается раз в кадр, а не на каждое событие формы."""
        assert "requestAnimationFrame" in APP_JS
        assert "document.addEventListener('input', schedule, true)" in APP_JS

    def test_chips_are_real_buttons_with_labels(self):
        """Чип — кнопка: клавиатура и скринридер достаются бесплатно."""
        start = APP_JS.index("function renderSetupSummary(")
        body = APP_JS[start:start + 1200]
        assert '<button type="button" class="setup-chip' in body
        assert 'aria-label="${escapeHtml(it.label)}' in body

    def test_summary_survives_the_closed_basic_section(self):
        """Строка раздела больше не дублирует сводку при открытом разделе."""
        start = APP_JS.index("function updateBasicSummary(")
        body = APP_JS[start:start + 900]
        assert "classList.contains('open')" in body
        assert "summaryHidden || !collapsed" in body


class TestSecondaryInformationOnDemand:
    """Неглавное прячется до наведения — список разделов перестал быть
    десятью строками текста."""

    def test_accordion_subtitles_reveal_on_hover_and_focus(self):
        assert "@media (hover:hover) and (pointer:fine)" in STYLE
        block = STYLE[STYLE.index("@media (hover:hover) and (pointer:fine)"):][:400]
        assert ".acc-sub{opacity:0" in block
        assert ".acc-hdr:hover .acc-sub" in block
        # Клавиатура видит то же, что и мышь.
        assert ".acc-hdr:focus-visible .acc-sub" in block

    def test_open_section_keeps_its_subtitle(self):
        assert ".acc.open .acc-sub{opacity:1}" in STYLE


class TestInteractivity:
    """Оживление интерфейса: движения только там, где они что-то сообщают."""

    def test_counter_pops_only_when_the_number_changes(self):
        start = APP_JS.index("function setRunFound(")
        body = APP_JS[start:start + 520]
        assert "el.textContent === next" in body, "пульсация должна зависеть от смены значения"
        assert "classList.add('pop')" in body
        assert "#run-found.pop{animation:found-pop" in STYLE

    def test_progress_track_breathes_while_the_run_is_live(self):
        assert "body:has(.run-hero:not(.is-hidden)) #run-track" in STYLE
        assert "@keyframes hero-breathe" in STYLE

    def test_panel_and_chip_entrance_animations_exist(self):
        assert "@keyframes panel-in" in STYLE
        assert "@keyframes setup-val-pop" in STYLE
        assert ".setup-chip.bump .setup-chip-val{animation:setup-val-pop" in STYLE

    def test_reduced_motion_turns_the_new_motion_off(self):
        """Все новые анимации выключаются при prefers-reduced-motion."""
        tail = STYLE[STYLE.index("/* ── Уважать «уменьшенное движение» ── */"):]
        for needle in (".setup-sum,", ".setup-chip.bump .setup-chip-val",
                       "#run-found.pop",
                       # Дыхание дорожки прогресса гасится вместе с анимацией.
                       "body:has(.run-hero:not(.is-hidden)) #run-track{animation:none"):
            assert needle in tail, needle


class TestAccessibility:
    """Доступность: вкладки, скачок к содержимому, читаемые фоны кнопок."""

    def test_tab_bar_follows_the_aria_tablist_pattern(self):
        start = APP_JS.index("function showTab(")
        body = APP_JS[start:start + 900]
        # Класс .active и aria-selected больше не расходятся.
        assert "b.setAttribute('aria-selected', on ? 'true' : 'false')" in body
        assert "b.tabIndex = on ? 0 : -1" in body, "roving tabindex: в Tab — только активная вкладка"
        # Стрелки, Home и End листают вкладки.
        kb = APP_JS[APP_JS.index("function initTabListKeyboard("):][:1400]
        for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
            assert f"'{key}'" in kb, key
        assert "next.focus()" in kb

    def test_skip_link_goes_to_the_content_region(self):
        assert 'class="skip-link" href="#main-content"' in TEMPLATE
        assert 'id="main-content"' in TEMPLATE
        assert ".skip-link{" in STYLE
        # Видна только при фокусе с клавиатуры.
        assert ".skip-link:focus-visible" in STYLE
        assert "top:-60px" in STYLE

    def test_percentage_padding_has_no_room_for_a_scroll_trap(self):
        """Сводка не должна вылезать за панель (иначе горизонтальный скролл)."""
        assert ".setup-sum{" in STYLE
        block = STYLE[STYLE.index(".setup-sum{"):][:260]
        assert "grid-template-columns:1fr 1fr" in block


class TestOnboardingStepsAreActions:
    """Шаги «Как это работает» — статичные карточки с кликабельными словами.

    Раньше вся карточка была одной большой кнопкой. Теперь нажимаются только
    выделенные ключевые слова: каждое ведёт к своему полю или разделу, и
    пользователь видит, куда именно попадёт.
    """

    def _how(self):
        start = TEMPLATE.index('class="flow-steps"')
        return TEMPLATE[start:TEMPLATE.index('onboarding-tip', start)]

    def test_steps_are_cards_not_buttons(self):
        how = self._how()
        assert how.count('class="flow-step"') == 3
        assert how.count('<article class="flow-step"') == 3, \
            "шаг — карточка, кликается только ключевое слово внутри"
        assert '<button type="button" class="flow-step"' not in how, \
            "вся панель снова стала кнопкой"
        assert 'onclick="onboardingStep' not in how

    def test_keywords_are_interactive_and_lead_to_exact_places(self):
        how = self._how()
        assert how.count('class="flow-key"') == 5
        for key in ("queries", "city", "run", "results", "messages"):
            assert f"onboardingKeyword('{key}')" in how, key
        # У каждой кнопки-слова есть понятное имя для скринридера.
        assert how.count('aria-label="') >= 5

    def test_handler_says_what_is_missing_instead_of_failing_silently(self):
        start = APP_JS.index("function onboardingStep(")
        body = APP_JS[start:start + 2200]
        assert "showToast(" in body, "без подсказки шаг просто ничего не делает"
        assert "Выберите хотя бы один город" in body
        assert "btn-run" in body, "шаг 2 обязан запускать тот же поиск, что и кнопка"
        assert "showTab('table')" in body, "шаг 3 ведёт к результатам"

    def test_keyword_handler_goes_to_the_exact_field(self):
        start = APP_JS.index("function onboardingKeyword(")
        body = APP_JS[start:start + 900]
        assert "'f-queries'" in body and "'f-city-input'" in body
        assert "showTab('templates')" in body, "слово «сообщение» ведёт к шаблонам"
        assert "onboardingStep(2)" in body and "onboardingStep(3)" in body

    def test_focus_lands_after_the_click(self):
        """Фокус ставится после клика: иначе его съедает нажатая кнопка."""
        start = APP_JS.index("function _onboardingFocus(")
        body = APP_JS[start:start + 500]
        assert "setTimeout(" in body
        assert "el.focus({ preventScroll: true })" in body

    def test_cards_are_static_but_keywords_look_clickable(self):
        start = STYLE.index(".flow-step{\n  display:grid")
        block = STYLE[start:start + 500]
        assert "cursor:pointer" not in block, "карточка не должна обещать клик"
        assert "background:var(--panel)" in block
        key = STYLE.index(".flow-key{")
        key_block = STYLE[key:key + 500]
        assert "cursor:pointer" in key_block
        assert "background:var(--card)" in key_block
        assert ".flow-key:focus-visible" in STYLE
        assert ".flow-steps{" in STYLE and "flex-direction:column" in STYLE


class TestOnboardingCanBeReopened:
    """«Как это работает» открывается заново после старта поиска.

    Первый экран удаляется при первой строке лога, поэтому нужен способ
    вернуться к инструкции во время прогона, а не только до него.
    """

    @staticmethod
    def _fn(name: str, limit: int = 2000) -> str:
        start = APP_JS.index("function " + name + "(")
        return APP_JS[start:start + limit]

    def test_log_toolbar_has_the_button(self):
        assert 'id="btn-log-howto"' in TEMPLATE
        assert 'onclick="toggleOnboardingHelp()"' in TEMPLATE
        # Статичный aria-controls называл два id сразу и после закрытия
        # инструкции указывал на удалённый узел — связку «кнопка — панель»
        # теперь ведёт syncOnboardingButton() по факту наличия региона.
        assert 'aria-controls="onboarding' not in TEMPLATE
        assert 'aria-expanded="false"' in TEMPLATE
        assert "#i-book" in TEMPLATE

    def test_help_button_controls_attribute_follows_the_open_panel(self):
        sync = self._fn("syncOnboardingButton", 900)
        assert "removeAttribute('aria-controls')" in sync, (
            "кнопка обязана забывать aria-controls, когда панели нет")
        assert "setAttribute('aria-controls', target)" in sync
        assert "syncOnboardingButton();" in self._fn("closeOnboardingHelp", 300)

    def test_instruction_is_cached_before_the_first_log_line(self):
        assert "cacheOnboardingHtml();" in APP_JS
        cache = self._fn("cacheOnboardingHtml", 400)
        assert "innerHTML" in cache, "без снимка разметки кнопка покажет пустоту"
        # Первая строка лога убирает первый экран — кнопка обязана узнать об этом.
        log = self._fn("appendLog", 1400)
        assert "syncOnboardingButton()" in log

    def test_reopened_card_sits_above_the_log_and_has_a_close(self):
        body = self._fn("toggleOnboardingHelp")
        assert "host.parentElement.insertBefore(wrap, host)" in body, \
            "подсказка должна вставать над журналом, а не внутрь прокрутки"
        assert "onb-close" in body and "closeOnboardingHelp" in body
        assert "aria-expanded" in APP_JS
        # Шаги и ключевые слова закрывают подсказку перед переходом к полю.
        assert "closeOnboardingHelp();" in self._fn("onboardingKeyword", 400)
        assert "closeOnboardingHelp();" in self._fn("onboardingStep", 500)

    def test_reopened_card_has_its_own_scroll(self):
        assert "#onboarding-help{" in STYLE
        start = STYLE.index("#onboarding-help{")
        block = STYLE[start:STYLE.index("}", start)]
        assert "max-height:min(46vh,460px)" in block
        assert "overflow:auto" in block
        assert "width:auto" in block, "width:100% + поля дают горизонтальную прокрутку"
        assert "#onboarding-help .onb-close{" in STYLE
        assert "#onboarding-help .onb-close .ico{margin:0}" in STYLE


class TestTemplateHotReloadInDevMode:
    """Из исходников шаблоны читаются заново — иначе правка UI видна только
    после перезапуска сервера (Jinja кеширует шаблоны при debug=False)."""

    def test_app_reloads_templates_when_running_from_source(self):
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")
        assert 'app.config["TEMPLATES_AUTO_RELOAD"] = True' in app_py
        assert "app.jinja_env.auto_reload = True" in app_py
        # В собранном приложении (PyInstaller) это лишний stat на рендер.
        assert 'getattr(sys, "frozen", False)' in app_py

class TestStatsGraphics:
    """«Статистика»: распределение рейтинга, готовность лидов, полнота данных."""

    def test_new_graphics_functions_exist(self):
        for name in ("function ratingBucketRows(", "function leadBucketRows(",
                     "function coverageRows(", "function pctBarRows(",
                     "function ratingSectionHTML(", "function leadSectionHTML(",
                     "function coverageSectionHTML(", "function newShare(",
                     "function newSectionHTML("):
            assert name in APP_JS, name

    def test_graphics_are_rendered_into_the_stats_panel(self):
        for call in ("ratingSectionHTML(data)", "leadSectionHTML(data)",
                     "coverageSectionHTML(data)", "newSectionHTML(data)"):
            assert call in APP_JS, call
        assert "class=\"stats-grid\"" in APP_JS
        assert "function statsPanelHTML(" in APP_JS
        for title in ("'Распределение рейтинга'", "'Готовность лидов'",
                      "'Полнота данных'", "'Новые организации'"):
            assert title in APP_JS, title

    def test_bucket_colors_are_theme_tokens(self):
        """Полосы носят var(--…) — цвет следует за темой, а не за строкой."""
        assert "color: 'var(--grn)'" in APP_JS
        assert "background:var(--c)" in APP_JS

    def test_lead_thresholds_match_the_table_badge(self):
        """Пороги лидов в графике — те же 70/45, что у бейджа scoreHTML."""
        assert re.search(r"min:\s*70", APP_JS)
        assert re.search(r"min:\s*45", APP_JS)

    def test_percentages_are_against_all_records(self):
        """Полнота данных меряется от ВСЕХ записей, а не от максимальной."""
        assert "Math.round(r.count / (r.total || 1) * 100)" in APP_JS

    def test_summary_cards_grow_with_quality_metrics(self):
        assert "'Средний рейтинг'" in APP_JS
        assert "'Горячих лидов'" in APP_JS
        # Доля новых — процент в карточке рядом с «Всего найдено».
        assert "lbl: 'Новых'" in APP_JS

    def test_new_organizations_split_bar_is_theme_aware(self):
        """Полоса «новые/повторные» — токены темы, и легенда дублирует числа."""
        assert ".new-split-fresh{background:var(--grn)" in STYLE
        assert ".new-split-repeat{background:var(--bdr-h)" in STYLE
        assert 'class="new-split-dot fresh"' in APP_JS
        assert "role=\"img\" aria-label=\"Новые" in APP_JS

    def test_empty_stats_have_an_illustration(self):
        assert 'class="sta-art" aria-hidden="true"' in APP_JS
        assert ".sta-art{" in STYLE and ".sta-col-hi{" in STYLE


class TestRequiredFieldsAndDockHint:
    """Пустая форма: два обязательных поля и подсказка у серой кнопки.

    Серая «Найти компании» без объяснения читалась как поломка: причина
    жила чипом наверху длинной панели и уезжала из виду. Теперь она
    написана прямо над кнопкой и кликабельна.
    """

    def test_both_required_fields_are_marked_for_eyes_and_screen_readers(self):
        assert TEMPLATE.count('class="req"') == 2
        assert 'aria-label="обязательное поле"' in TEMPLATE
        assert 'Кого будем искать?<span class="req"' in TEMPLATE
        assert 'Где ищем? <span class="req"' in TEMPLATE
        # Требование озвучивается и самим полем.
        assert 'id="f-queries" aria-required="true"' in TEMPLATE
        assert "inp.setAttribute('aria-required', 'true')" in APP_JS

    def test_hint_sits_above_the_button_row(self):
        tail = '<!-- ПРАВО: вкладки -->'
        assert tail in TEMPLATE
        dock = TEMPLATE[TEMPLATE.index('id="run-dock"'):]
        dock = dock[:dock.index(tail)]
        assert 'class="run-hint" id="run-hint"' in dock
        assert 'aria-describedby="run-hint"' in dock
        # Сначала подсказка, потом ряд кнопок: иначе она оказалась бы под CTA.
        assert dock.index('id="run-hint"') < dock.index('class="run-dock-row"')
        assert dock.index('class="run-dock-row"') < dock.index('id="btn-run"')

    def test_hint_is_a_button_that_leads_to_the_missing_field(self):
        assert "function runHintJump()" in APP_JS
        body = APP_JS.split("function runHintJump()")[1][:900]
        assert "toggleAccordion(hdr)" in body
        assert "'f-city-input' : 'f-queries'" in body
        assert "hint.setAttribute('data-need', need)" in APP_JS

    def test_hint_texts_cover_every_empty_state(self):
        assert 'Введите запрос и выберите город — без них поиск не начнётся' in APP_JS
        assert 'Напишите, кого искать — например «кафе»' in APP_JS
        assert 'Выберите город — без него поиск не начнётся' in APP_JS

    def test_styles_keep_the_dock_one_row_of_buttons(self):
        start = STYLE.index('#run-dock.sidebar-footer{')
        rule = STYLE[start:STYLE.index('}', start)]
        assert 'flex-direction:column' in rule
        assert '.run-dock-row{display:flex;gap:8px;align-items:stretch}' in STYLE
        hint = STYLE[STYLE.index('.run-hint{'):]
        hint = hint[:hint.index('}')]
        assert 'cursor:pointer' in hint
        assert 'color:var(--sub)' in hint
        assert 'font-size:12px' in hint
        assert '.run-hint[hidden]{display:none}' in STYLE
        assert 'color:var(--c)' in STYLE[STYLE.index('.req{'):][:80]


class TestFirstScreenCopy:
    """Первый экран: справка вместо тревоги и короткие подсказки.

    «API-ключи ⚠ 0/1» новичок читал как «настройка не закончена» и шёл
    искать ключи, хотя поиску они не нужны. Абзац про пресеты занимал
    четыре строки и отодвигал два обязательных поля вниз.
    """

    def test_api_badge_is_neutral_when_nothing_is_configured(self):
        assert "cls = 'off'; txt = 'необязательно'" in APP_JS
        assert "UI_ICONS.warn + `${have}/${total}`" not in APP_JS
        assert '.api-badge.off{background:var(--cl);color:var(--sub)' in STYLE
        # Пояснение остаётся в подсказке: что именно теряется без ключа.
        assert 'Поиск работает и без ключей.' in APP_JS

    def test_preset_hints_are_one_short_line(self):
        line = 'Сохраните текущий поиск кнопкой «+ Новый» — вернётесь к нему одним кликом.'
        assert line in TEMPLATE
        assert line in APP_JS
        assert 'Выберите пресет — настройки подставятся автоматически.' in APP_JS
        # Запуск без интерфейса — не первый экран для новичка.
        assert 'Тот же пресет запускается без интерфейса' not in APP_JS


class TestDockSurface:
    """Док не просвечивает: подсказка и форма больше не наезжают.

    На первом экране верхние 12px дока были прозрачными, а подсказка
    стояла именно там — сквозь неё читалось «Напишите по одному виду
    бизнеса в строке», и две строки выглядели склеенными.
    """

    def test_dock_has_an_opaque_surface(self):
        start = STYLE.index('#run-dock{')
        rule = STYLE[start:STYLE.index('}', start)]
        assert 'background:var(--card)' in rule
        assert 'transparent 0%' not in rule, 'прозрачная верхушка вернулась'
        assert 'position:sticky' in rule

    def test_separator_is_a_border_not_a_fade(self):
        # Градиент над доком при прокрутке до конца гасил последние 18px
        # формы: нижние галочки выглядели обрезанными. Шов — линия.
        start = STYLE.index('#run-dock{')
        rule = STYLE[start:STYLE.index('}', start)]
        assert 'border-top:1px solid var(--bdr)' in rule
        assert '#run-dock::before' not in STYLE

    def test_hint_sits_on_the_solid_part(self):
        # Подсказка — первый ребёнок дока, а подложка начинается с его
        # верхней границы, поэтому текст всегда на непрозрачном фоне.
        dock = TEMPLATE[TEMPLATE.index('id="run-dock"'):]
        dock = dock[:dock.index('<!-- ПРАВО: вкладки -->')]
        assert dock.index('id="run-hint"') < dock.index('class="run-dock-row"')


class TestCollapsedAccordion:
    """Закрытая секция не показывает обрезанную первую строку.

    Аккордеон сжимается через grid-rows:0fr, но внутренний отступ (12px
    сверху + 16px снизу) оставался видимым — у «Форматы результата»
    торчала половина галочек Excel/JSON.
    """

    def test_collapsed_inner_has_no_vertical_padding(self):
        assert '.acc:not(.open) .acc-inner{padding-top:0;padding-bottom:0}' in STYLE

    def test_padding_collapses_with_the_same_curve_as_the_rows(self):
        body = STYLE[STYLE.index('.acc-body{'):]
        body = body[:body.index('}')]
        assert 'grid-template-rows .26s cubic-bezier(.4,0,.2,1)' in body
        inner = STYLE[STYLE.index('.acc-inner{\n  transition:padding-top'):]
        inner = inner[:inner.index('}')]
        assert 'cubic-bezier(.4,0,.2,1)' in inner


class TestEmptyStates:
    """Пустой экран говорит, что произошло и что нажать.

    «Запустите парсер для получения результатов» — жаргон без подсказки,
    «История пуста» — факт без объяснения, а «Измените настройки» не
    говорило, какие именно и где.
    """

    def test_results_placeholder_names_the_next_step(self):
        assert 'Здесь появятся компании после поиска' in TEMPLATE
        assert 'Запустите парсер' not in TEMPLATE

    def test_filters_point_to_the_section_not_just_settings(self):
        assert 'снимите часть условий в «Фильтрации результата»' in APP_JS
        assert 'Измените настройки.' not in APP_JS
        # Общий плейсхолдер таблицы тоже подсказывает, что менять.
        assert 'Ничего не найдено — измените запрос, города или фильтры' in APP_JS

    def test_history_explains_what_will_appear(self):
        assert 'История пуста — запущенные поиски появятся здесь' in APP_JS

    def test_map_and_stats_promise_data_instead_of_stating_absence(self):
        assert 'Карта пуста: точек пока нет — они появятся после поиска.' in APP_JS
        assert ('здесь появится разбор: рейтинги, горячие лиды '
                'и полнота карточек') in TEMPLATE

    def test_parser_jargon_left_the_user_facing_copy(self):
        for text in (TEMPLATE, APP_JS):
            assert 'собрал парсер' not in text
            assert 'парсер не остановится' not in text


class TestHistoryOwnsThePast:
    """Прошлое — в одном месте: «История» с видами «Поиски» и «Файлы».

    Раньше история поисков была отдельной вкладкой, а история файлов —
    подвкладкой «Результатов»: два похожих раздела про одно и то же.
    Теперь «Результаты» — только текущая таблица, а файлы лежат рядом с
    поисками, которые их создали.
    """

    def _history_panel(self) -> str:
        return TEMPLATE[TEMPLATE.index('id="p-history"'):TEMPLATE.index('id="p-templates"')]

    def test_results_tab_is_only_the_current_table(self):
        table = TEMPLATE[TEMPLATE.index('id="p-table"'):TEMPLATE.index('id="p-map"')]
        assert 'id="rs-history"' not in table
        assert 'id="results-subtabs"' not in TEMPLATE
        assert 'История файлов' not in TEMPLATE

    def test_history_has_runs_and_files_views(self):
        panel = self._history_panel()
        for needle in ('id="hist-runs"', 'id="hist-files"',
                       'data-hsub="runs"', 'data-hsub="files"',
                       "onclick=\"setHistorySubTab('files')\""):
            assert needle in panel, needle
        assert panel.index('id="hist-runs"') < panel.index('id="hist-files"')

    def test_file_browser_lives_inside_history(self):
        panel = self._history_panel()
        for needle in ('id="history-raw"', 'id="history-processed"',
                       'id="history-archive"', 'onclick="loadFilesPanel(true)"',
                       'id="btn-files-bulk-delete"'):
            assert needle in panel, needle

    def test_file_card_opens_the_table_by_click(self):
        """Кнопка «открыть в таблице» убрана: открывает сама карточка.

        Четвёртая иконка в ряду читалась как ещё одна служебная кнопка, а
        открыть файл — главное действие карточки. Клик по чекбоксу и по
        самим кнопкам открытие не запускает.
        """
        assert 'data-act="open"' not in APP_JS
        assert 'data-open-path' in APP_JS
        assert "closest('.file-card')" in APP_JS
        assert "closest('input, label, .file-actions')" in APP_JS
        assert ".file-card.is-openable{cursor:pointer}" in STYLE
        assert "is-openable:focus-visible{outline:2px solid var(--c)" in STYLE

    def test_views_toggle_without_replacing_the_table(self):
        assert 'function setHistorySubTab(' in APP_JS
        assert 'function setResultsSubTab(' not in APP_JS
        body = APP_JS.split('function setHistorySubTab(')[1][:700]
        assert 'runs.hidden = files' in body
        assert 'hist.hidden = !files' in body
        # Переход в «Результаты» из файла не должен просить общий срез:
        # иначе он перетрёт открытый файл ответом «последний поиск».
        assert "showTab('table', true)" in APP_JS
        assert 'function showTab(name, skipLoad)' in APP_JS


class TestCityInputCommit:
    """Город не теряется и фиксируется до клика по кнопке.

    Раньше уход фокуса сохранял только совпадение со справочником, а
    «Уфа, Башкортостан» молча стирал. И чип появлялся через 200мс — уже
    после клика по серой «Найти компании», поэтому первый клик пропадал.
    """

    def test_unknown_names_are_added_not_dropped(self):
        assert 'function commitCityInput()' in APP_JS
        body = APP_JS.split('function commitCityInput()')[1][:600]
        assert 'addCity(match ? match.name : text)' in body
        assert "citySearchText = ''" in body

    def test_blur_commits_before_the_dropdown_delay(self):
        assert "e.relatedTarget && dd.contains(e.relatedTarget)" in APP_JS
        # Первый клик должен застать уже готовую кнопку.
        assert 'commitCityInput();' in APP_JS
        assert 'setTimeout(() => {\n      if (dd.contains(document.activeElement)) return;' in APP_JS


class TestOpenResultFolder:
    """Рядом со скачиванием — «Открыть папку с результатами».

    Файлы лежат на диске, а не только в загрузках браузера; папку по
    умолчанию новичок не знает и ищет вручную.
    """

    def test_button_lives_in_the_download_row(self):
        start = TEMPLATE.index('id="dl-section"')
        row = TEMPLATE[start:TEMPLATE.index('</div>', start)]
        assert 'id="dl-open-folder"' in row
        assert 'openOutputDir(this)' in row
        assert 'aria-label="Открыть папку с результатами"' in row

    def test_one_handler_serves_both_buttons(self):
        assert 'function openOutputDir(btn)' in APP_JS
        body = APP_JS.split('function openOutputDir(btn)')[1][:800]
        assert "document.getElementById('btn-output-open')" in body
        assert 'b.innerHTML = label' in body, 'подпись кнопки должна вернуться как была'

    def test_style_is_secondary_to_downloads(self):
        assert '.dl-open{' in STYLE
        rule = STYLE[STYLE.index('.dl-open{'):]
        rule = rule[:rule.index('}')]
        assert 'border:1px solid var(--bdr)' in rule
        assert 'color:var(--sub)' in rule


class TestCssParts:
    """Стили разбиты на части, и порядок ссылок — это каскад.

    Один style.css на 4700 строк невозможно читать; части названы с
    двумя цифрами, поэтому sorted() — тот же порядок, что в шаблоне.
    """

    def test_monolith_is_gone(self):
        assert not (ROOT / "static" / "css" / "style.css").exists()

    def test_template_links_every_part_in_cascade_order(self):
        linked = re.findall(r'"(\d{2}-[a-z0-9-]+\.css)"', TEMPLATE)
        assert linked, "в шаблоне нет списка частей"
        assert linked == [p.name for p in css_files()], (
            "порядок ссылок в шаблоне должен совпадать с порядком файлов")

    def test_every_part_is_small_enough_to_read(self):
        big = [(p.name, p.read_text(encoding="utf-8").count("\n"))
               for p in css_files() if p.read_text(encoding="utf-8").count("\n") > 450]
        assert not big, f"часть разрослась: {big}"


class TestSectionHierarchy:
    """Разделы различаются не одной полоской.

    «Сбор данных» и «Вывод и фильтрация» были строкой мелких капс и
    сливались с полями; шапки аккордеонов — тем же фоном, что и форма.
    У длинных подсказок — свёртка: короткая строка и подробности по клику.
    """

    def test_group_titles_have_an_accent_bar_and_a_rule(self):
        assert ".group-title::before{" in STYLE
        assert ".group-title::after{" in STYLE
        bar = STYLE[STYLE.index(".group-title::before{"):]
        bar = bar[:bar.index("}")]
        assert "background:var(--c)" in bar

    def test_accordion_header_is_a_separate_surface(self):
        assert ".acc-hdr{background:var(--panel)}" in STYLE
        # Открытая шапка — --acc-soft, а не --cl: в тёмной теме --cl
        # (#1B2028) и --panel (#1C1F26) отличаются на единицу, и открытый
        # блок выглядел закрытым (видно в браузере, ловится тестом ниже).
        assert ".acc.open>.acc-hdr{background:var(--acc-soft)}" in STYLE
        assert ".card-hdr{background:var(--panel)}" in STYLE

    def test_open_accordion_band_is_visible_in_dark(self):
        """Подсветка открытой шапки должна читаться, а не совпадать с фоном."""
        block = DARK_TOKEN_BLOCK[:DARK_TOKEN_BLOCK.index("/*/TOK*/")]

        def token(name):
            m = re.search(rf"--{name}:\s*([^;]+);", block)
            assert m, f"токен --{name} не найден в тёмной теме"
            return m.group(1).strip()

        def rgba(value):
            if value.startswith("#"):
                return (*[int(value[i:i + 2], 16) for i in (1, 3, 5)], 1.0)
            nums = [float(n) for n in re.findall(r"[\d.]+", value)]
            return (*nums[:3], nums[3] if len(nums) > 3 else 1.0)

        card = rgba(token("card"))
        closed = rgba(token("panel"))
        wash = rgba(token("acc-soft"))
        blended = [wash[i] * wash[3] + card[i] * (1 - wash[3]) for i in range(3)]
        delta = max(abs(blended[i] - closed[i]) for i in range(3))
        assert delta >= 8, (
            f"открытая шапка почти не отличается от закрытой: "
            f"{tuple(round(v) for v in blended)} vs {closed[:3]}")

    def test_basic_parameters_groups_are_separated(self):
        # Три группы «Основных параметров» шли подряд без границ.
        assert "#acc-basic-body > .acc-inner > div + div{" in STYLE
        block = STYLE[STYLE.index("#acc-basic-body > .acc-inner > div + div{"):]
        assert "border-top:1px solid var(--bdr)" in block[:block.index("}")]

    def test_subheaders_have_a_short_accent(self):
        assert ".sec::before{" in STYLE
        bar = STYLE[STYLE.index(".sec::before{"):]
        assert "height:12px" in bar[:bar.index("}")]

    def test_long_hints_are_collapsed_by_default(self):
        for lead in ("Поиск сам пойдёт дальше",
                     "Ключи платных API не нужны",
                     "Старые файлы удаляются",
                     "Что попадает в историю",
                     "Вежливый режим",
                     "Журнал источников",
                     "Где хранятся отметки"):
            assert lead in TEMPLATE, lead
        assert TEMPLATE.count('<details class="hint-more') >= 6

    def test_collapsible_hint_needs_no_javascript(self):
        assert 'class="hm-more"' in TEMPLATE and 'class="hm-less"' in TEMPLATE
        assert ".hint-more[open] .hm-less{display:inline}" in STYLE
        assert "hint-more" not in APP_JS, "свёртка должна работать без JS"


class TestNarrowWindows:
    """Узкие окна: шапка и вкладки не должны прятать содержимое.

    На 1280 заголовок ломался на две строки в колонке 142px (разделитель
    висел в конце первой), на 1024 и 900 «Шаблоны сообщений» уезжали
    за край полосы вкладок — часть навигации становилась невидимой.
    """

    def test_title_stays_on_one_line(self):
        block = STYLE[STYLE.index("header h1{"):]
        block = block[:block.index("}")]
        assert "min-width:0" in block
        assert "white-space:nowrap" in block
        assert "text-overflow:ellipsis" in block

    def test_source_suffix_is_dropped_before_the_title_wraps(self):
        # Полное имя (202px) плюс подписи кнопок (1098px) требуют ≥1352px.
        start = STYLE.index("@media(max-width:1351px){")
        block = STYLE[start:STYLE.index("\n}", start)]
        assert ".hdr-sep,.hdr-src{display:none}" in block

    def test_header_labels_hide_before_the_title_is_crushed(self):
        start = STYLE.index("@media(max-width:1270px){")
        block = STYLE[start:STYLE.index("\n}", start)]
        assert ".hdr-right > button .hdr-lbl{display:none}" in block

    def test_narrow_window_hides_low_priority_chrome(self):
        start = STYLE.index("@media(max-width:1010px){")
        block = STYLE[start:STYLE.index("\n}", start)]
        assert "#app-version{display:none}" in block
        assert "#notify-txt{display:none}" in block

    def test_narrow_tab_bar_shows_all_six_tabs(self):
        start = STYLE.index("@media(min-width:861px) and (max-width:1023px){")
        block = STYLE[start:STYLE.index("\n}", start)]
        assert "grid-template-columns:repeat(3,1fr)" in block
        assert "overflow:visible" in block, "в сетке не нужна прокрутка полосы"
        assert len(re.findall(r'id="t-[a-z]+"', TEMPLATE)) == 6


class TestSocialTiles:
    """Плитки «Обязательные соцсети»: одна галочка и видимый выбор."""

    @staticmethod
    def _fn(name: str) -> str:
        start = APP_JS.index("function " + name + "(")
        end = APP_JS.find("\nfunction ", start + 1)
        return APP_JS[start:end if end != -1 else None]

    def test_checkmark_is_drawn_once(self):
        # Текст «✓» внутри .soc-mark плюс ::after давали ДВЕ галочки
        # на выбранной плитке — в обеих темах.
        tile_html = self._fn("initSocialNetCheckboxes")
        assert '<span class="soc-mark"' in tile_html
        assert "✓" not in tile_html, "галочку рисует только CSS"
        assert '.soc-tile.on .soc-mark::after{content:"✓"' in STYLE

    def test_selected_tile_stays_selected_in_dark_theme(self):
        # Тёмное правило идёт после .soc-tile.on и при равной специфичности
        # гасило заливку и обводку выбранной плитки.
        assert '[data-theme="dark"] .soc-tile:not(.on)' in STYLE
        start = STYLE.index('[data-theme="dark"] .soc-tile.on{')
        block = STYLE[start:STYLE.index("}", start)]
        assert "border-color:var(--tile" in block
        assert "color-mix(in srgb, var(--tile" in block
        assert STYLE.index('[data-theme="dark"] .soc-tile:not(.on)') < start

    def test_form_social_settings_do_not_refilter_the_table(self):
        # Выбор сетей — параметр следующего сбора, а не фильтр уже
        # показанных результатов: плитка не должна сужать таблицу.
        for fn in ("setSocialMode", "toggleRequiredSocial"):
            assert "filterTable()" not in self._fn(fn), fn
        table = (ROOT / "static" / "js" / "04-results-table.js").read_text(encoding="utf-8")
        start = table.index("function _applyRowFilters(")
        body = table[start:table.index("\n}", start)]
        assert "socialMode" not in body, "режим соцсетей не фильтрует готовую таблицу"
        assert "requiredSocials" not in body, "обязательные сети не фильтруют готовую таблицу"


class TestMapPanel:
    """Вкладка «На карте»: категории цветом, панель фильтров, читаемая метка.

    Раньше карта была одним прямоугольником: все компании одним цветом, а
    поиск и фильтры жили только в таблице. Теперь у вкладки есть панель слева,
    и это проверяется по разметке, а не по картинке: без id-шников сломается
    не отрисовка, а обработчики.
    """

    def _panel(self) -> str:
        return TEMPLATE[TEMPLATE.index('id="p-map"'):TEMPLATE.index('id="p-stats"')]

    def test_map_tab_has_a_side_panel_with_search(self):
        panel = self._panel()
        assert 'class="map-side"' in panel
        assert 'id="map-search"' in panel
        assert 'aria-label="Поиск по названию на карте"' in panel
        assert 'oninput="mapOnSearchInput(this)"' in panel
        assert 'id="map-shown"' in panel, "счётчик «показано из» нужен рядом с легендой"

    def test_map_filters_cover_reviews_site_and_new(self):
        panel = self._panel()
        assert 'id="map-reviews"' in panel
        assert 'id="map-site"' in panel
        # «Только новые» повторяет логику таблицы: серверный признак _is_new.
        assert 'id="map-only-new"' in panel
        assert 'value="without"' in panel and 'value="with"' in panel
        for step in ("5", "10", "50", "100"):
            assert f'<option value="{step}">' in panel, step

    def test_map_legend_is_a_list_of_toggle_buttons(self):
        panel = self._panel()
        assert 'id="map-cats"' in panel
        assert 'role="group" aria-label="Категории на карте"' in panel
        assert 'onclick="mapAllCats(true)"' in panel and 'onclick="mapAllCats(false)"' in panel
        # Легенда строится из данных: жёсткого списка категорий в шаблоне быть
        # не должно — категории приходят из файла.
        assert "<option value=\"Кафе\"" not in panel

    def test_category_toggle_is_a_pressed_button(self):
        js = APP_JS
        assert "function mapToggleCat(" in js
        assert "aria-pressed=\"${off ? 'false' : 'true'}\"" in js
        assert "mapToggleCat(this.dataset.cat)" in js, "цвет и подпись — из data-атрибутов"

    def test_map_filters_run_over_the_same_pure_rule(self):
        js = APP_JS
        assert "function mapRowVisible(r, opts)" in js
        assert "function mapVisibleRows(rows)" in js
        # Точки без координат на карту не попадают: иначе легенда обещает
        # больше, чем видно.
        assert "if (!r || !r.lat || !r.lon) return false;" in js

    def test_marker_and_legend_share_one_palette(self):
        js = APP_JS
        assert "const MAP_CAT_COLORS = [" in js
        assert ".map-cat-dot" in STYLE and "background:var(--cat,var(--c))" in STYLE
        assert "background:var(--pin,var(--c))" in STYLE, "метка красится тем же цветом"

    def test_popup_values_are_not_faded(self):
        # Раньше адрес и телефон были цветом --sub на белой подложке попапа и
        # почти не читались. Бледными остались только подписи полей.
        block = STYLE[STYLE.index(".map-pop-row{"):]
        block = block[:block.index("}")]
        assert "color:var(--txt)" in block
        key = STYLE[STYLE.index(".map-pop-key{"):]
        assert "color:var(--muted)" in key[:key.index("}")]

    def test_panel_keeps_the_12px_floor(self):
        block = STYLE[STYLE.index(".map-side{"):STYLE.index(".map-canvas{")]
        sizes = [float(m) for m in re.findall(r"font-size:(\d+(?:\.\d+)?)px", block)]
        assert sizes, "у панели есть текст"
        assert min(sizes) >= 12, f"мельче 12px: {sorted(sizes)}"

    def test_narrow_screen_moves_the_panel_below_the_map(self):
        block = STYLE[STYLE.index("@media (max-width:860px){"):]
        assert ".map-shell{flex-direction:column-reverse}" in block[:400]
        assert "max-height:52%" in block[:400]
