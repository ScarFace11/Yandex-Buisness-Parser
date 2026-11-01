// Кнопки шапки: обработчик есть, скрипты разбираются целиком.
//
// Регресс, ради которого это написано: кнопки верхней панели переставали
// нажиматься, хотя разметка не менялась. Причина — модуль, который не
// разобрался (синтаксическая ошибка или оборванный файл): его объявления
// функций тогда не создаются вовсе, и onclick="showLogsModal()" падает с
// «showLogsModal is not defined» — клик выглядит «мёртвым». Кнопка
// «Соглашение» при этом работала, потому что её обработчик живёт в другом
// модуле. Воспроизведено на живом приложении: с намеренно сломанным
// 09-ui-extras.js нажимались ровно те кнопки, чьи обработчики в нём не лежат.
//
// Вторая проверка того же класса — в браузере: что до кнопки вообще доходит
// клик (её не накрыл прозрачный слой), tests/test_a11y_browser.py.
//
// Run with: node --test tests/ui/*.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { readAppSrc, root } from './_src.mjs';

const html = readFileSync(join(root, 'templates', 'index.html'), 'utf8');
const src = readAppSrc();

// Кнопки, без которых шапка перестаёт быть шапкой: у каждой свой id и onclick.
const HEADER_BUTTONS = [
  'btn-terms', 'btn-notify', 'btn-theme', 'btn-skip',
  'btn-logs', 'btn-diag', 'btn-report', 'btn-whatsnew', 'btn-updates',
];

function headerHtml() {
  const start = html.indexOf('<header>');
  const end = html.indexOf('</header>');
  assert.ok(start >= 0 && end > start, 'в шаблоне нет <header>…</header>');
  return html.slice(start, end);
}

function buttonMarkup(id) {
  const at = html.indexOf('id="' + id + '"');
  assert.ok(at >= 0, 'кнопки нет в шаблоне: ' + id);
  const open = html.lastIndexOf('<button', at);
  const close = html.indexOf('>', at);
  return html.slice(open, close + 1);
}

function handlerName(markup) {
  const m = /onclick="([A-Za-z_$][\w$]*)\(/.exec(markup);
  return m ? m[1] : null;
}

// Объявление функции в любом из модулей: обычное или присваиванием.
function isDeclared(name) {
  return new RegExp('function\\s+' + name + '\\s*\\(').test(src)
    || new RegExp('\\b' + name + '\\s*=\\s*(async\\s+)?function').test(src);
}

test('у каждой кнопки шапки есть id, onclick и обработчик в скриптах', () => {
  const header = headerHtml();
  const problems = [];
  for (const id of HEADER_BUTTONS) {
    assert.ok(header.includes('id="' + id + '"'), 'кнопка вне шапки или пропала: ' + id);
    const markup = buttonMarkup(id);
    const name = handlerName(markup);
    if (!name) { problems.push(id + ': нет onclick'); continue; }
    if (!isDeclared(name)) problems.push(id + ': обработчик ' + name + ' не объявлен');
    if (/\sdisabled(\s|>)/.test(markup)) problems.push(id + ': кнопка disabled');
  }
  assert.deepEqual(problems, [], 'кнопки шапки без рабочего обработчика:\n  ' + problems.join('\n  '));
});

test('шапка не теряет кнопки: набор id совпадает с ожидаемым', () => {
  const header = headerHtml();
  const found = [...header.matchAll(/<button[^>]*\bid="([^"]+)"/g)].map(m => m[1]);
  const buttons = found.filter(id => !id.startsWith('notify-'));
  assert.deepEqual(
    buttons.sort(),
    [...HEADER_BUTTONS].sort(),
    'набор кнопок шапки изменился — проверь, что ни одна не осталась без обработчика',
  );
});

test('все модули скриптов разбираются: сломанный файл не оставит кнопки без обработчиков', () => {
  // Склейка в порядке подключения — тот же текст, что грузит браузер.
  // new Function только компилирует: топ-level обращения к DOM не выполняются.
  assert.doesNotThrow(
    () => new Function(src),
    'склейка static/js/*.js не разбирается — модуль с синтаксической ошибкой '
    + 'не создаст свои функции, и кнопки шапки перестанут нажиматься',
  );
});
