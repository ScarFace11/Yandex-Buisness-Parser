// Тема интерфейса: два режима и цикл кнопки — светлая → тёмная → светлая.
//
// Covered here:
//   • themePref(): по умолчанию 'light', мусор в хранилище — тоже 'light';
//   • toggleTheme(): цикл кнопки, запись в хранилище, data-theme и значок.
//
// Режим «как в системе» убран из интерфейса намеренно: кнопка переключает
// только светлую и тёмную, поэтому matchMedia здесь не участвует.
//
// Механика переключения в живом интерфейсе (значок, aria-label, анимация)
// проверяется в браузере (tests/test_a11y_keyboard.py); здесь — логика режимов,
// которая может незаметно сломаться при рефакторинге.
//
// Run with: node --test tests/ui/*.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readAppSrc } from './_src.mjs';

const src = readAppSrc();

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

// Литералы темы: строка кончается "';", массив — '];', объект — '};'.
function grabLiteral(name) {
  const m = new RegExp('const\\s+' + name + '\\s*=').exec(src);
  assert.ok(m, 'const not found in app.js: ' + name);
  const i = m.index;
  const eq = src.indexOf('=', i) + 1;
  let j = eq;
  while (j < src.length && /\s/.test(src[j])) j++;
  let end;
  if (src[j] === "'" || src[j] === '"') end = src.indexOf("';", i) + 2;
  else if (src[j] === '[') end = src.indexOf('];', i) + 2;
  else end = src.indexOf('};', i) + 2;
  assert.ok(end > i, 'конец литерала не найден: ' + name);
  return src.slice(i, end).trim().replace(/;$/, '');
}

const CODE = [
  grabLiteral('THEME_KEY'), grabLiteral('THEME_ORDER'), grabLiteral('THEME_RU'),
  'let themeAnimTimer = null;',
  grab('themePref'), grab('applyTheme'),
  grab('applyThemePref'), grab('toggleTheme'),
].join('\n');

// Окружение под контролем теста: хранилище и DOM.
function makeApp({ stored = null } = {}) {
  const state = { stored, theme: null };
  const ls = {
    getItem: k => (k === 'yp_theme_v1' ? state.stored : null),
    setItem: (k, v) => { if (k === 'yp_theme_v1') state.stored = v; },
  };
  const btn = { innerHTML: '', title: '', setAttribute: () => {} };
  const doc = {
    documentElement: {
      setAttribute: (_k, v) => { state.theme = v; },
      getAttribute: () => state.theme,
      classList: { add: () => {}, remove: () => {} },
    },
    getElementById: id => (id === 'btn-theme' ? btn : null),
  };
  const api = new Function(
    'localStorage', 'document', 'UI_ICONS', 'setTimeout', 'clearTimeout',
    CODE + '; return { themePref, applyThemePref, toggleTheme };')(
      ls, doc,
      { sun: 'ICON-sun', moon: 'ICON-moon' },
      () => 0, () => {});
  return { state, api, btn };
}

test('по умолчанию тема — светлая', () => {
  assert.equal(makeApp().api.themePref(), 'light');
});

test('мусор в хранилище не ломает выбор темы', () => {
  assert.equal(makeApp({ stored: 'neon' }).api.themePref(), 'light');
});

test('сохранённая тёмная тема читается обратно', () => {
  assert.equal(makeApp({ stored: 'dark' }).api.themePref(), 'dark');
});

test('кнопка циклически меняет: светлая → тёмная → светлая', () => {
  const a = makeApp({ stored: 'light' });
  a.api.toggleTheme();
  assert.equal(a.state.stored, 'dark');
  assert.equal(a.state.theme, 'dark');
  assert.equal(a.btn.innerHTML, 'ICON-sun');

  a.api.toggleTheme();
  assert.equal(a.state.stored, 'light');
  assert.equal(a.state.theme, 'light');
  assert.equal(a.btn.innerHTML, 'ICON-moon');
});
