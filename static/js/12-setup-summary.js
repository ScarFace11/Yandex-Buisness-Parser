// ═══════════════════════════════════════════
//  Живая сводка настройки (верх сайдбара)
//
//  Сайдбар — длинная форма из пяти аккордеонов, и «что именно я запущу»
//  приходилось собирать глазами по всей панели. Сводка показывает главное
//  (запрос, город, тип, соцсети, форматы) без раскрытия разделов, а каждый
//  чип — кнопка: открывает раздел, которому принадлежит значение.
//
//  Значение пересобирается по факту изменения формы (делегированные
//  input/change/click), а «оживление» — короткая пульсация только у тех
//  чипов, текст которых изменился: перерисовка всей строки не должна
//  дёргать всю сводку.
// ═══════════════════════════════════════════

// Куда ведёт чип: раздел аккордеона, к которому относится значение.
const SETUP_SUM_TARGETS = {
  queries: 'acc-basic',
  cities:  'acc-basic',
  volume:  'acc-tech',
  type:    'acc-filters',
  socials: 'acc-filters',
  formats: 'acc-formats',
};

function _setupQueries() {
  return (document.getElementById('f-queries')?.value || '')
    .split('\n').map(s => s.trim()).filter(Boolean);
}

function _setupCities() {
  try { return [...selectedCities]; } catch { return []; }
}

function _setupFormats() {
  const names = { 'f-excel': 'Excel', 'f-json': 'JSON', 'f-csv': 'CSV', 'f-map': 'Карта' };
  const on = Object.entries(names)
    .filter(([id]) => document.getElementById(id)?.checked)
    .map(([, label]) => label);
  return on;
}

// Оценка объёма прогона ДО запуска. Считает searchVolumeEstimate (js/01):
// одна модель на карточки объёма и на сводку, иначе числа расходятся.
function setupVolumeEstimate() {
  const v = searchVolumeEstimate();
  return {
    cells: v.cells, cities: v.cities, queries: v.queries, pages: v.pages,
    searchPages: v.searchPages, maxCandidates: v.cap,
    cards: v.total, capped: v.capped,
  };
}

// Компактное число для чипа: «1 200» / «12 тыс.» — широкие числа не должны
// растягивать чип (в колонке 300px место ограничено).
function _setupNum(n) {
  return n >= 10000 ? Math.round(n / 1000) + ' тыс.' : n.toLocaleString('ru-RU');
}

// Русское склонение: «1 страница», «2 страницы», «5 страниц».
// Подсказка собирается из чисел, поэтому подставить слово на месте нельзя —
// иначе в интерфейсе появлялось бы «2 страниц выдачи».
function _setupPlural(n, one, few, many) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return few;
  return many;
}

// Текст и состояние каждого чипа. Помимо значения несёт `tone`:
// 'warn' — не хватает данных для запуска, 'ok' — всё на месте.
function buildSetupSummary() {
  const queries = _setupQueries();
  const cities = _setupCities();
  const formats = _setupFormats();

  const queriesText = queries.length
    ? (queries.length === 1 ? queries[0] : `${queries[0]} +${queries.length - 1}`)
    : 'не задано';

  const citiesText = cities.length
    ? (cities.length <= 2 ? cities.join(', ')
        : `${cities.slice(0, 2).join(', ')} +${cities.length - 2}`)
    : 'не выбрано';

  const parseLabel = parseMode === 'all' ? 'все организации' : 'только без сайтов';
  const socialLabel = socialMode === 'with_socials' ? 'только с соцсетями'
    : socialMode === 'without_socials' ? 'без соцсетей' : 'все соцсети';

  // «Объём» — не отдельная настройка, а следствие всего выше: города,
  // запросы, страницы и покрытие города. Пока их нет, считать нечего.
  const vol = setupVolumeEstimate();
  const volumeKnown = vol.cities > 0 && vol.queries > 0;
  const volumeDetail = volumeKnown
    ? `Точек поиска на город: ${vol.cells} · Городов: ${vol.cities} · Запросов: ${vol.queries}`
      + ` · Страниц на точку: ${vol.pages} → ${_setupNum(vol.searchPages)}`
      + ` ${_setupPlural(vol.searchPages, 'страница', 'страницы', 'страниц')} выдачи,`
      + ` до ${CARDS_PER_PAGE} организаций со страницы.`
      + (vol.capped
          ? ` Потолок «Макс. организаций» (${_setupNum(vol.maxCandidates)}) сработает раньше.`
          : '')
    : 'Выберите город и запрос — посчитаю объём прогона';

  return [
    { key: 'queries', label: 'Кого ищем', value: queriesText, tone: queries.length ? 'ok' : 'warn' },
    { key: 'cities',  label: 'Города',    value: citiesText,  tone: cities.length ? 'ok' : 'warn' },
    { key: 'volume',  label: 'Объём',
      value: volumeKnown
        ? `до ${_setupNum(vol.cards)}`
          + ` ${_setupPlural(vol.cards, 'организация', 'организации', 'организаций')}`
          + ` · ${_setupNum(vol.searchPages)} стр.`
        : '—',
      tone: 'ok', detail: volumeDetail },
    { key: 'type',    label: 'Организации', value: parseLabel, tone: 'ok' },
    { key: 'socials', label: 'Соцсети',   value: socialLabel, tone: 'ok' },
    { key: 'formats', label: 'Файлы',     value: formats.length ? formats.join(', ') : 'не выбрано',
      tone: formats.length ? 'ok' : 'warn' },
  ];
}

let _setupSumShown = {};   // key → последний показанный текст (для пульсации)

function renderSetupSummary() {
  const host = document.getElementById('setup-summary');
  if (!host) return;
  const items = buildSetupSummary();
  // Значение и подсказка сами заканчиваются точкой («…132 стр.», «…сработает
  // раньше.»): вторая точка в конце фразы читалась бы как опечатка в
  // подсказке и в озвучке скринридером.
  const sentence = t => String(t || '').replace(/\.+$/, '');
  host.innerHTML = items.map(it => {
    const missing = it.tone === 'warn';
    return `<button type="button" class="setup-chip${missing ? ' is-missing' : ''}"`
      + ` data-setup-jump="${SETUP_SUM_TARGETS[it.key] || ''}"`
      + ` data-setup-key="${it.key}"`
      + ` title="${it.detail
          ? escapeHtml(sentence(it.detail)) + ' — открыть раздел'
          : (missing ? 'Нужно заполнить — откройте раздел' : 'Открыть раздел с этой настройкой')}"`
      + ` aria-label="${escapeHtml(it.label)}: ${escapeHtml(sentence(it.value))}.`
      + `${it.detail ? ' ' + escapeHtml(sentence(it.detail)) + '.' : ''} Открыть раздел">`
      + `<span class="setup-chip-lbl">${escapeHtml(it.label)}</span>`
      + `<span class="setup-chip-val">${escapeHtml(it.value)}</span>`
      + `</button>`;
  }).join('');

  // Пульсация только у изменившихся значений: иначе каждое нажатие клавиши
  // «оживляло» бы всю строку и сводка читалась бы как ошибка загрузки.
  host.querySelectorAll('.setup-chip').forEach(chip => {
    const key = chip.dataset.setupKey;
    const val = chip.querySelector('.setup-chip-val')?.textContent || '';
    if (_setupSumShown[key] !== undefined && _setupSumShown[key] !== val) {
      chip.classList.add('bump');
      chip.addEventListener('animationend', () => chip.classList.remove('bump'), { once: true });
    }
    _setupSumShown[key] = val;
  });
}

// Чип открывает свой раздел и ставит фокус на первое поле в нём — это быстрее,
// чем прокрутка формы руками.
function _setupJump(target, key) {
  const sec = document.getElementById(target);
  if (!sec) return;
  // Разделы, уехавшие в окно «Ещё настройки», сначала открывают его на нужной
  // вкладке: иначе чип уводил фокус в невидимую секцию и выглядел сломанным.
  // Карта внутри функции — её одну и выдёргивают тесты.
  const tab = { 'acc-parse': 'data', 'acc-tech': 'data',
                'acc-filters': 'filters', 'acc-formats': 'files' }[target];
  if (tab && typeof openMoreSettings === 'function') openMoreSettings(tab);
  if (!sec.classList.contains('open')) {
    const hdr = sec.querySelector('.acc-hdr');
    if (hdr) toggleAccordion(hdr);
  }
  sec.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  const focusIds = {
    queries: 'f-queries', cities: 'f-city-input', type: 'acc-filters',
    socials: 'acc-filters', formats: 'f-excel',
  };
  const el = document.getElementById(focusIds[key] || '') ||
    sec.querySelector('input:not([type=hidden]), textarea, select, button');
  if (el && typeof el.focus === 'function') el.focus({ preventScroll: true });
}

(function initSetupSummary() {
  const host = document.getElementById('setup-summary');
  if (!host) return;

  host.addEventListener('click', e => {
    const chip = e.target.closest('.setup-chip');
    if (!chip) return;
    _setupJump(chip.dataset.setupJump, chip.dataset.setupKey);
  });

  // Один делегированный слушатель на всю боковую панель: значения меняются в
  // десятках мест (город добавляется кликом, формат — чекбоксом, пресет —
  // одной кнопкой), а свой обработчик в каждый из них — это десяток правок.
  let pending = false;
  const schedule = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; renderSetupSummary(); });
  };
  document.addEventListener('input', schedule, true);
  document.addEventListener('change', schedule, true);
  document.addEventListener('click', schedule, true);
  schedule();
})();
