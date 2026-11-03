// UI unit tests: «Тип компании» — только значения формы.
//
// Счётчик «сколько подойдёт» удалён: он ходил в сеть при каждом клике и
// показывал цифру, которую пользователь не просил. Остались сами фильтры:
// период, выключенный без своего чекбокса, и значения для запуска поиска.
//
// Run with: node --test tests/ui/companytype.test.mjs
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

function mkEl(id) {
  const classes = new Set();
  return {
    id, value: '', checked: false, disabled: false,
    classList: {
      add: (...c) => c.forEach(x => classes.add(x)),
      remove: (...c) => c.forEach(x => classes.delete(x)),
      toggle: (c, on) => { const w = on === undefined ? !classes.has(c) : !!on; w ? classes.add(c) : classes.delete(c); },
      contains: c => classes.has(c),
    },
    closest: () => mkEl('chk-' + id),
    querySelectorAll: () => [],
  };
}

const els = {};
for (const id of ['f-only-single', 'f-only-new', 'f-new-months', 'company-type-new-row']) {
  els[id] = mkEl(id);
}
els['f-new-months'].value = '6';
globalThis.document = {
  getElementById: id => els[id] ?? null,
  querySelectorAll: () => [],
  querySelector: () => null,
  addEventListener: () => {},
  body: mkEl('body'),
};
// Ни один из оставшихся обработчиков не должен ходить в сеть.
globalThis.fetch = () => { throw new Error('сеть не нужна: счётчик удалён'); };

(0, eval)([
  grabConst('COMPANY_TYPE_PERIODS'), grabConst('COMPANY_TYPE_DEFAULT_MONTHS'),
  grab('onlySingleChecked'), grab('newMonthsValue'), grab('newMonthsPeriod'),
  grab('companyTypeOn'), grab('syncCompanyTypeUi'), grab('onCompanyTypeChange'),
].join('\n'));

function reset({ single = false, onlyNew = false, period = '6' } = {}) {
  els['f-only-single'].checked = single;
  els['f-only-new'].checked = onlyNew;
  els['f-new-months'].value = period;
  globalThis.syncCompanyTypeUi();
}

test('оба фильтра выключены: значения для запуска пустые', () => {
  reset();
  assert.equal(globalThis.companyTypeOn(), false);
  assert.equal(globalThis.newMonthsValue(), null);
  assert.equal(globalThis.newMonthsPeriod(), '6');
});

test('одиночки без периода и период без одиночек', () => {
  reset({ single: true });
  assert.equal(globalThis.newMonthsValue(), null);
  assert.equal(globalThis.onlySingleChecked(), true);

  reset({ onlyNew: true, period: '12' });
  assert.equal(globalThis.newMonthsValue(), 12);
  assert.equal(globalThis.newMonthsPeriod(), '12');
});

test('селект периода выключен, пока не отмечен его чекбокс', () => {
  reset();
  assert.equal(els['f-new-months'].disabled, true);
  assert.equal(els['company-type-new-row'].classList.contains('on'), false);

  els['f-only-new'].checked = true;
  globalThis.syncCompanyTypeUi();
  assert.equal(els['f-new-months'].disabled, false);
  assert.equal(els['company-type-new-row'].classList.contains('on'), true);
});

test('неизвестный период из DOM заменяется дефолтом', () => {
  reset({ onlyNew: true, period: '99' });
  assert.equal(globalThis.newMonthsValue(), 6);
});

test('изменение чекбокса не ходит в сеть', () => {
  reset();
  els['f-only-single'].checked = true;
  assert.doesNotThrow(() => globalThis.onCompanyTypeChange());
  assert.equal(globalThis.companyTypeOn(), true);
});
