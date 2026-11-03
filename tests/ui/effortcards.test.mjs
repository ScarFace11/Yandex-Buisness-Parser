// UI unit tests: карточки объёма — удаление с отменой и серверное хранилище.
//
// Карточки — данные, поэтому важны две вещи, которые легко сломать:
//   1. удаление обратимо: тост даёт «Отменить», и карточка возвращается на
//      своё место, а не в конец списка;
//   2. источник правды — settings.json: карточки с сервера заменяют локальные,
//      а пустой ответ означает первый запуск и отправляет семена на сервер.
//
// Run with: node --test tests/ui/effortcards.test.mjs
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

function grabConst(name) {
  const i = src.indexOf('const ' + name + ' = ');
  assert.ok(i >= 0, 'const not found in app.js: ' + name);
  let k = src.indexOf('=', i) + 1;
  let depth = 0;
  for (; k < src.length; k++) {
    if (src[k] === '{' || src[k] === '[') depth++;
    else if (src[k] === '}' || src[k] === ']') { depth--; if (!depth) break; }
    else if (src[k] === ';' && !depth) break;
  }
  return src.slice(i, k + 1);
}

// ── DOM / storage / network stubs ─────────────────────────────
const els = {};
const store = new Map();
globalThis.localStorage = {
  getItem: key => (store.has(key) ? store.get(key) : null),
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: key => store.delete(key),
};
globalThis.document = {
  getElementById: id => els[id] ?? null,
  querySelector: () => null,
};
globalThis.setTimeout = fn => { fn(); return 1; };
globalThis.clearTimeout = () => {};

let serverCards = null;
let posts = [];
globalThis.fetch = (url, opts) => {
  if (opts && opts.method === 'POST') {
    posts.push(JSON.parse(opts.body));
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
  }
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(serverCards
      ? { ok: true, cards: serverCards.cards, active: serverCards.active }
      : { ok: true, cards: [], active: '' }),
  });
};

let renders = 0;
globalThis.renderEffortCards = () => { renders++; };
globalThis.fillEffortEditor = () => {};
let toasts = [];
globalThis.showToast = (msg, type, opts) => { toasts.push({ msg, type, opts }); };

(0, eval)([
  grabConst('EFFORT_DEFAULTS'), grabConst('EFFORT_ORDER'),
  "const EFFORT_STORE = 'effort-cards';",
  "const EFFORT_LEGACY_STORE = 'effort-presets';",
  "const EFFORT_SERVER = '/effort/cards';",
  'let _effortCards = null;',
  "let _effortActive = '';",
  'let _effortSaveTimer = null;',
  'let _effortUndo = null;',
  'let _effortServerReady = false;',
  'let _editingEffort = null;',
  grab('_effortClamp'), grab('_effortNormalize'), grab('_effortDefaults'),
  grab('_effortLocalCards'), grab('loadEffortCards'), grab('_effortPostToServer'),
  grab('_effortScheduleServerSave'), grab('saveEffortCards'),
  grab('loadEffortCardsFromServer'), grab('effortCard'), grab('currentEffort'),
  grab('setSearchEffort'), grab('_effortWindowOpen'), grab('deleteEffortCard'),
  grab('undoDeleteEffortCard'),
  // Сброс кеша — внутри eval: _effortCards объявлен через let, снаружи до
  // него не добраться.
  'globalThis.__effortTestReset = (list, active) => {'
    + '_effortCards = null; _effortActive = ""; _effortUndo = null;'
    + '_effortServerReady = true;'
    + '_editingEffort = null;'
    + 'localStorage.setItem(EFFORT_STORE, JSON.stringify(list));'
    + 'if (active) localStorage.setItem("search-effort", active);'
    + 'else localStorage.removeItem("search-effort");'
    + '};',
].join('\n'));

function reset(cards, active = '') {
  store.clear();
  els.length = 0;
  toasts = [];
  posts = [];
  renders = 0;
  serverCards = null;
  globalThis.__effortTestReset(cards, active);
}

const cards = [
  { key: 'a', name: 'Первый', note: '', pages: 1, candidates: 20, vk: false },
  { key: 'b', name: 'Второй', note: '', pages: 2, candidates: 200, vk: false },
  { key: 'c', name: 'Третий', note: '', pages: 5, candidates: 600, vk: true },
];

// ── Отмена удаления ───────────────────────────────────────────
test('удаление показывает «Отменить» и возвращает карточку на место', () => {
  reset(cards, 'b');

  globalThis.deleteEffortCard();

  assert.deepEqual(globalThis.loadEffortCards().map(c => c.key), ['a', 'c']);
  assert.equal(globalThis.currentEffort(), 'a', 'активной стала следующая');
  const toast = toasts.find(t => t.msg === 'Карточка удалена');
  assert.ok(toast, 'нет тоста об удалении');
  assert.equal(toast.opts.action.label, 'Отменить');
  assert.equal(toast.opts.duration, 8000, 'на отмену даётся время');

  toast.opts.action.onClick();

  assert.deepEqual(globalThis.loadEffortCards().map(c => c.key), ['a', 'b', 'c']);
  assert.equal(globalThis.currentEffort(), 'b', 'прежняя активная вернулась');
  assert.ok(renders > 0, 'сайдбор перерисован');
});

test('отмена без удаления ничего не делает', () => {
  reset(cards);
  globalThis.undoDeleteEffortCard();
  assert.deepEqual(globalThis.loadEffortCards().map(c => c.key), ['a', 'b', 'c']);
});

test('последнюю карточку удалить нельзя', () => {
  reset([cards[0]]);
  globalThis.deleteEffortCard();
  assert.equal(globalThis.loadEffortCards().length, 1);
  assert.match(toasts[0].msg, /Последнюю/);
});

// ── settings.json как источник правды ────────────────────────
test('карточки с сервера заменяют локальные', async () => {
  reset(cards, 'a');
  serverCards = {
    active: 'x',
    cards: [{ key: 'x', name: 'С сервера', note: '', pages: 3, candidates: 300, vk: false }],
  };

  await globalThis.loadEffortCardsFromServer();

  assert.deepEqual(globalThis.loadEffortCards().map(c => c.key), ['x']);
  assert.equal(globalThis.currentEffort(), 'x');
});

test('пустой сервер получает текущие карточки при первом запуске', async () => {
  reset(cards, 'b');

  await globalThis.loadEffortCardsFromServer();

  assert.equal(posts.length, 1, 'семена отправлены один раз');
  assert.deepEqual(posts[0].cards.map(c => c.key), ['a', 'b', 'c']);
  assert.equal(posts[0].active, 'b');
});
