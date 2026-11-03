// UI unit tests for the log terminal + multi-city progress panel logic in
// static/js/app.js (run offline in Node against a DOM stub).
//
// Run with: node --test "tests/ui/logpanel.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readAppSrc } from './_src.mjs';
import { readCss } from './_css.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const src = readAppSrc(root);

// Slice a full function (balanced braces) from the production bundle.
function grab(name) {
  let i = src.indexOf('function ' + name + '(');
  assert.ok(i >= 0, 'function not found in app.js: ' + name);
  if (i >= 6 && src.slice(i - 6, i) === 'async ') i -= 6;   // async functions
  let depth = 0;
  const body = src.indexOf('{', i);
  for (let k = body; k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (!depth) return src.slice(i, k + 1); }
  }
  throw new Error('unbalanced braces while slicing: ' + name);
}

// ── Minimal DOM stub ──────────────────────────────────────────
function mkEl(id) {
  const classes = new Set();
  let html = '';
  const el = {
    id, value: '', textContent: '', hidden: true, style: {}, attrs: {},
    children: [], firstChild: null, scrollTop: 0, scrollHeight: 0,
    setAttribute(k, v) { el.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(el.attrs, k) ? el.attrs[k] : null; },
    classList: {
      add: (...c) => c.forEach(x => classes.add(x)),
      remove: (...c) => c.forEach(x => classes.delete(x)),
      toggle: (c, on) => { const want = on === undefined ? !classes.has(c) : !!on; want ? classes.add(c) : classes.delete(c); },
    },
    _classes: classes,
    appendChild(c) { el.children.push(c); el.firstChild = el.children[0]; },
    removeChild(c) {
      const i = el.children.indexOf(c);
      if (i >= 0) el.children.splice(i, 1);
      el.firstChild = el.children[0] || null;
    },
    remove() { /* stub: detach from parent — enough for appendLog paths */ },
    insertBefore(newEl, refEl) {
      const i = el.children.indexOf(refEl);
      if (i < 0) el.children.push(newEl);
      else el.children.splice(i, 0, newEl);
      return newEl;
    },
  };
  // innerHTML behaves like the real thing for the one case the code relies
  // on: assigning an empty string wipes the element's children (clearLog).
  Object.defineProperty(el, 'innerHTML', {
    get: () => html,
    set: v => { html = String(v); if (!html) { el.children = []; el.firstChild = null; } },
  });
  return el;
}

const els = {};
for (const id of ['log-output', 'log-ph', 'onboarding-screen', 'log-skeleton',
  'city-progress-list', 'city-progress', 'btn-tech-details', 'term-log-lbl',
  't-stats', 'run-hero', 'run-pct', 'run-fill', 'run-track', 'run-found',
  'run-city', 'run-city-pct', 'run-org', 'run-cities', 'run-eta', 'run-stage',
  'log-more', 'btn-log-more', 'log-more-menu',
  'log-jump', 'log-jump-n', 'log-filter-empty', 'log-err-count',
  'log-autoscroll', 'tab-log-dot']) {
  els[id] = mkEl(id);
}
// log-output starts with the onboarding card, like the real page.
els['log-output'].appendChild(els['onboarding-screen']);
els['onboarding-screen'].hidden = false;

let dynCount = 0;
const createdEls = [];   // createElement output is findable by getElementById, as in a real DOM
const _mkDoc = {
  getElementById: id => els[id] || createdEls.find(e => e.id === id) || null,
  createElement: () => { const e = mkEl('dyn-' + (++dynCount)); createdEls.push(e); return e; },
  title: '',
};
globalThis.document = _mkDoc;
globalThis.window = {};
globalThis.showToast = () => {};
globalThis.updateStatsBadge = () => {};
globalThis.refreshLiveStats = () => {};
globalThis.playCityDoneSound = () => {};
globalThis.renderDefaultStats = () => {};
globalThis.renderQuotaCard = () => {};
globalThis.notificationsEnabled = false;
globalThis.startTime = Date.now();
// Text helpers the sliced log functions call.
globalThis.escapeHtml = s => String(s ?? '');
globalThis.pluralRecords = n => 'записей';
globalThis.isRunActive = () => true;
// Module-level state the sliced functions close over — pre-seeded as globals.
globalThis._lastLogMsg = '';
globalThis.autoScrollEnabled = true;
globalThis._showTechDetails = false;
globalThis._cityProgressData = {};
globalThis._totalCities = 0;
globalThis._currentCityName = '';
// appendLog/toggleTechDetails close over the module-level logEl constant.
globalThis.logEl = els['log-output'];
// _trimLog closes over the module-level cap constant.
globalThis.MAX_LOG_LINES = 1200;

// ── Slice the functions under test ────────────────────────────
const fns = ['_trimLog', '_isDup', 'appendLog', 'toggleTechDetails', 'clearLog',
  // clearLog/appendLog синхронизируют кнопку «Как это работает»
  'cacheOnboardingHtml', 'onboardingIsOpen', 'syncOnboardingButton',
  'closeOnboardingHelp', 'toggleOnboardingHelp',
  'initCityProgress', 'updateCityProgress', 'renderCityProgress',
  'handleProgress', 'handleCityDone',
  'logStamp', '_elapsedStamp', '_logNorm', '_scrollLogIfFollowing', '_etaText',
  'setProgress', 'hideProgress', 'setRunFound', 'setRunEntity', 'setRunCityPct', 'setRunEta',
  '_runOverallFrac', 'updateRunCities',
  'toggleLogMenu', 'closeLogMenu',
  'setRunIndicator', 'renderLogStats',
  '_ls', '_logLevel', '_logIsNoise', '_logIsSummary', '_logIsCity', '_logIndent', '_onLogScroll',
  '_updateLogJump', 'logJumpToBottom', 'setLogFilter', '_refreshLogFilter',
  'toggleLogBlock', '_logPlainText', 'saveLogFile', 'copyLogText'];
// Constants the sliced functions close over: declared with `const` in app.js,
// so eval-based slicing has to bring them along.
function grabConst(name) {
  const i = src.indexOf('const ' + name + ' =');
  assert.ok(i >= 0, 'const not found in app.js: ' + name);
  return src.slice(i, src.indexOf(';', i) + 1);
}
(0, eval)(fns.map(grab).join('\n')
  + '\n' + ['LOG_NOISE_RE', 'LOG_KEEP_RE', 'LOG_SUMMARY_RE', 'LOG_CITY_RE', 'LOG_SUBLINE_RE', 'LOG_FILTERS',
    'UI_ICONS']
    .map(grabConst).join('\n'));
// _logIsSummary uses LOG_SUMMARY_RE and LOG_NOISE_RE.

const logEl = els['log-output'];
const visibleLines = () => logEl.children.filter(c => c.className !== undefined);

// Every log test starts from a clean panel: counters, folds and the stamp
// memory are module state inside app.js, not per-element state.
function resetLog() {
  logEl.children = [];
  logEl.firstChild = null;
  logEl._classes.clear();
  logEl.clientHeight = 0;
  globalThis._logState = null;
  globalThis._lastLogMsg = '';
  globalThis._showTechDetails = false;
  els['log-jump'].hidden = true;
  els['log-filter-empty'].hidden = true;
}

// ── 1. Duplicate suppression ─────────────────────────────────
test('appendLog drops a consecutive duplicate line', () => {
  logEl.children = [];
  globalThis._lastLogMsg = '';
  globalThis.appendLog('info', '🏙  Город 12/14: Душанбе');
  globalThis.appendLog('info', '🏙  Город 12/14: Душанбе');
  assert.equal(logEl.children.length, 1);
});

test('appendLog dedup is emoji/whitespace/case-insensitive', () => {
  logEl.children = [];
  globalThis._lastLogMsg = '';
  // Same line through different producers: city header vs summary — the
  // normalized comparison collapses them.
  globalThis.appendLog('info', '  Поиск: 1 город(ов), запросы: кафе');
  globalThis.appendLog('info', 'Поиск: 1 город(ов), запросы: кафе ');
  assert.equal(logEl.children.length, 1, 'variant whitespace still deduped');
  logEl.children = [];
  globalThis._lastLogMsg = '';
  globalThis.appendLog('info', '🏙 Город 1/2: Уфа');
  globalThis.appendLog('info', 'Город 1/2: Уфа');
  assert.equal(logEl.children.length, 1, 'emoji-only difference deduped');
});

test('appendLog keeps non-consecutive repeats (A B A)', () => {
  logEl.children = [];
  globalThis._lastLogMsg = '';
  globalThis.appendLog('info', 'a');
  globalThis.appendLog('info', 'b');
  globalThis.appendLog('info', 'a');
  assert.equal(logEl.children.length, 3);
});

test('appendLog drops duplicates of warn lines too', () => {
  logEl.children = [];
  globalThis._lastLogMsg = '';
  globalThis.appendLog('warn', '  [!] одинаковая ошибка');
  globalThis.appendLog('warn', '  [!] одинаковая ошибка');
  assert.equal(logEl.children.length, 1);
});

test('progress and result events are never deduped through appendLog', () => {
  // appendLog is only used for human levels; ensure repeated calls with
  // different content still land.
  logEl.children = [];
  globalThis._lastLogMsg = '';
  globalThis.appendLog('info', 'x');
  globalThis.appendLog('info', 'y');
  assert.equal(logEl.children.length, 2);
});

// ── 2. Tech-details toggle ───────────────────────────────────
// Developer traces are always STORED (hidden by CSS) — otherwise the
// «Технические» filter and the toggle could only reveal lines that happened
// to arrive while they were already on.
test('tech lines are stored but hidden until the toggle is on', () => {
  resetLog();
  globalThis._showTechDetails = false;
  globalThis.appendLog('tech', '2GIS API error: code=404 type=notFound');
  assert.equal(logEl.children.length, 1, 'tech line kept');
  assert.match(logEl.children[0].className, /tech/);
  assert.equal(logEl._classes.has('show-tech'), false, 'hidden by the container class');

  globalThis.toggleTechDetails();
  assert.equal(globalThis._showTechDetails, true);
  // Значок кнопки — инлайновый SVG: подпись читаем по тексту, состояние —
  // по классу .ico/иконке eyeOff из UI_ICONS.
  assert.match(els['btn-tech-details'].innerHTML, /Скрыть детали/);
  assert.match(els['btn-tech-details'].innerHTML, /#i-eye-off/);
  assert.equal(logEl._classes.has('show-tech'), true, 'now revealed');

  globalThis.toggleTechDetails();
  assert.equal(globalThis._showTechDetails, false);
  assert.match(els['btn-tech-details'].innerHTML, /Технические детали/);
  assert.doesNotMatch(els['btn-tech-details'].innerHTML, /Скрыть детали/);
  assert.equal(logEl._classes.has('show-tech'), false);
  assert.equal(globalThis._ls().stats.tech, 1, 'counted for the «Технические» filter');
});

// ── 3. clearLog resets the duplicate guard ───────────────────
test('clearLog resets the last-line memory', () => {
  globalThis._lastLogMsg = 'Старая строка';
  globalThis.clearLog();
  assert.equal(globalThis._lastLogMsg, '');
});

// ── 4. City progress panel ───────────────────────────────────
test('city_list event prefills queued cities with ⏸ and (ожидание)', () => {
  globalThis._cityProgressData = {};
  globalThis._totalCities = 0;
  els['city-progress'].children = [];
  els['city-progress-list'].innerHTML = '';
  globalThis.handleProgress('city_list|Ташкент/Санкт-Петербург');
  assert.equal(globalThis._totalCities, 2);
  const html = els['city-progress-list'].innerHTML;
  assert.match(html, /⏸/);
  assert.match(html, /\(ожидание\)/);
  assert.equal(els['run-cities'].textContent, '0 из 2 городов');
});

test('city transition marks the current city as running (⏳)', () => {
  // Real flow: city_list arrives before the first city transition.
  globalThis._cityProgressData = {};
  globalThis._totalCities = 0;
  logEl.children = [];
  globalThis._lastLogMsg = '';
  globalThis.handleProgress('city_list|Ташкент/Санкт-Петербург');
  globalThis.handleProgress('city/1/2/Ташкент');
  const html = els['city-progress-list'].innerHTML;
  assert.match(html, /⏳/);
  assert.match(html, /cp-running/);
});

test('progress ping updates % and shows found count in parentheses', () => {
  // _currentCityName was set to «Ташкент» by the previous transition.
  globalThis.handleProgress('45/100/кафе/37/0');
  const html = els['city-progress-list'].innerHTML;
  assert.match(html, /45%/);
  assert.match(html, /\(37 найд\.\)/);
  // Большой процент — общий по прогону: 45% первого из двух городов = 23%,
  // а собственный процент города стоит рядом с его названием.
  assert.equal(els['run-pct'].textContent, '23', 'общий процент по всем городам');
  assert.equal(els['run-city-pct'].textContent, '45', 'процент текущего города');
});

test('city_done marks ✓, 100% and updates the «обработано» counter', () => {
  globalThis.handleProgress('city_done|1|2|Ташкент|done|45');
  const html = els['city-progress-list'].innerHTML;
  assert.match(html, /✓/);
  assert.match(html, /100%/);
  assert.match(html, /\(45 найд\.\)/);
  assert.equal(els['run-cities'].textContent, '1 из 2 городов');
  assert.equal(els['run-pct'].textContent, '50', 'один город из двух = половина пути');
  assert.equal(els['run-city-pct'].textContent, '100');
  // Строка «Город … — завершён» больше не засоряет журнал: город и процент
  // уже видны в полосе поиска, а ниже идёт карточка статистики.
  assert.ok(!logEl.children.some(el => /завершён/.test(String(el.innerHTML || ''))),
    'журнал не повторяет «город завершён»');
});

test('queued city stays grey (cp-queued) while another is running', () => {
  const html = els['city-progress-list'].innerHTML;
  assert.match(html, /cp-queued/);        // Санкт-Петербург still queued
  assert.match(html, /Санкт-Петербург/);
});

test('a single-city run ends at 100%, not at zero', () => {
  globalThis._cityProgressData = {};
  globalThis._totalCities = 0;          // city_list приходит только при >1 города
  globalThis._currentCityName = 'Уфа';
  globalThis.handleProgress('city_done|1|1|Уфа|done|5');
  assert.equal(els['run-pct'].textContent, '100');
});

test('single-city runs keep the panel hidden', () => {
  els['city-progress'].style.display = '';
  globalThis.initCityProgress(1);
  assert.equal(els['city-progress'].style.display, 'none');
});

// ── 5. Elapsed stamps + autoscroll ───────────────────────────
test('every log line carries an absolute [HH:MM:SS] stamp (delta in title)', () => {
  logEl.children = [];
  globalThis._lastLogMsg = '';
  globalThis.startTime = Date.now();
  globalThis.appendLog('info', 'строка');
  // Absolute wall-clock time [HH:MM:SS], run-start delta moved to the title.
  // Second repeats are hidden by CSS («same»), the text is always rendered.
  assert.match(logEl.children[0].innerHTML, /class="ll-time(?: same)?">\d\d:\d\d:\d\d</);
  assert.match(logEl.children[0].title, /^\+\d+:\d\d$/, 'elapsed delta in hover title');
  // Elapsed helper: 90 seconds in → +1:30.
  globalThis.startTime = Date.now() - 90000;
  assert.equal(globalThis._elapsedStamp(), '+1:30');
  // Absolute stamp always matches HH:MM:SS.
  assert.match(globalThis.logStamp(), /^\d\d:\d\d:\d\d$/);
});

test('the log follows the tail by default and stops when the user scrolls up', () => {
  resetLog();
  logEl.scrollTop = 0;
  logEl.scrollHeight = 500;
  globalThis.appendLog('info', 'первая строка');
  assert.equal(logEl.scrollTop, 500, 'sticks to the tail by default');

  // The reader scrolls up: 400px away from the tail on a 100px-high viewport.
  logEl.clientHeight = 100;
  logEl.scrollTop = 0;
  globalThis._onLogScroll();
  assert.equal(globalThis._ls().follow, false, 'autoscroll released');

  globalThis.appendLog('info', 'вторая строка');
  assert.equal(logEl.scrollTop, 0, 'a scrolled-up reader is not yanked to the tail');
  assert.equal(els['log-jump'].hidden, false, 'the «К последней строке» button appears');
  assert.equal(els['log-jump-n'].textContent, '1', 'and counts what is waiting');

  globalThis.logJumpToBottom();
  assert.equal(els['log-jump'].hidden, true);
  assert.equal(globalThis._ls().follow, true);
  assert.equal(globalThis._ls().below, 0);
});

test('app.js has no leftover autoscroll switch wiring', () => {
  assert.ok(!/autoScrollEnabled/.test(src), 'autoScrollEnabled global is gone');
  assert.ok(!/getElementById\(['"]autoscroll['"]\)/.test(src), 'no autoscroll checkbox lookup left');
  assert.ok(!/Здесь появится ход поиска/.test(src), 'the old placeholder caption is gone');
});

// ── 6. Aggregate progress in the single top strip ─────────────
test('city counter counts finished cities and names the total', () => {
  globalThis._cityProgressData = {
    'Ташкент': {pct: 100, found: 45, status: 'done'},
    'Санкт-Петербург': {pct: 50, found: 10, status: 'running'},
  };
  globalThis._totalCities = 2;
  globalThis.updateRunCities();
  assert.equal(els['run-cities'].textContent, '1 из 2 городов');
  // 1 finished city + the running one at 50% of 2 cities = 75%.
  assert.equal(globalThis._runOverallFrac(), 0.75);

  globalThis._totalCities = 1;
  globalThis.updateRunCities();
  assert.equal(els['run-cities'].textContent, '1 из 1 города');
});

// ── 7. Run indicator on the «Ход поиска» tab ─────────────────
test('tab dot follows the run lifecycle', () => {
  globalThis.setRunIndicator(true);
  assert.equal(els['tab-log-dot'].hidden, false);
  globalThis.setRunIndicator(false);
  assert.equal(els['tab-log-dot'].hidden, true);
});

// ── 8. Structured stats card ─────────────────────────────────
test('renderLogStats draws rows with bars instead of ASCII art', () => {
  logEl.children = [];
  globalThis.renderLogStats(JSON.stringify({
    total: 50,
    by_social: [{label: 'ВКонтакте', count: 37}, {label: 'Telegram', count: 30}],
    by_query: [],
    top_categories: [{label: 'кафе', count: 9}],
  }));
  assert.equal(logEl.children.length, 1);
  assert.equal(logEl.children[0].className, 'log-stats');
  const html = logEl.children[0].innerHTML;
  assert.match(html, /ВКонтакте/);
  assert.match(html, /width:100%/, 'longest bar is full width');
  assert.match(html, /Топ категорий/);

  // A broken payload must never paint an empty card.
  logEl.children = [];
  globalThis.renderLogStats('{not json');
  assert.equal(logEl.children.length, 0);
});

test('the stats card names the city it was built for', () => {
  logEl.children = [];
  globalThis.renderLogStats(JSON.stringify({
    total: 99, city: 'Душанбе',
    by_social: [], by_query: [], top_categories: [],
  }));
  assert.match(logEl.children[0].innerHTML, /📊 Статистика — Душанбе/);

  // Без города заголовок остаётся прежним — никакого висящего тире.
  logEl.children = [];
  globalThis.renderLogStats(JSON.stringify({total: 2, by_social: [], by_query: [], top_categories: []}));
  assert.match(logEl.children[0].innerHTML, /📊 Статистика <span>/);
});

// ── 9. Level colours ─────────────────────────────────────────
test('every level gets its own colour class', () => {
  resetLog();
  globalThis.appendLog('ok', '  ✅ Сохранено');
  globalThis.appendLog('warn', '  ⚠ Предупреждение');
  globalThis.appendLog('error', '  [✖] Не найдено');
  globalThis.appendLog('info', '  📡 Ищу');
  const cls = logEl.children.map(c => c.className);
  assert.match(cls[0], /\bok\b/);
  assert.match(cls[1], /\bwarn\b/);
  assert.match(cls[2], /\berror\b/);
  assert.match(cls[3], /\binfo\b/);
});

test('a warn-level line marked [!] is painted as an error', () => {
  resetLog();
  globalThis.appendLog('warn', '  [!] Ошибка записи Excel');
  assert.match(logEl.children[0].className, /\berror\b/);
  assert.equal(globalThis._ls().stats.err, 1);
});

// ── 10. Filters ──────────────────────────────────────────────
test('filters are one class on the container, with an empty verdict', () => {
  resetLog();
  globalThis.appendLog('info', '  📡 Ищу кафе');
  globalThis.setLogFilter('errors');
  assert.equal(globalThis._ls().filter, 'errors');
  assert.equal(logEl._classes.has('f-errors'), true);
  assert.equal(els['log-filter-empty'].hidden, false);
  assert.equal(els['log-filter-empty'].textContent, '✅ Ошибок нет');

  globalThis.appendLog('warn', '  [✖] Сломалось');
  assert.equal(els['log-filter-empty'].hidden, true, 'a warning fills the errors filter');
  assert.equal(els['log-err-count'].textContent, '1');
  assert.equal(els['log-err-count'].hidden, false);

  globalThis.setLogFilter('all');
  assert.equal(logEl._classes.has('f-all'), true);
  assert.equal(logEl._classes.has('f-errors'), false, 'only one filter class at a time');
});

// The «Важные» filter owns the WHOLE technical stream: geocoding, raw
// coordinates, per-query banners, page/point counters, HTTP statuses and
// client traces. Results and statuses stay readable in both filters.
test('«Важные» hides every technical line and keeps the results', () => {
  const noise = [
    '  Геокодирую «Москва»…',
    '  → 61.24178, 73.39383',
    '  ─── Запрос «кафе»: начало поиска',
    '  🔍 Поиск: «кафе» в Москва…',
    '  page 2/5',
    '  HTTP 200',
    '  point 3/12',
    '  Checkpoint: 40 ранее найденных, 3 точек уже обработано.',
    '  browser_client: cache initialized, 12 entries',
  ];
  const keep = [
    '  🏙  Город 1/2: Москва',
    '  🔍 Поиск в «Москва» — запросы: кафе',
    '  🗺  Источник: 2GIS (официальный API — соцсети и сайты уже в ответе)',
    '  🗺  Источник: Яндекс.Карты',
    '  ✅ «кафе»: 50 записей',
    '  📦 Raw: 50 организаций (без фильтров) → output/raw/',
    '  🎯 Processed: 44 организаций → 2 файлов в output/processed/',
    '  💾 Карта: готово → output/map.html',
    '  [!] Не удалось загрузить детали — пропускаю организацию',
  ];
  resetLog();
  noise.forEach(t => globalThis.appendLog('info', t));
  keep.forEach(t => globalThis.appendLog('info', t));
  assert.equal(globalThis._ls().stats.noise, noise.length,
    'each technical line is classified as noise');
  noise.forEach((t, i) => assert.match(logEl.children[i].className, /\bnoise\b/, 'noise: ' + t));
  keep.forEach((t, i) =>
    assert.ok(!/\bnoise\b/.test(logEl.children[noise.length + i].className), 'kept: ' + t));
});

test('«Технические»/«Все» still show the mechanics «Важные» hides', () => {
  resetLog();
  globalThis.appendLog('info', '  → 61.24178, 73.39383');
  globalThis.appendLog('info', '  🏙  Город 1/1: Уфа');
  globalThis.setLogFilter('tech');
  // The line stays in the DOM (CSS decides visibility), it is only tagged.
  assert.equal(logEl.children.length, 2);
  assert.match(logEl.children[0].className, /\bnoise\b/);
  globalThis.setLogFilter('all');
  assert.equal(logEl._classes.has('f-all'), true);
});

test('«Важные» shows ONLY the summary lines, not the whole log', () => {
  resetLog();
  globalThis.appendLog('info', '  📡 Геокодирую «Ленина 1»');
  globalThis.appendLog('info', '  [!] Сеть: RemoteProtocolError — повтор 1/2');
  globalThis.appendLog('info', '  🏙  Город 1/1: Уфа');
  globalThis.appendLog('info', '  ✅ «кафе»: 138 записей');
  globalThis.appendLog('info', '  📦 Raw: 138 организаций (без фильтров) → output/raw/');
  globalThis.setLogFilter('important');
  // Механика и город — не итоги; ошибка живёт во вкладке «Ошибки».
  assert.match(logEl.children[0].className, /\bnoise\b/);
  assert.ok(!/\bsum\b/.test(logEl.children[1].className), 'errors are not summary');
  assert.ok(!/\bsum\b/.test(logEl.children[2].className), 'city header is not summary');
  assert.match(logEl.children[3].className, /\bsum\b/);
  assert.match(logEl.children[4].className, /\bsum\b/);
  assert.equal(globalThis._ls().stats.sum, 2);
  // Есть итоги → плашка пустоты скрыта; пустой вердикт считается по итоговым
  // строкам, а не по «всему, что не шум».
  assert.equal(els['log-filter-empty'].hidden, true, 'summaries fill the tab');
  resetLog();
  globalThis.appendLog('info', '  📡 Геокодирую «Ленина 1»');
  globalThis.setLogFilter('important');
  assert.equal(els['log-filter-empty'].hidden, false, 'no summaries → empty verdict');
  assert.equal(els['log-filter-empty'].textContent, 'Итогов пока нет — включите «Все»');

  // warn-строки с итоговым эмодзи (пауза/стоп) остаются итогами.
  resetLog();
  globalThis.appendLog('warn', '  ⏸ Поиск на паузе — прогресс сохранён.');
  assert.match(logEl.children[0].className, /\bsum\b/);
  assert.equal(globalThis._ls().stats.sum, 1);

  globalThis.setLogFilter('tech');
  globalThis.appendLog('tech', 'http_client: GET 429');
  assert.equal(els['log-filter-empty'].hidden, true);
  assert.equal(globalThis._ls().stats.tech, 1);
});

// ── 11. City folds + hierarchy ───────────────────────────────
test('city headers open a fold and later lines can be collapsed', () => {
  resetLog();
  globalThis.appendLog('info', '  🏙  Город 1/2: Уфа');
  globalThis.appendLog('info', '  📡 Ищу кафе');
  const hdr = logEl.children[0];
  assert.match(hdr.className, /\bcity\b/);
  assert.equal(typeof hdr.onclick, 'function', 'the header is clickable');

  hdr.onclick();
  assert.equal(globalThis._ls().collapsed[0], true);
  assert.equal(hdr._classes.has('collapsed'), true);
  assert.equal(logEl.children[1].style.display, 'none');

  hdr.onclick();
  assert.equal(logEl.children[1].style.display, '', 'unfolded again');

  hdr.onclick();
  globalThis.appendLog('info', '  📡 Строка при свёрнутом блоке');
  assert.equal(logEl.children[2].style.display, 'none', 'a folded block stays folded');
});

test('indented sub-lines get the hierarchy class', () => {
  resetLog();
  globalThis.appendLog('info', '  queries=[\'кафе\']');
  globalThis.appendLog('info', '  📡 Ищу кафе');
  assert.match(logEl.children[0].className, /\bind-1\b/);
  assert.ok(!/\bind-1\b/.test(logEl.children[1].className));
});

// ── 12. Timestamps ───────────────────────────────────────────
test('the stamp column is dimmed when the second has not changed', () => {
  resetLog();
  globalThis.appendLog('info', 'a');
  globalThis.appendLog('info', 'b');
  const first = />(\d\d:\d\d:\d\d)</.exec(logEl.children[0].innerHTML);
  assert.ok(first, 'the first line always carries a time');
  const second = logEl.children[1].innerHTML;
  const m = />(\d\d:\d\d:\d\d)</.exec(second);
  if (m && m[1] === first[1]) assert.match(second, /ll-time same/, 'repeated second is dimmed');
  else assert.match(second, /ll-time"/, 'a new second is printed');
});

// ── 13. Save / copy the whole log ────────────────────────────
test('_logPlainText writes one stamped line per log row', () => {
  resetLog();
  globalThis.appendLog('info', 'первая');
  globalThis.appendLog('ok', '  ✅ вторая');
  const lines = globalThis._logPlainText().split('\n');
  assert.equal(lines.length, 2, 'the cards and placeholders are not lines');
  assert.match(lines[0], /^\[\d\d:\d\d:\d\d\] первая$/);
  assert.match(lines[1], /вторая$/);

  // A cleared log saves nothing — the buttons must not write an empty file.
  globalThis.clearLog();
  assert.equal(globalThis._logPlainText(), '');
});

// ── 14. One progress strip: percent + city + last organization ──
test('the hero shows the percent, the city and the last found organization', () => {
  globalThis.setProgress(37, '«кафе»');
  assert.equal(els['run-hero']._classes.has('is-hidden'), false);
  assert.equal(els['run-pct'].textContent, '37');
  assert.equal(els['run-fill'].style.width, '37%');
  assert.equal(els['run-track'].getAttribute('aria-valuenow'), '37');
  assert.equal(els['run-stage'].textContent, '«кафе»');

  globalThis.setRunEntity('Санкт-Петербург', 'Кофейня «Ветер»');
  assert.equal(els['run-city'].textContent, 'Санкт-Петербург');
  assert.equal(els['run-org'].textContent, 'Кофейня «Ветер»');

  globalThis.setRunCityPct(64);
  assert.equal(els['run-city-pct'].textContent, '64', 'процент города — рядом с городом');

  globalThis.hideProgress();
  assert.equal(els['run-hero']._classes.has('is-hidden'), true, 'run over → strip hidden');
});

test('the log toolbar menu opens, closes and reports its state', () => {
  els['log-more-menu'].hidden = true;
  globalThis.toggleLogMenu();
  assert.equal(els['log-more-menu'].hidden, false);
  assert.equal(els['btn-log-more'].getAttribute('aria-expanded'), 'true');
  globalThis.closeLogMenu();
  assert.equal(els['log-more-menu'].hidden, true);
  assert.equal(els['btn-log-more'].getAttribute('aria-expanded'), 'false');
});

test('the log panel never repeats the city list (top strip owns it)', () => {
  const tpl = readFileSync(join(root, 'templates', 'index.html'), 'utf8');
  assert.ok(!/id="tp-cities"/.test(tpl), 'tp-cities markup is gone');
  assert.ok(!/tp-chip/.test(src), 'per-city chips are not rendered any more');
  const css = readCss(root);
  assert.ok(!/\.tp-chip/.test(css), 'chip styles are gone too');
  // …while the top strip caps its height and scrolls instead of growing.
  assert.match(css, /#city-progress-list\{[^}]*max-height/);
  assert.match(css, /#city-progress-list\{[^}]*overflow-y:auto/);
});
