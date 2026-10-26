// UI unit test: баннер обновления ставится под навигацию (а не поверх шапки),
// а сбой установки после перезапуска показывается один раз на попытку.
//
// Run with: node --test "tests/ui/updatebanner.test.mjs"
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

// ── Куда вставляется баннер ───────────────────────────────────
function mkEl(tag) {
  return {
    tag, parentElement: null, inserted: null, prepended: null,
    insertAdjacentElement(pos, node) {
      this.inserted = { pos, node };
      node.parentElement = this.parentElement;
    },
  };
}

function withDom({ hasNav }) {
  const body = mkEl('body');
  body.prepend = node => { body.prepended = node; };
  const col = mkEl('main');
  const nav = mkEl('nav');
  nav.parentElement = col;
  globalThis.document = {
    querySelector: sel => (sel === '.tab-bar' && hasNav ? nav : null),
    body,
  };
  return { body, col, nav };
}

(0, eval)(grab('_placeUpdateBanner'));

test('баннер вставляется сразу после вкладок, внутри правой колонки', () => {
  const { col, nav } = withDom({ hasNav: true });
  const banner = mkEl('div');
  globalThis._placeUpdateBanner(banner);
  assert.equal(nav.inserted.pos, 'afterend');
  assert.equal(nav.inserted.node, banner);
  assert.equal(banner.parentElement, col, 'родитель — колонка, а не body');
});

test('без навигации баннер всё равно не встаёт поверх шапки', () => {
  const { body } = withDom({ hasNav: false });
  const banner = mkEl('div');
  globalThis._placeUpdateBanner(banner);
  assert.equal(body.prepended, banner);
});

// ── Причина сбоя после перезапуска ────────────────────────────
function withToast(store) {
  const shown = [];
  globalThis.localStorage = {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
  };
  globalThis.showToast = (text, kind) => shown.push({ text, kind });
  return shown;
}

(0, eval)(grab('_notifyFailedUpdate'));

test('сбой установки показывается один раз на попытку', () => {
  const shown = withToast({});
  const data = { last_update: { ok: false, error: 'диск занят', at: '2026-10-25 10:00:00' } };
  globalThis._notifyFailedUpdate(data);
  globalThis._notifyFailedUpdate(data);
  assert.equal(shown.length, 1, 'повторный старт не повторяет тост');
  assert.equal(shown[0].kind, 'error');
  assert.match(shown[0].text, /диск занят/);
});

test('новая неудачная попытка снова видна', () => {
  const shown = withToast({});
  globalThis._notifyFailedUpdate({ last_update: { ok: false, error: 'раз', at: '1' } });
  globalThis._notifyFailedUpdate({ last_update: { ok: false, error: 'два', at: '2' } });
  assert.equal(shown.length, 2);
  assert.match(shown[1].text, /два/);
});

test('успешная установка и отсутствие результата молчат', () => {
  const shown = withToast({});
  globalThis._notifyFailedUpdate({ last_update: { ok: true, version: '2.3.5' } });
  globalThis._notifyFailedUpdate({});
  globalThis._notifyFailedUpdate(null);
  assert.equal(shown.length, 0);
});

test('к причине приложен путь к журналу', () => {
  const shown = withToast({});
  globalThis._notifyFailedUpdate({
    last_update: { ok: false, error: 'ошибка', at: '3', log: 'C:\\Data\\_update\\update.log' },
  });
  assert.match(shown[0].text, /update\.log/);
});

// ── «Что нового»: краткое описание и полный текст ─────────────────
(0, eval)(grab('_clTexts'));
(0, eval)(grab('_clVersions'));

test('подписи окна приходят из update_notes, без них — запасные', () => {
  const custom = globalThis._clTexts({ texts: { modal_title: 'Что нового', latest: 'свежая' } });
  assert.equal(custom.title, 'Что нового');
  assert.equal(custom.latest, 'свежая');
  assert.equal(custom.back, 'Назад', 'незаполненные подписи берутся из запасных');

  const fallback = globalThis._clTexts(null);
  assert.equal(fallback.title, 'История изменений');
  assert.equal(fallback.error.includes('интернет'), true);
});

test('версии приводятся к одной форме: summary, дата, пункты', () => {
  const list = globalThis._clVersions({
    version: '2.3.6',
    history: [
      { version: '2.3.6', date: '2026-10-25', title: 'Установщик', summary: 'кратко',
        items: [{ title: 'Ярлык', text: 'полный текст' }, { title: 'пусто', text: '' }] },
      { version: '2.3.3', changelog: 'старый формат' },
      { version: '' },
    ],
  });
  assert.equal(list.length, 2, 'запись без номера версии отбрасывается');
  assert.deepEqual(list[0].items, [{ title: 'Ярлык', text: 'полный текст' }]);
  assert.equal(list[0].summary, 'кратко');
  assert.equal(list[1].summary, 'старый формат', 'старое поле changelog читается как краткое');
  assert.deepEqual(list[1].items, []);
});

test('без history окно всё равно показывает текущий релиз', () => {
  const list = globalThis._clVersions({ version: '2.3.5', changelog: 'одна строка' });
  assert.equal(list.length, 1);
  assert.equal(list[0].version, '2.3.5');
  assert.equal(list[0].summary, 'одна строка');
});
