// UI unit tests: шаги «Как это работает» — static/js/09-ui-extras.js.
//
// Три шага на пустом экране раньше были картинками с тенью при наведении:
// клик по ним ничего не делал. Теперь каждый делает то, о чём говорит —
// ведёт к полю, запускает поиск, открывает результаты, — а если запустить
// пока нельзя, объясняет, чего не хватает.
//
// Run with: node --test "tests/ui/onboarding.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readAppSrc } from './_src.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const src = readAppSrc(root);

function grab(name) {
  const i = src.indexOf('function ' + name + '(');
  assert.ok(i >= 0, 'function not found in app.js: ' + name);
  let depth = 0;
  const body = src.indexOf('{', i);
  for (let k = body; k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (!depth) return src.slice(i, k + 1); }
  }
  throw new Error('unbalanced braces while slicing: ' + name);
}

function mkEl(id) {
  const classes = new Set();
  return {
    id, value: '', _focused: false, _clicked: 0, _scrolled: false,
    _attrs: {}, children: [], _removed: false, innerHTML: '',
    set className(v) { classes.clear(); String(v).split(/\s+/).filter(Boolean).forEach(c => classes.add(c)); },
    get className() { return [...classes].join(' '); },
    classList: {
      add: (...c) => c.forEach(x => classes.add(x)),
      remove: (...c) => c.forEach(x => classes.delete(x)),
      toggle: (c, on) => { const w = on === undefined ? !classes.has(c) : !!on; w ? classes.add(c) : classes.delete(c); },
      contains: c => classes.has(c),
    },
    _classes: classes,
    setAttribute(k, v) { this._attrs[k] = String(v); },
    getAttribute(k) { return this._attrs[k]; },
    removeAttribute(k) { delete this._attrs[k]; },
    appendChild(c) { this.children.push(c); return c; },
    remove() { this._removed = true; if (this.id) delete els[this.id]; },
    querySelector: () => null,
    scrollIntoView() { this._scrolled = true; },
    focus() { this._focused = true; },
    click() { this._clicked++; },
  };
}

const els = {
  'f-queries': mkEl('f-queries'),
  'f-city-input': mkEl('f-city-input'),
  'btn-run': mkEl('btn-run'),
  'acc-basic': mkEl('acc-basic'),
  'btn-log-howto': mkEl('btn-log-howto'),
};
els['btn-log-howto'].setAttribute('aria-expanded', 'true');
els['f-queries'].value = 'кафе';

globalThis.document = {
  getElementById: id => els[id] ?? null,
  querySelectorAll: () => [],
  addEventListener: () => {},
  createElement: () => mkEl(''),
};
globalThis.setTimeout = fn => { fn(); return 0; };
globalThis.showToast = (msg, type) => { globalThis.__toasts.push([msg, type]); };
globalThis.isRunActive = () => globalThis.__runActive;
globalThis.allResults = [];
globalThis.toggleAccordion = () => { globalThis.__accordionToggled = true; };
globalThis.showTab = name => { globalThis.__tab = name; };

(0, eval)(src.match(/let _onboardingHtml = '';/)[0] + '\n'
  + grab('_onboardingFocus') + '\n' + grab('_onboardingOpenBasic')
  + '\n' + grab('onboardingStep') + '\n' + grab('onboardingKeyword')
  + '\n' + grab('cacheOnboardingHtml') + '\n' + grab('onboardingIsOpen')
  + '\n' + grab('toggleOnboardingHelp')
  + '\n' + grab('closeOnboardingHelp') + '\n' + grab('syncOnboardingButton'));

function reset({ queries = 'кафе', cities = [], runActive = false, results = [] } = {}) {
  els['f-queries'].value = queries;
  els['f-queries']._focused = false;
  els['f-city-input']._focused = false;
  els['btn-run']._clicked = 0;
  els['acc-basic']._classes.clear();
  els['acc-basic']._classes.add('open');
  els['acc-basic'].querySelector = () => null;
  globalThis.__toasts = [];
  globalThis.__runActive = runActive;
  globalThis.__tab = null;
  globalThis.__accordionToggled = false;
  globalThis.selectedCities = cities;
  globalThis.allResults = results;
}

// ── Шаг 01: ведёт к незаполненному полю ───────────────────────
test('шаг 1 ставит курсор в пустое поле запроса', () => {
  reset({ queries: '' });
  globalThis.onboardingStep(1);
  assert.equal(els['f-queries']._focused, true);
  assert.equal(els['f-city-input']._focused, false);
});

test('шаг 1 при заполненном запросе ведёт к городу', () => {
  reset({ queries: 'кафе' });
  globalThis.onboardingStep(1);
  assert.equal(els['f-city-input']._focused, true);
});

test('шаг 1 раскрывает свёрнутый раздел «Основные параметры»', () => {
  reset({ queries: 'кафе' });
  els['acc-basic']._classes.clear();                 // раздел свёрнут
  els['acc-basic'].querySelector = () => ({});
  globalThis.onboardingStep(1);
  assert.equal(globalThis.__accordionToggled, true, 'свёрнутый раздел не раскрылся');
});

// ── Шаг 02: запускает поиск или объясняет, чего не хватает ────
test('шаг 2 без запроса объясняет и ведёт к запросу', () => {
  reset({ queries: '' });
  globalThis.onboardingStep(2);
  assert.equal(els['btn-run']._clicked, 0, 'без запроса запускать нечего');
  assert.equal(globalThis.__toasts.length, 1);
  assert.equal(globalThis.__toasts[0][1], 'error');
  assert.match(globalThis.__toasts[0][0], /кого искать/i);
  assert.equal(els['f-queries']._focused, true);
});

test('шаг 2 без города объясняет и ведёт к выбору города', () => {
  reset({ queries: 'кафе', cities: [] });
  globalThis.onboardingStep(2);
  assert.equal(els['btn-run']._clicked, 0);
  assert.match(globalThis.__toasts[0][0], /город/i);
  assert.equal(els['f-city-input']._focused, true);
});

test('шаг 2 с готовыми данными нажимает «Найти компании»', () => {
  reset({ queries: 'кафе', cities: ['Уфа'] });
  globalThis.onboardingStep(2);
  assert.equal(els['btn-run']._clicked, 1);
  assert.equal(globalThis.__toasts.length, 0, 'нечего объяснять — всё заполнено');
});

test('шаг 2 во время прогона не запускает второй поиск', () => {
  reset({ queries: 'кафе', cities: ['Уфа'], runActive: true });
  globalThis.onboardingStep(2);
  assert.equal(els['btn-run']._clicked, 0);
  assert.match(globalThis.__toasts[0][0], /уже идёт/i);
});

// ── Шаг 03: открывает результаты ──────────────────────────────
test('шаг 3 открывает таблицу и говорит, если пока пусто', () => {
  reset({ results: [] });
  globalThis.onboardingStep(3);
  assert.equal(globalThis.__tab, 'table');
  assert.equal(globalThis.__toasts.length, 1);
  assert.match(globalThis.__toasts[0][0], /пусто/i);

  reset({ results: [{ name: 'А' }] });
  globalThis.onboardingStep(3);
  assert.equal(globalThis.__tab, 'table');
  assert.equal(globalThis.__toasts.length, 0, 'есть записи — подсказка не нужна');
});

// ── Ключевые слова ведут именно туда, куда обещают ────────────
test('слово «запрос» ведёт к полю запроса даже при заполненном городе', () => {
  reset({ queries: 'кафе' });
  globalThis.onboardingKeyword('queries');
  assert.equal(els['f-queries']._focused, true);
  assert.equal(els['f-city-input']._focused, false);
});

test('слово «город» ведёт к полю города', () => {
  reset({ queries: 'кафе' });
  globalThis.onboardingKeyword('city');
  assert.equal(els['f-city-input']._focused, true);
  assert.equal(els['f-queries']._focused, false);
});

test('слово «Найти компании» запускает тот же поиск', () => {
  reset({ queries: 'кафе', cities: ['Уфа'] });
  globalThis.onboardingKeyword('run');
  assert.equal(els['btn-run']._clicked, 1);
});

test('слово «сообщение» открывает шаблоны и подсказывает кнопку', () => {
  reset();
  globalThis.onboardingKeyword('messages');
  assert.equal(globalThis.__tab, 'templates');
  assert.equal(globalThis.__toasts.length, 1);
  assert.match(globalThis.__toasts[0][0], /Копировать/);
  assert.equal(globalThis.__toasts[0][1], 'info');
});

// ── «Как это работает» после старта: кнопка в журнале ─────────
test('на пустом экране кнопка ведёт к уже открытой инструкции', () => {
  const screen = mkEl('onboarding-screen');
  els['onboarding-screen'] = screen;
  globalThis.__helpInserted = null;
  globalThis.toggleOnboardingHelp();
  assert.equal(screen._scrolled, true);
  assert.equal(globalThis.__helpInserted, null, 'второй экземпляр не нужен');
  delete els['onboarding-screen'];
});

test('после старта поиска инструкция открывается над логом и закрывается', () => {
  const screen = mkEl('onboarding-screen');
  screen.innerHTML = '<div class="onboarding-inner">шаги</div>';
  els['onboarding-screen'] = screen;
  globalThis.cacheOnboardingHtml();
  delete els['onboarding-screen'];       // первая строка лога убрала первый экран

  const log = mkEl('log-output');
  log.parentElement = {
    insertBefore(el, before) {
      globalThis.__helpInserted = el;
      els[el.id] = el;
      assert.equal(before, log, 'подсказка встаёт перед журналом');
    },
  };
  els['log-output'] = log;

  globalThis.toggleOnboardingHelp();
  const help = globalThis.__helpInserted;
  assert.ok(help, 'карточка не появилась');
  assert.equal(help.id, 'onboarding-help');
  assert.equal(help.className, 'onboarding');
  assert.equal(help.innerHTML, '<div class="onboarding-inner">шаги</div>');
  assert.equal(help.getAttribute('role'), 'region');
  assert.equal(help.children.length, 1, 'у карточки есть крестик');
  assert.equal(help.children[0].className, 'onb-close');
  assert.equal(els['btn-log-howto'].getAttribute('aria-expanded'), 'true');

  globalThis.toggleOnboardingHelp();
  assert.equal(help._removed, true);
  assert.equal(els['btn-log-howto'].getAttribute('aria-expanded'), 'false');
  delete els['log-output'];
});
