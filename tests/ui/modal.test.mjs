// UI unit tests for the shared dialogs: uiConfirm and uiChoose.
//
// Окно выбора проверялось только сквозным тестом в браузере, поэтому его
// результат (какой вариант вернулся, что делает чекбокс «применить ко всем»)
// не был закреплён. Здесь проверяется именно возвращаемое значение, отмена,
// клик вне окна и экранирование данных, без запуска браузера.
//
// Run with: node --test tests/ui/modal.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readAppSrc, MODAL_A11Y_STUB, root } from './_src.mjs';

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

(0, eval)([
  MODAL_A11Y_STUB,
  grab('escapeHtml'),
  grab('uiConfirm'),
  grab('uiChoose'),
].join('\n'));

const ENTITIES = {amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'"};

function decodeEntities(value) {
  return String(value).replace(/&(amp|lt|gt|quot|#39);/g, (_, name) => ENTITIES[name]);
}

function mkEl(tag, className = '') {
  return {
    tagName: tag.toUpperCase(),
    className,
    textContent: '',
    dataset: {},
    value: '',
    checked: false,
    removed: false,
    focused: false,
    _listeners: {},
    addEventListener(type, fn) {
      (this._listeners[type] ||= []).push(fn);
    },
    click() {
      if (typeof this.onclick === 'function') this.onclick({target: this});
      for (const fn of this._listeners.click || []) fn({target: this});
    },
    focus() { this.focused = true; },
    remove() { this.removed = true; },
  };
}

let lastOverlay = null;

function mkOverlay() {
  const overlay = mkEl('div', 'ui-modal-overlay');
  let html = '';
  overlay._options = [];
  overlay._cancel = null;
  overlay._ok = null;
  overlay._checkbox = null;

  Object.defineProperty(overlay, 'innerHTML', {
    get: () => html,
    set(value) {
      html = String(value);
      overlay._options = [];
      overlay._cancel = null;
      overlay._ok = null;
      overlay._checkbox = null;

      const buttonRe = /<button\b([^>]*)>([^<]*)<\/button>/g;
      let match;
      while ((match = buttonRe.exec(html))) {
        const attrs = match[1];
        const cls = (/class="([^"]*)"/.exec(attrs) || [])[1] || '';
        const value = /data-value="([^"]*)"/.exec(attrs);
        const button = mkEl('button', cls);
        button.textContent = match[2];
        button.value = decodeEntities(value ? value[1] : '');
        button.dataset.value = button.value;
        const names = cls.split(/\s+/);
        if (names.includes('m-opt')) overlay._options.push(button);
        if (names.includes('m-cancel')) overlay._cancel = button;
        if (names.includes('m-ok')) overlay._ok = button;
      }
      if (/class="m-applyall"/.test(html)) {
        overlay._checkbox = mkEl('input', 'm-applyall');
      }
    },
  });

  overlay.querySelectorAll = sel => (sel === '.m-opt' ? overlay._options : []);
  overlay.querySelector = sel => {
    if (sel === '.m-opt') return overlay._options[0] || null;
    if (sel === '.m-cancel') return overlay._cancel;
    if (sel === '.m-ok') return overlay._ok;
    if (sel === '.m-applyall') return overlay._checkbox;
    return null;
  };
  return overlay;
}

globalThis.document = {
  createElement: () => mkOverlay(),
  body: {
    appendChild: el => { lastOverlay = el; },
  },
};

function open(fn) {
  const promise = fn();
  assert.ok(lastOverlay, 'окно не добавилось в body');
  return {promise, overlay: lastOverlay};
}

test('uiConfirm: «ОК» возвращает true и закрывает окно', async () => {
  const {promise, overlay} = open(() =>
    uiConfirm('Удалить файл?', 'Удалить файл', 'Удалить', true));
  assert.equal(overlay.querySelector('.m-ok').className, 'm-ok danger');
  assert.equal(overlay.querySelector('.m-ok').focused, true);
  overlay.querySelector('.m-ok').click();
  assert.equal(await promise, true);
  assert.equal(overlay.removed, true);
});

test('uiConfirm: «Отмена» и клик вне окна дают false', async () => {
  let {promise, overlay} = open(() => uiConfirm('Удалить?', 'Удалить', 'Удалить'));
  overlay.querySelector('.m-cancel').click();
  assert.equal(await promise, false);
  assert.equal(overlay.removed, true);

  ({promise, overlay} = open(() => uiConfirm('Удалить?', 'Удалить', 'Удалить')));
  overlay.click();
  assert.equal(await promise, false);
  assert.equal(overlay.removed, true);
});

test('uiConfirm: Escape даёт false', async () => {
  const {promise, overlay} = open(() => uiConfirm('Удалить?', 'Удалить', 'Удалить'));
  for (const fn of overlay._listeners.keydown || []) {
    fn({key: 'Escape', preventDefault() {}});
  }
  assert.equal(await promise, false);
});

test('uiChoose: выбранный вариант возвращает value и applyAll=false', async () => {
  const {promise, overlay} = open(() => uiChoose(
    'Что делать?', 'Выбор',
    [{value: 'a', label: 'Первый'}, {value: 'b', label: 'Второй'}]));
  assert.equal(overlay._options.length, 2);
  assert.equal(overlay._options[0].focused, true);
  overlay._options[1].click();
  assert.deepEqual(await promise, {value: 'b', applyAll: false});
  assert.equal(overlay.removed, true);
});

test('uiChoose: чекбокс «применить ко всем» попадает в результат', async () => {
  const {promise, overlay} = open(() => uiChoose(
    'Что делать?', 'Выбор', [{value: 'a', label: 'Первый'}],
    {checkboxLabel: 'Применить ко всем'}));
  overlay._checkbox.checked = true;
  overlay._options[0].click();
  assert.deepEqual(await promise, {value: 'a', applyAll: true});
});

test('uiChoose: «Отмена» и клик вне окна дают null', async () => {
  let {promise, overlay} = open(() => uiChoose(
    'Что делать?', 'Выбор', [{value: 'a', label: 'Первый'}]));
  overlay.querySelector('.m-cancel').click();
  assert.equal(await promise, null);

  ({promise, overlay} = open(() => uiChoose(
    'Что делать?', 'Выбор', [{value: 'a', label: 'Первый'}])));
  overlay.click();
  assert.equal(await promise, null);
});

test('uiChoose: текст и значения экранируются, значение возвращается как есть', async () => {
  const {promise, overlay} = open(() => uiChoose(
    '<b>текст</b>', '<i>заголовок</i>',
    [{value: 'a"b', label: '<вариант>'}]));
  assert.ok(overlay.innerHTML.includes('&lt;b&gt;текст&lt;/b&gt;'));
  assert.ok(overlay.innerHTML.includes('&lt;i&gt;заголовок&lt;/i&gt;'));
  assert.ok(overlay.innerHTML.includes('data-value="a&quot;b"'));
  assert.ok(overlay.innerHTML.includes('&lt;вариант&gt;'));
  overlay._options[0].click();
  assert.deepEqual(await promise, {value: 'a"b', applyAll: false});
});

test('uiChoose: пустой список вариантов всё равно можно отменить', async () => {
  const {promise, overlay} = open(() => uiChoose('Ничего нет', 'Выбор', null));
  assert.equal(overlay._options.length, 0);
  overlay.querySelector('.m-cancel').click();
  assert.equal(await promise, null);
});
