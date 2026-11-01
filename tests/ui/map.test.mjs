// UI unit tests for the map panel: category colours, filters, popup (offline).
//
// Карта перестала быть «все точки одним цветом». Здесь проверяется то, что
// легко сломать и не видно в разметке: цвета категорий не повторяются,
// фильтры (поиск, отзывы, сайт, «только новые») отсекают ровно то, что нужно,
// а попап показывает контакты читаемыми классами, а не бледной строкой.
//
// Run with: node --test tests/ui/map.test.mjs
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
  const i = src.indexOf('const ' + name + ' =');
  assert.ok(i >= 0, 'const not found: ' + name);
  const open = src[src.indexOf('=', i) + 2];
  let k = src.indexOf('=', i) + 2;
  if (open === '[' || open === '{') {
    const close = open === '[' ? ']' : '}';
    let depth = 0;
    for (; k < src.length; k++) {
      if (src[k] === open) depth++;
      else if (src[k] === close) { depth--; if (!depth) break; }
    }
    return 'globalThis.' + name + ' = ' + src.slice(src.indexOf('=', i) + 2, k + 1) + ';';
  }
  return 'globalThis.' + name + ' = ' + src.slice(src.indexOf('=', i) + 2, src.indexOf(';', k)) + ';';
}

globalThis.escapeHtml = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');
globalThis.safeUrl = v => {
  const raw = String(v || '');
  return /^https:\/\//i.test(raw) ? raw : '#';
};
globalThis.pluralNum = (n, one, few, many) => {
  const a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
};
globalThis.SOCIALS = { vk: '#4C75A3', telegram: '#2CA5E0' };
globalThis.SLABELS = { vk: 'VK', telegram: 'TG' };

(0, eval)([
  grabConst('MAP_CAT_COLORS'),
  grab('mapCatParts'), grab('mapCatKey'), grab('mapCatExtra'),
  grab('mapCategories'), grab('mapCatColor'),
  grab('mapRowVisible'), grab('mapPopupHtml'),
].join('\n'));

const R = (name, city, extra = {}) => ({
  name, category: 'Кафе', lat: '55.75', lon: '37.62', city, ...extra,
});

// ── Категории и цвета ────────────────────────────────────────
test('категории считаются по частоте, при равенстве — по алфавиту', () => {
  const cats = mapCategories([
    R('A', 'Москва', { category: 'Кафе' }),
    R('B', 'Москва', { category: 'Автомойка' }),
    R('C', 'Москва', { category: 'Кафе' }),
    R('D', 'Москва', { category: 'Ресторан' }),
    R('E', 'Москва', { category: 'Автомойка' }),
    R('F', 'Москва', { category: 'Кафе' }),
  ]);
  assert.deepEqual(cats.map(c => c.name), ['Кафе', 'Автомойка', 'Ресторан']);
  assert.deepEqual(cats[0], { name: 'Кафе', count: 3 });
});

test('точка без координат в легенду не попадает', () => {
  const cats = mapCategories([
    R('A', 'Москва', { category: 'Кафе' }),
    { name: 'B', category: 'Бар' },                    // без lat/lon
    R('C', 'Москва', { category: 'Бар', lat: '' }),
  ]);
  assert.deepEqual(cats.map(c => c.name), ['Кафе']);
});

test('пустая категория не смешивается с реальной', () => {
  assert.equal(mapCatKey({ category: '  ' }), 'Без категории');
  assert.equal(mapCatKey({}), 'Без категории');
  assert.equal(mapCatKey({ category: ' Кафе ' }), 'Кафе');
});

// Карточка приходит со списком категорий: «Автомойка, Шиномонтаж, Автоэлектрик».
// В легенде такая строка рождала десятки строк по одной записи, поэтому
// группой считается первая категория, а остальные уходят в карточку метки.
test('категория точки — первая из списка', () => {
  assert.equal(mapCatKey({ category: 'Автомойка, Шиномонтаж' }), 'Автомойка');
  assert.equal(mapCatKey({ category: ' Автомойка ,Шиномонтаж ,' }), 'Автомойка');
  assert.equal(mapCatExtra({ category: 'Автомойка, Шиномонтаж, Автоэлектрик' }),
    'Шиномонтаж, Автоэлектрик');
  assert.equal(mapCatExtra({ category: 'Автомойка' }), '');
  assert.equal(mapCatExtra({}), '');
});

test('список категорий через запятую даёт одну строку легенды', () => {
  const cats = mapCategories([
    R('A', 'Ярославль', { category: 'Автомойка, Шиномонтаж' }),
    R('B', 'Ярославль', { category: 'Автомойка, Автоэлектрик' }),
    R('C', 'Ярославль', { category: 'Кафе, Кофейня' }),
  ]);
  assert.deepEqual(cats, [{ name: 'Автомойка', count: 2 }, { name: 'Кафе', count: 1 }]);
});

test('у каждой категории свой цвет, и он не меняется между перерисовками', () => {
  const rows = ['Кафе', 'Автомойка', 'Ресторан', 'Бар', 'Стоматология'].map(
    (c, i) => R('N' + i, 'Москва', { category: c }));
  const cats = mapCategories(rows);
  const colors = cats.map(c => mapCatColor(c.name, cats));
  assert.equal(new Set(colors).size, colors.length, 'цвета не повторяются');
  // Тот же набор — те же цвета: легенда не перекрашивается сама по себе.
  assert.deepEqual(mapCategories(rows).map(c => mapCatColor(c.name, cats)), colors);
  // Цвет — из палитры, а не случайный.
  colors.forEach(c => assert.ok(MAP_CAT_COLORS.includes(c), c));
});

// ── Фильтры ──────────────────────────────────────────────────
test('поиск по названию не зависит от регистра и пробелов', () => {
  const row = R('Кофейня «Утро»', 'Москва');
  assert.equal(mapRowVisible(row, { search: 'утро' }), true);
  assert.equal(mapRowVisible(row, { search: '  УТРО ' }), true);
  assert.equal(mapRowVisible(row, { search: 'вечер' }), false);
  // Пустой запрос ничего не отсекает.
  assert.equal(mapRowVisible(row, { search: '' }), true);
});

test('скрытая категория пропадает с карты', () => {
  const row = R('A', 'Москва', { category: 'Кафе' });
  assert.equal(mapRowVisible(row, { hidden: new Set(['Кафе']) }), false);
  assert.equal(mapRowVisible(row, { hidden: new Set(['Бар']) }), true);
});

test('порог отзывов отсекает компании без потока клиентов', () => {
  const row = R('A', 'Москва', { reviews_count: '42' });
  assert.equal(mapRowVisible(row, { minReviews: 50 }), false);
  assert.equal(mapRowVisible(row, { minReviews: 10 }), true);
  // Без числа отзывов запись не проходит порог, но видна при «любых».
  const none = R('B', 'Москва');
  assert.equal(mapRowVisible(none, { minReviews: 5 }), false);
  assert.equal(mapRowVisible(none, { minReviews: 0 }), true);
});

test('«с сайтом» и «без сайта» учитывают и визитку-таплинк', () => {
  const own = R('A', 'Москва', { website: 'https://kafe.ru' });
  const tap = R('B', 'Москва', { aggregator_url: 'https://taplink.cc/kafe' });
  const none = R('C', 'Москва');
  assert.equal(mapRowVisible(own, { siteMode: 'with' }), true);
  assert.equal(mapRowVisible(tap, { siteMode: 'with' }), true);
  assert.equal(mapRowVisible(none, { siteMode: 'with' }), false);
  assert.equal(mapRowVisible(none, { siteMode: 'without' }), true);
  assert.equal(mapRowVisible(tap, { siteMode: 'without' }), false);
  assert.equal(mapRowVisible(tap, { siteMode: 'all' }), true);
});

test('«только новые» берёт серверный признак, как фильтр таблицы', () => {
  const fresh = R('A', 'Москва', { _is_new: true });
  const old = R('B', 'Москва', { _is_new: false });
  const unknown = R('C', 'Москва');
  assert.equal(mapRowVisible(fresh, { onlyNew: true }), true);
  assert.equal(mapRowVisible(old, { onlyNew: true }), false);
  assert.equal(mapRowVisible(unknown, { onlyNew: true }), false, 'не с чем сравнивать — не новое');
  assert.equal(mapRowVisible(old, { onlyNew: false }), true);
});

test('фильтр по оценке отсекает слабые лиды', () => {
  const hot = R('A', 'Москва', { lead_score: 72 });
  const cold = R('B', 'Москва', { lead_score: 30 });
  const none = R('C', 'Москва');
  assert.equal(mapRowVisible(hot, { minScore: 65 }), true);
  assert.equal(mapRowVisible(cold, { minScore: 65 }), false);
  assert.equal(mapRowVisible(cold, { minScore: 0 }), true);
  // Без оценки запись не проходит порог: сравнивать нечего.
  assert.equal(mapRowVisible(none, { minScore: 35 }), false);
});

test('фильтры складываются, а не перекрывают друг друга', () => {
  const row = R('Кофейня', 'Москва', { reviews_count: '120', vk: 'https://vk.com/x' });
  const ok = { search: 'коф', minReviews: 100, siteMode: 'without', onlyNew: true };
  assert.equal(mapRowVisible({ ...row, _is_new: true }, ok), true);
  assert.equal(mapRowVisible({ ...row, _is_new: true }, { ...ok, minReviews: 200 }), false);
});

// ── Попап метки ──────────────────────────────────────────────
test('попап показывает категорию, рейтинг, контакты и сайт', () => {
  const html = mapPopupHtml(R('Клиника «Здоровье»', 'Москва', {
    category: 'Стоматология', reviews_count: '128', rating: '4.7',
    address: 'ул. Ленина, 1', phone: '+7 900 000-00-00',
    website: 'https://klinika.ru', yandex_maps_url: 'https://yandex.ru/maps/1',
    lead_score: 85,
  }), MAP_CAT_COLORS[0]);
  assert.match(html, /map-pop-cat/, 'категория — бейдж');
  assert.match(html, /Стоматология/);
  assert.match(html, /128 отзывов/);
  assert.match(html, /ул\. Ленина, 1/);
  assert.match(html, /\+7 900 000-00-00/);
  assert.match(html, /https:\/\/klinika\.ru/);
  assert.match(html, /Открыть на Я\.Картах/);
  assert.match(html, /85 из 100/);
});

test('попап показывает и остальные категории компании', () => {
  const html = mapPopupHtml(R('Мойка', 'Москва', {
    category: 'Автомойка, Шиномонтаж, Полировка',
  }), MAP_CAT_COLORS[2]);
  assert.match(html, /<div class="map-pop-cat">Автомойка<\/div>/);
  assert.match(html, /Ещё: Шиномонтаж, Полировка/);
  // Одна категория — без пустой строки «Ещё:».
  assert.ok(!/Ещё:/.test(mapPopupHtml(R('Мойка', 'Москва', { category: 'Автомойка' }), MAP_CAT_COLORS[2])));
});

test('попап не выводит пустые поля и экранирует данные', () => {
  const html = mapPopupHtml({ name: '<b>Кафе</b>', category: 'Кафе', lat: '1', lon: '1' },
    MAP_CAT_COLORS[1]);
  assert.ok(!/<b>Кафе<\/b>/.test(html), 'имя экранировано');
  assert.ok(!/map-pop-row/.test(html), 'пустых строк нет');
  assert.ok(!/Открыть на Я\.Картах/.test(html), 'без ссылки на карточку — без строки');
});
