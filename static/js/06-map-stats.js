// ═══════════════════════════════════════════
// ── Экспорт/импорт данных приложения (отметки + настройки) ──
// Кнопки в аккордеоне «Форматы результата» (секция «Данные»). Экспорт — обычная ссылка на zip;
// импорт показывает сводку и перезагружает отметки, чтобы таблица и
// динамика увидели их сразу.
function exportAppData() {
  window.location.href = '/data/export';
  showToast('Готовлю архив с отметками и настройками…', 'info');
}

async function importAppData(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.zip')) {
    showToast('Нужен zip-архив из «Экспорта данных»', 'warning');
    input.value = '';
    return;
  }
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch('/data/import', { method: 'POST', body: fd });
    const d = await r.json();
    if (!d.ok) { showToast(d.error || 'Импорт не удался', 'error'); input.value = ''; return; }
    const parts = [];
    if (d.marks) parts.push(_pluralRu(d.marks, 'отметка', 'отметки', 'отметок'));
    if (d.settings) parts.push('настройки');
    // Настройки вкладок (browser.json из «Экспорта настроек»): применяем сами —
    // сервер их хранить не может, он лишь вернул снимок из архива.
    const applied = applyImportedBrowserSettings(d.browser);
    if (applied) parts.push('настройки окна: ' + applied);
    showToast('Импортировано: ' + (parts.join(', ') || 'ничего нового'), 'success');
    // Отметки приходят с сервера: перечитываем их и перерисовываем таблицу.
    try { loadReviewed(); } catch (e) {}
    try { _reloadDaily(); } catch (e) {}
    // Настройки вступают в силу при загрузке страницы — перезагружаем,
    // как это делает окно сброса.
    if (applied) setTimeout(() => location.reload(), 1100);
  } catch (e) {
    showToast('Импорт не удался — сервер не ответил', 'error');
  }
  input.value = '';
}

async function exportFiltered(fmt) {
  if (!filteredRows.length) return;
  // Выгрузка должна нести актуальные отметки, а не те, что были до батча.
  await autoPersistReviewed(true);
  fetch('/export-filtered', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({rows: filteredRows, format: fmt})
  })
  .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.blob(); })
  .then(blob => {
    const ext = fmt === 'xlsx' ? 'xlsx' : 'csv';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `filtered_export.${ext}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  })
  .catch(e => showToast('Ошибка экспорта: ' + e.message, 'error'));
}

// ═══════════════════════════════════════════
//  Map (Leaflet)
// ═══════════════════════════════════════════
// Leaflet подключается по требованию: библиотека лежит рядом с приложением
// (static/vendor/leaflet) и грузится только при открытии вкладки «На карте».
// Раньше <script> и <link> стояли в <head> и тянулись с unpkg при каждой
// загрузке страницы — без интернета вкладка не работала вообще.
// Промис кешируется: десять кликов по вкладке дают одну загрузку.
let _leafletPromise = null;
function loadLeaflet() {
  if (window.L) return Promise.resolve();
  if (_leafletPromise) return _leafletPromise;
  const assets = window.LEAFLET_ASSETS || {};
  _leafletPromise = new Promise((resolve, reject) => {
    if (!assets.js) { reject(new Error('путь к библиотеке карт не передан')); return; }
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = assets.css;
    document.head.appendChild(css);
    const js = document.createElement('script');
    js.src = assets.js;
    js.onload = () => (window.L ? resolve() : reject(new Error('библиотека карт не инициализировалась')));
    js.onerror = () => reject(new Error('файл библиотеки карт недоступен'));
    document.head.appendChild(js);
  });
  // Неудачу не запоминаем: следующий клик по вкладке попробует снова.
  _leafletPromise.catch(() => { _leafletPromise = null; });
  return _leafletPromise;
}

// Вкладка карты: сначала библиотека, потом карта. Ошибку показываем на месте
// карты — вместо пустого прямоугольника.
// mapPending — загрузка Leaflet и создание карты идут асинхронно. Пока они не
// закончились, повторный вызов (открыли файл и сразу переключили вкладку)
// создавал вторую карту на том же контейнере и падал с «Map container is
// already initialized» — вместо карты человек видел ошибку.
let mapPending = false;

function ensureMapReady() {
  if (mapPending) return;
  const container = document.getElementById('map-container');
  if (container && !window.L) container.innerHTML = '<div class="no-data" style="padding:40px">Загружаю карту…</div>';
  mapPending = true;
  loadLeaflet()
    .then(() => { mapPending = false; initMap(); })
    .catch(err => {
      mapPending = false;
      if (container) {
        container.innerHTML = '<div class="no-data" style="padding:40px">Карта недоступна: '
          + escapeHtml(err && err.message ? err.message : 'библиотека не загрузилась')
          + '. Результаты и выгрузка работают без неё.</div>';
      }
    });
}

// ── Состояние карты ──────────────────────────────────────────
// Палитра категорий — это данные визуализации, как SOCIALS и CAT_COLORS ниже:
// цвета различают категории, а не оформляют поверхность, поэтому токенами
// темы их не выразить. Тона тёмные: и точка, и подпись в легенде читаются на
// светлой подложке карты, а белый текст на бейдже даёт нужный контраст.
const MAP_CAT_COLORS = ['#1d4ed8', '#b91c1c', '#047857', '#b45309', '#6d28d9',
                        '#0e7490', '#be185d', '#4d7c0f', '#c2410c', '#4338ca',
                        '#0f766e', '#a21caf'];
// Порог отзывов задаётся списком, а не полем ввода: в таблице «горячим» уже
// считается от 50 отзывов, и на карте полезны те же ступени.
const MAP_REVIEW_STEPS = [0, 5, 10, 50, 100];
// Ступени оценки лида те же, что у пресетов таблицы: на карте нужен не
// произвольный порог, а тот же отбор «горячих» клиентов.
const MAP_SCORE_STEPS = [0, 35, 50, 65];

let mapHiddenCats = new Set();     // категории, снятые галочкой в легенде
let mapSearch = '';                // поиск по названию бизнеса
let mapMinReviews = 0;
let mapMinScore = 0;
let mapSiteMode = 'all';           // all | with | without
let mapOnlyNew = false;
let mapLayer = null;               // слой меток; пересобирается без пересоздания карты

// Категории из карточки: их приходит целая строка через запятую
// («Автомойка, Шиномонтаж, Автоэлектрик»). В легенду идёт только первая:
// иначе один и тот же вид бизнеса распадался на десятки строк по одной
// записи. Остальные категории показывает карточка метки.
function mapCatParts(r) {
  return String((r && r.category) || '')
    .split(',').map(s => s.trim()).filter(Boolean);
}

// Категория точки: пустая не должна сливаться с «Без категории» в фильтре.
function mapCatKey(r) {
  return mapCatParts(r)[0] || 'Без категории';
}

// Второстепенные категории строкой — для карточки метки: подробности нужны
// при выборе точки, но в легенде они только мешают.
function mapCatExtra(r) {
  return mapCatParts(r).slice(1).join(', ');
}

// Город точки: в одном наборе бывает несколько городов, и одна и та же
// категория в них — разные группы.
function mapCityKey(r) {
  return String((r && r.city) || '').trim() || 'Без города';
}

// Ключ скрытия — пара «город + категория»: без города одно нажатие в легенде
// убирало бы кофейни сразу из всех городов. Разделитель — \u001f, его не
// бывает в названиях, поэтому ключи не склеиваются.
function mapCatHideKey(city, cat) {
  return city + '\u001f' + cat;
}

function mapHideKey(r) {
  return mapCatHideKey(mapCityKey(r), mapCatKey(r));
}

// Города и их категории для легенды: внутри города — по частоте и алфавиту,
// сами города — по числу точек. Порядок не прыгает между перерисовками.
function mapCityGroups(rows) {
  const cities = new Map();
  (rows || []).forEach(r => {
    if (!r || !r.lat || !r.lon) return;
    const city = mapCityKey(r), cat = mapCatKey(r);
    let node = cities.get(city);
    if (!node) { node = { city, total: 0, cats: new Map() }; cities.set(city, node); }
    node.total += 1;
    node.cats.set(cat, (node.cats.get(cat) || 0) + 1);
  });
  return [...cities.values()]
    .map(node => ({
      city: node.city,
      total: node.total,
      cats: [...node.cats.entries()]
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'ru')),
    }))
    .sort((a, b) => b.total - a.total || a.city.localeCompare(b.city, 'ru'));
}

// Категории набора с числом точек: по частоте, затем по алфавиту — порядок
// легенды не прыгает между перерисовками.
function mapCategories(rows) {
  const counts = new Map();
  (rows || []).forEach(r => {
    if (!r || !r.lat || !r.lon) return;      // без координат точки на карте нет
    const k = mapCatKey(r);
    counts.set(k, (counts.get(k) || 0) + 1);
  });
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'ru'));
}

// Цвет категории — по её месту в списке категорий набора. Одинаковый набор
// даёт одинаковые цвета, а двух одинаковых цветов в легенде не бывает.
function mapCatColor(name, cats) {
  const i = Math.max(0, (cats || []).findIndex(c => c.name === name));
  return MAP_CAT_COLORS[i % MAP_CAT_COLORS.length];
}

// Проходит ли запись через фильтры карты. Чистая функция — на ней держатся
// и метки, и счётчик «показано из», и тесты.
function mapRowVisible(r, opts) {
  const o = opts || {};
  if (!r || !r.lat || !r.lon) return false;
  if (o.hidden && o.hidden.has(mapHideKey(r))) return false;
  const q = String(o.search || '').trim().toLowerCase();
  if (q && !String(r.name || '').toLowerCase().includes(q)) return false;
  if (o.minReviews && (parseFloat(r.reviews_count) || 0) < o.minReviews) return false;
  if (o.minScore && (parseFloat(r.lead_score) || 0) < o.minScore) return false;
  // «Сайт» — и своя страница, и визитка-таплинк: обе ведут клиента наружу.
  const hasSite = !!(String(r.website || '').trim() || String(r.aggregator_url || '').trim());
  if (o.siteMode === 'with' && !hasSite) return false;
  if (o.siteMode === 'without' && hasSite) return false;
  // «Только новые»: признак ставит сервер тем же сравнением, что и фильтр
  // таблицы — организации не было в файлах прошлых поисков.
  if (o.onlyNew && r._is_new !== true) return false;
  return true;
}

function mapFilterState() {
  return {
    hidden: mapHiddenCats,
    search: mapSearch,
    minReviews: mapMinReviews,
    minScore: mapMinScore,
    siteMode: mapSiteMode,
    onlyNew: mapOnlyNew,
  };
}

function mapVisibleRows(rows) {
  const opts = mapFilterState();
  return (rows || []).filter(r => mapRowVisible(r, opts));
}

// Круглая цветная точка вместо стандартной синей капли: цвет — категория,
// и он же повторяется в бейдже попапа.
function mapPinIcon(color) {
  return L.divIcon({
    className: 'map-pin',
    html: `<span class="map-pin-dot" style="--pin:${color}"></span>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -10],
  });
}

// Подробности метки: то, по чему решают звонить, — категория, рейтинг с
// числом отзывов, адрес, телефоны, страница и соцсети. Значения идут
// основным тоном текста, бледным — только подписи: в прежнем попапе адрес и
// телефон были светло-серыми и на белой подложке почти не читались.
function mapPopupHtml(r, color) {
  const rating = typeof scoreRating === 'function' ? scoreRating(r) : (parseFloat(r.rating) || 0);
  const reviews = Math.round(parseFloat(r.reviews_count) || 0);
  const meta = [];
  if (rating > 0) meta.push(`Рейтинг ${rating}`);
  if (reviews > 0) meta.push(`${reviews} ${pluralNum(reviews, 'отзыв', 'отзыва', 'отзывов')}`);
  const score = r.lead_score;
  const site = String(r.aggregator_url || r.website || '').trim();
  const phones = String(r.phone || '').split(',').map(s => s.trim()).filter(Boolean).slice(0, 3);
  const extra = mapCatExtra(r);
  const socials = typeof SOCIALS === 'object' && SOCIALS
    ? Object.entries(SOCIALS)
      .filter(([p]) => r[p])
      .map(([p, c]) => `<a class="map-soc" style="--tile:${c}" href="${escapeHtml(safeUrl(r[p]))}"`
        + ` target="_blank" rel="noopener noreferrer">${SLABELS[p]}</a>`)
      .join('')
    : '';
  return `
    <div class="map-pop" style="--pin:${color}">
      <div class="map-pop-cat">${escapeHtml(mapCatKey(r))}</div>
      <div class="map-pop-name">${escapeHtml(r.name || 'Без названия')}</div>
      ${extra ? `<div class="map-pop-extra">Ещё: ${escapeHtml(extra)}</div>` : ''}
      ${meta.length ? `<div class="map-pop-meta">${escapeHtml(meta.join(' · '))}</div>` : ''}
      ${r.address ? `<div class="map-pop-row"><span class="map-pop-key">Адрес</span>${escapeHtml(r.address)}</div>` : ''}
      ${phones.length ? `<div class="map-pop-row"><span class="map-pop-key">Телефон</span>${escapeHtml(phones.join(', '))}</div>` : ''}
      ${site ? `<div class="map-pop-row"><span class="map-pop-key">Сайт</span>`
        + `<a href="${escapeHtml(safeUrl(site))}" target="_blank" rel="noopener noreferrer">${escapeHtml(site)}</a></div>` : ''}
      ${score !== '' && score != null ? `<div class="map-pop-row"><span class="map-pop-key">Оценка лида</span>${escapeHtml(String(score))} из 100</div>` : ''}
      ${socials ? `<div class="map-pop-soc">${socials}</div>` : ''}
      <div class="map-pop-links">
        ${r.yandex_maps_url ? `<a href="${escapeHtml(safeUrl(r.yandex_maps_url))}" target="_blank" rel="noopener noreferrer">Открыть на Я.Картах ↗</a>` : ''}
      </div>
    </div>`;
}

function initMap() {
  const container = document.getElementById('map-container');
  if (!container) return;
  // Страховка от двойного входа: прежнюю карту снимаем сами, иначе Leaflet
  // откажется создавать новую на том же контейнере.
  if (leafMap) {
    try { leafMap.remove(); } catch (e) {}
    leafMap = null;
  }
  const pts = allResults.filter(r => r.lat && r.lon);
  if (!pts.length) {
    // Два разных «пусто»: данных вовсе нет и данные есть, но файл собран без
    // колонок Широта/Долгота — без подсказки пустая карта выглядит поломкой.
    const msg = allResults.length
      ? 'Координат в этом файле нет: колонки «Широта/Долгота» пишутся с версии 2.3.5. '
        + 'Запустите новый поиск — по нему карта покажет точки.'
      : 'Карта пуста: точек пока нет — они появятся после поиска.';
    container.innerHTML = `<div class="no-data" style="padding:60px">${msg}</div>`;
    mapInited = false;
    renderMapPanel();
    return;
  }

  // Подсказка «Загружаю карту…» живёт в том же контейнере: Leaflet сносит
  // содержимое только при повторном создании, поэтому очищаем сами.
  container.innerHTML = '';
  leafMap = L.map(container).setView([parseFloat(pts[0].lat), parseFloat(pts[0].lon)], 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {attribution:'© OpenStreetMap contributors', maxZoom:19}).addTo(leafMap);
  mapLayer = L.layerGroup().addTo(leafMap);
  mapInited = true;
  renderMapMarkers(true);
}

// Метки пересобираются внутри уже созданной карты. Подгонка вида (fit) — только
// когда сменился набор данных: при выборе категории или отзывов карта не имеет
// права прыгать, человек уже выбрал место и масштаб, а нажал лишь фильтр.
function renderMapMarkers(fit) {
  const rows = mapVisibleRows(allResults);
  const cats = mapCategories(allResults);
  const latLngs = [];
  if (leafMap && mapLayer) {
    mapLayer.clearLayers();
    rows.forEach(r => {
      const lat = parseFloat(r.lat), lon = parseFloat(r.lon);
      if (isNaN(lat) || isNaN(lon)) return;
      const color = mapCatColor(mapCatKey(r), cats);
      L.marker([lat, lon], { icon: mapPinIcon(color), title: r.name || '' })
        .addTo(mapLayer)
        .bindPopup(mapPopupHtml(r, color))
        .bindTooltip(escapeHtml(r.name || ''), { direction: 'top', offset: [0, -10] });
      latLngs.push([lat, lon]);
    });
    if (fit && latLngs.length) leafMap.fitBounds(L.latLngBounds(latLngs).pad(0.1));
  }
  const empty = document.getElementById('map-empty');
  if (empty) empty.hidden = rows.length > 0;
  renderMapPanel();
}

// Легенда и счётчик «показано из»: легенда — список кнопок, а не чекбоксов,
// потому что это переключатели видимости, и aria-pressed говорит о ней прямо.
function renderMapPanel() {
  const cats = mapCategories(allResults);
  const rows = mapVisibleRows(allResults);
  const total = allResults.filter(r => r.lat && r.lon).length;
  const shown = document.getElementById('map-shown');
  if (shown) shown.textContent = `${rows.length} из ${total}`;
  const box = document.getElementById('map-cats');
  if (!box) return;
  // Несколько городов — легенда делится по городам: «Кафе» в Ярославле и в
  // Москве — разные строки, и скрыть их можно по отдельности. Один город
  // (или его нет) — обычный список без лишнего заголовка.
  const groups = mapCityGroups(allResults);
  const withCities = groups.length > 1;
  box.innerHTML = groups.map(g => {
    const items = g.cats.map(c => {
      const off = mapHiddenCats.has(mapCatHideKey(g.city, c.name));
      return `<button type="button" class="map-cat${off ? ' off' : ''}"`
        + ` data-city="${escapeHtml(g.city)}" data-cat="${escapeHtml(c.name)}"`
        + ` style="--cat:${mapCatColor(c.name, cats)}"`
        + ` aria-pressed="${off ? 'false' : 'true'}"`
        + ` title="${off ? 'Показать на карте' : 'Скрыть с карты'}: ${escapeHtml(c.name)}`
        + `${withCities ? ' · ' + escapeHtml(g.city) : ''}"`
        + ` onclick="mapToggleCat(this.dataset.city, this.dataset.cat)">`
        + '<span class="map-cat-dot" aria-hidden="true"></span>'
        + `<span class="map-cat-name">${escapeHtml(c.name)}</span>`
        + `<span class="map-cat-count">${c.count}</span></button>`;
    }).join('');
    const head = withCities
      ? `<div class="map-city"><span class="map-city-name">${escapeHtml(g.city)}</span>`
        + `<span class="map-city-count">${g.total}</span></div>`
      : '';
    return `<div class="map-city-group">${head}${items}</div>`;
  }).join('') || '<div class="map-cats-empty">Категорий пока нет — запустите поиск или откройте прошлый файл.</div>';
}

// Город и категория обязательны вместе: так одна и та же категория в разных
// городах скрывается отдельно.
function mapToggleCat(city, cat) {
  if (!cat) return;
  const key = mapCatHideKey(city || 'Без города', cat);
  if (mapHiddenCats.has(key)) mapHiddenCats.delete(key);
  else mapHiddenCats.add(key);
  renderMapMarkers();
}

function mapAllCats(show) {
  if (show) mapHiddenCats.clear();
  else mapCityGroups(allResults).forEach(g => g.cats.forEach(c => {
    mapHiddenCats.add(mapCatHideKey(g.city, c.name));
  }));
  renderMapMarkers();
}

function mapOnSearchInput(el) {
  mapSearch = (el && el.value) || '';
  renderMapMarkers();
}

// Фильтры читаются из полей целиком: так одно состояние (mapSiteMode и др.)
// не расходится с тем, что видно в панели после перерисовки.
function mapReadFilters() {
  const rev = document.getElementById('map-reviews');
  if (rev) mapMinReviews = parseInt(rev.value, 10) || 0;
  const site = document.getElementById('map-site');
  if (site) mapSiteMode = site.value || 'all';
  const score = document.getElementById('map-score');
  if (score) mapMinScore = parseInt(score.value, 10) || 0;
  const newest = document.getElementById('map-only-new');
  if (newest) mapOnlyNew = !!newest.checked;
  renderMapMarkers();
}

// Набор данных сменился — открыли файл из «Истории», переключили срез или
// пришёл новый прогон. Маркеры принадлежат прежнему набору, поэтому карту
// собираем заново: без этого при открытии прошлых файлов на карте висели
// точки другого поиска (или пусто, если карта один раз построилась раньше).
function resetMapView() {
  mapHiddenCats = new Set();
  mapSearch = '';
  mapMinReviews = 0;
  mapMinScore = 0;
  mapSiteMode = 'all';
  mapOnlyNew = false;
  // Поля возвращаются к значениям по умолчанию, а не к пустой строке: пустой
  // select выглядел бы сломанным (нет выбранного пункта вообще).
  const search = document.getElementById('map-search');
  if (search) search.value = '';
  const defaults = { 'map-reviews': '0', 'map-site': 'all', 'map-score': '0' };
  Object.keys(defaults).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = defaults[id];
  });
  const newest = document.getElementById('map-only-new');
  if (newest) newest.checked = false;
  mapInited = false;
  mapLayer = null;
  if (leafMap) {
    try { leafMap.remove(); } catch (e) {}
    leafMap = null;
  }
  const container = document.getElementById('map-container');
  if (container) container.innerHTML = '';
}

// Если карта открыта прямо сейчас — пересобираем сразу, иначе человек видел бы
// пустой прямоугольник до следующего переключения вкладки.
function syncMapWithResults() {
  resetMapView();
  const panel = document.getElementById('p-map');
  if (panel && panel.classList && panel.classList.contains('active') && allResults.length) {
    ensureMapReady();
  } else if (typeof renderMapPanel === 'function') {
    // Легенда живёт в той же панели: после смены набора она должна показать
    // категории нового среза, даже если карта ещё ни разу не открыта.
    renderMapPanel();
  }
}

// ═══════════════════════════════════════════
//  Stats
// ═══════════════════════════════════════════
const CAT_COLORS = ['#1A6B3C','#2980b9','#8e44ad','#c0392b','#d35400','#16a085','#2c3e50','#27ae60','#f39c12','#7f8c8d'];

// ═══════════════════════════════════════
//  Default stats (always visible, even before the first search)
// ═══════════════════════════════════════
function renderDefaultStats() {
  const body = document.getElementById('stats-body');
  if (!body) return;
  body.innerHTML = `
    <div class="stat-cards">
      <div class="stat-card"><div class="num">0</div><div class="lbl">Всего найдено</div></div>
      <div class="stat-card"><div class="num">0</div><div class="lbl">С соцсетями</div></div>
      <div class="stat-card"><div class="num">—</div><div class="lbl">Время</div></div>
    </div>
    ${statsEmptyArtHTML()}
    <div class="stat-section">
      <h3>По соцсетям</h3>
      <div class="no-data" style="padding:18px 12px">Данные появятся после запуска поиска</div>
    </div>
    <div class="stat-section">
      <h3>Топ категорий</h3>
      <div class="no-data" style="padding:18px 12px">Данные появятся после запуска поиска</div>
    </div>`;
}

// Одна карточка статистики: заголовок и свой разбор внутри. Сетка из таких
// карточек заменяет длинную колонку секций — вкладка читается по блокам,
// а не как один сплошной список.
function statsPanelHTML(title, body, cls) {
  return `<section class="stats-panel${cls ? ' ' + cls : ''}">
      <h3>${title}</h3>
      ${body}
    </section>`;
}

// Shared bar renderer for the stats sections. Bars are normalized against
// the MAXIMUM value (not the record total), so the largest bar is always
// full width and small values stay comparable. Tiny counts (<3) get a
// minimal 5px bar so they stay visible; the exact number is in the tail.
function barRows(rows) {
  if (!rows || !rows.length) return '';
  const max = Math.max(...rows.map(r => r.count)) || 1;
  return rows.map(r => {
    const pct = Math.max(Math.round(r.count / max * 100), 1);
    const min = r.count < 3 ? 5 : 0;          // px floor for tiny values
    const style = `width:${pct}%;${min ? `min-width:${min}px;` : ''}background:${r.color}`;
    return `
        <div class="bar-row">
          <div class="bar-lbl" title="${escapeHtml(r.label)}">${escapeHtml(r.label)}</div>
          <div class="bar-track"><div class="bar-fill" style="${style}"></div></div>
          <div class="bar-val">${r.count}</div>
        </div>`;
  }).join('');
}

// Кольцевая диаграмма для долей (соцсети): SVG-окружности со штрих-даш-
// массивом. Радиус 70 при ободе 16 — центр свободен под итог. Доли < 0.5%
// сливаются с дорожкой, поэтому каждая дуга получает минимум 0.5%. Одна
// соцсеть — полное кольцо (окружность целиком, а не 100%-dash). Точные
// значения — только в легенде: подписи внутри секторов сливались с соседней
// дугой и наезжали на край кольца.
function donutHTML(rows, centerLabel) {
  if (!rows || !rows.length) return '';
  const total = rows.reduce((s, r) => s + r.count, 0) || 1;
  const C = 2 * Math.PI * 70;
  let offset = 0;
  const arcs = rows.map(r => {
    const frac = r.count / total;
    const len = Math.max(frac * C, 0.005 * C);
    const dash = `${len} ${C - len}`;
    const el = `<circle class="donut-arc" cx="84" cy="84" r="70"`
      + ` stroke="${r.color}" stroke-dasharray="${dash}"`
      + ` style="--dash-rest:${(C - len).toFixed(1)}"`
      + ` stroke-dashoffset="${-offset}" stroke-linecap="butt"`
      + ` title="${escapeHtml(r.label)}: ${r.count}"></circle>`;
    offset += frac * C;
    return el;
  }).join('');
  const single = rows.length === 1
    ? `<circle class="donut-arc" cx="84" cy="84" r="70" stroke="${rows[0].color}"`
      + ` title="${escapeHtml(rows[0].label)}: ${rows[0].count}"></circle>`
    : arcs;
  const legend = rows.map(r => `
      <div class="donut-legend-row">
        <i class="donut-swatch" style="background:${r.color}"></i>
        <span title="${escapeHtml(r.label)}">${escapeHtml(r.label)}</span>
        <b>${r.count} · ${Math.round(r.count / total * 100)}%</b>
      </div>`).join('');
  return `<div class="donut-wrap">`
    + `<div class="donut"><svg width="168" height="168" viewBox="0 0 168 168" aria-hidden="true">`
    + `<circle class="donut-track" cx="84" cy="84" r="70"></circle>${single}</svg>`
    + `<div class="donut-center"><b>${_fmtCount(total)}</b>`
    + `<span>${escapeHtml(centerLabel || '')}</span></div></div>`
    + `<div class="donut-legend">${legend}</div></div>`;
}

// ═══════════════════════════════════════════
//  Графики по качеству данных: рейтинг, лиды, полнота
// ═══════════════════════════════════════════
// Те же .bar-row, что и «Топ категорий», но цвета — токены темы
// (var(--…)): светлая и тёмная темы получают свои оттенки бесплатно.
// Пороги лидов — те же 70/45, что у бейджа в таблице (scoreHTML).
const RATING_BUCKETS = [
  {label: '5,0',        min: 5,    color: 'var(--grn)'},
  {label: '4,5 – 4,9',  min: 4.5,  color: 'var(--blu)'},
  {label: '4,0 – 4,4',  min: 4,    color: 'var(--yel)'},
  {label: 'ниже 4,0',   min: 0.01, color: 'var(--red)'},
];
const LEAD_BUCKETS = [
  {label: 'Горячие, 70+',   min: 70, color: 'var(--grn)'},
  {label: 'Тёплые, 45–69',  min: 45, color: 'var(--yel)'},
  {label: 'Холодные, 0–44', min: 0,  color: 'var(--blu)'},
];

// Строки для полос «Распределения рейтинга». Оценка в записях бывает
// строкой с запятой («4,6») или шкалой 0..50 — нормализация та же, что
// у балла лида (scoreRating). null — если оценок нет вовсе: секция тогда
// не рисуется, а не пустует заглушкой.
function ratingBucketRows(data) {
  const counts = RATING_BUCKETS.map(() => 0);
  let rated = 0;
  for (const r of data) {
    const v = scoreRating(r);
    if (!(v > 0)) continue;
    rated++;
    for (let i = 0; i < RATING_BUCKETS.length; i++) {
      if (v >= RATING_BUCKETS[i].min) { counts[i]++; break; }
    }
  }
  if (!rated) return null;
  const rows = RATING_BUCKETS
    .map((b, i) => ({label: b.label, count: counts[i], color: b.color}))
    .filter(r => r.count > 0);
  const none = data.length - rated;
  if (none) rows.push({label: 'Без оценки', count: none, color: 'var(--muted)'});
  return rows;
}

// { rows, hot } — сегменты «Готовности лидов» и сколько горячих (≥70).
// Записи без lead_score (старые файлы) живут отдельной серой полосой.
function leadBucketRows(data) {
  const counts = LEAD_BUCKETS.map(() => 0);
  let scored = 0;
  for (const r of data) {
    if (r.lead_score == null || r.lead_score === '') continue;
    scored++;
    const v = +r.lead_score || 0;
    for (let i = 0; i < LEAD_BUCKETS.length; i++) {
      if (v >= LEAD_BUCKETS[i].min) { counts[i]++; break; }
    }
  }
  if (!scored) return null;
  const rows = LEAD_BUCKETS
    .map((b, i) => ({label: b.label, count: counts[i], color: b.color}))
    .filter(r => r.count > 0);
  const none = data.length - scored;
  if (none) rows.push({label: 'Не оценены', count: none, color: 'var(--muted)'});
  return {rows, hot: counts[0]};
}

// Полнота данных: какая доля записей заполнена по каждому полю. Строки
// показываются только для ВКЛЮЧЁННЫХ полей («Что парсить»): ноль у
// выключенного поля — не пробел данных, а выбор пользователя.
function coverageRows(data) {
  const fields = (typeof parseFieldsEnabled === 'function') ? parseFieldsEnabled() : null;
  const on = k => !fields || fields.has(k);
  const socOn = (typeof socialsEnabled === 'function') ? socialsEnabled() : true;
  const defs = [
    {show: on('phone'),          label: 'Телефон',         test: r => !!String(r.phone || '').trim()},
    {show: on('aggregator_url'), label: 'Сайт / Таплинк',  test: r => !!String(r.website || r.aggregator_url || '').trim()},
    {show: socOn,                label: 'Соцсети',         test: r => Object.keys(SOCIALS).some(p => r[p])},
    {show: on('rating'),         label: 'Рейтинг',         test: r => scoreRating(r) > 0},
  ];
  const total = data.length || 1;
  return defs.filter(d => d.show)
             .map(d => ({label: d.label, count: data.filter(d.test).length, total}));
}

// Полосы в процентах от ВСЕХ записей (не от максимума, как в категориях):
// шкала тут — «сколько заполнено», и 100% должно быть во всю дорожку.
function pctBarRows(rows) {
  return rows.map(r => {
    const pct = Math.round(r.count / (r.total || 1) * 100);
    return `
        <div class="bar-row">
          <div class="bar-lbl">${escapeHtml(r.label)}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:var(--c)"></div></div>
          <div class="bar-val">${pct}%</div>
        </div>`;
  }).join('');
}

function ratingSectionHTML(data) {
  const rows = ratingBucketRows(data);
  if (!rows) return '';
  return statsPanelHTML('Распределение рейтинга', barRows(rows));
}

function leadSectionHTML(data) {
  const info = leadBucketRows(data);
  if (!info) return '';
  return statsPanelHTML('Готовность лидов', barRows(info.rows));
}

function coverageSectionHTML(data) {
  const rows = coverageRows(data);
  if (!rows.length) return '';
  return statsPanelHTML('Полнота данных', pctBarRows(rows));
}

// «Новые организации»: сколько записей текущего прогона не встречалось в
// прошлых файлах. Сервер ставит каждой записи `_is_new` (true/false), а
// `null` — сравнивать не с чем: нет маркера старта текущего поиска. Долю
// считаем от записей с известным статусом; если таких нет — null, иначе
// «0%» на экране читалось бы как «всё повторное», хотя сравнения не было.
function newShare(data) {
  let fresh = 0, known = 0;
  for (const r of data) {
    if (!r) continue;
    if (r._is_new === true) { fresh++; known++; }
    else if (r._is_new === false) known++;
  }
  if (!known) return null;
  return {fresh, repeat: known - fresh, known, pct: Math.round(fresh / known * 100)};
}

// Одна полоса на две доли: новые слева, повторные справа. Цифры дублируются
// в легенде — полоса декоративна (aria-label), читается и без неё.
function newSectionHTML(data) {
  const s = newShare(data);
  if (!s) return '';
  const repeatPct = 100 - s.pct;
  return statsPanelHTML('Новые организации', `<div class="new-split">
        <div class="new-split-head"><b>${s.pct}%</b><span>${s.fresh} из ${s.known} не встречались в прошлых прогонах</span></div>
        <div class="new-split-bar" role="img" aria-label="Новые — ${s.pct}%, уже встречались — ${repeatPct}%">
          <span class="new-split-fresh" style="width:${s.pct}%"></span>
          <span class="new-split-repeat" style="width:${repeatPct}%"></span>
        </div>
        <div class="new-split-legend">
          <span class="new-split-item"><i class="new-split-dot fresh"></i>Новые<b>${s.fresh} · ${s.pct}%</b></span>
          <span class="new-split-item"><i class="new-split-dot repeat"></i>Уже встречались<b>${s.repeat} · ${repeatPct}%</b></span>
        </div>
      </div>
    `);
}

// Пустая «Статистика»: столбцы и тренд — та же идея, что в онбординге,
// но в статистическом ключе. Декоративна (aria-hidden): вся информация —
// в тексте рядом.
function statsEmptyArtHTML() {
  return `<svg viewBox="0 0 120 64" class="sta-art" aria-hidden="true" focusable="false">`
    + `<rect x="14" y="34" width="14" height="24" rx="3" class="sta-col"/>`
    + `<rect x="38" y="24" width="14" height="34" rx="3" class="sta-col"/>`
    + `<rect x="62" y="12" width="14" height="46" rx="3" class="sta-col-hi"/>`
    + `<path d="M84 46l9-11 6 6 11-17" class="sta-line"/>`
    + `<circle cx="110" cy="24" r="3" class="sta-dot"/>`
    + `</svg>`;
}

// Одна точка обновления вкладки «Статистика». Набор данных сменился — новый
// прогон, другой срез или открытый из истории файл — карточки должны считать
// его, а не прошлый поиск. Без записей возвращаем нули: старые цифры на
// пустом наборе читаются как «файл не открылся».
function refreshStatsFor(rows) {
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) {
    if (typeof renderDefaultStats === 'function') renderDefaultStats();
    return;
  }
  renderStats(list,
    typeof _runElapsed === 'function' ? _runElapsed() : null,
    typeof _lastSkippedCities !== 'undefined' ? _lastSkippedCities : []);
}

function renderStats(data, elapsed, skippedCities) {
  if (!data.length) return;
  const total  = data.length;
  // Соцсети могли не собираться вовсе («Что парсить») — тогда и статистики
  // по соцсетям быть не должно.
  const socOn  = (typeof socialsEnabled === 'function') ? socialsEnabled() : true;
  const withSo = data.filter(r => Object.keys(SOCIALS).some(p => r[p])).length;
  const dur    = elapsed ? (elapsed < 60 ? elapsed.toFixed(0)+'с' : (elapsed/60).toFixed(1)+'м') : '—';

  const cards = [
    {num: total,   lbl: 'Всего найдено'},
    {num: dur,     lbl: 'Время'},
  ];
  if (socOn) cards.splice(1, 0, {num: withSo, lbl: 'С соцсетями'});
  // Доля новых — итог прогона наравне с «Всего»: сразу видно, дал ли
  // повторный поиск свежие организации или только дубли.
  const fresh = newShare(data);
  if (fresh) {
    cards.splice(1, 0, {num: fresh.pct + '%', lbl: 'Новых',
      tip: `Организаций, которых не было в прошлых прогонах: ${fresh.fresh} из ${fresh.known}`});
  }
  // Качество данных — тоже итог: средняя оценка и горячие лиды читаются
  // одним взглядом, без прокрутки к полосам ниже.
  const rated = data.filter(r => scoreRating(r) > 0);
  if (rated.length) {
    const avg = rated.reduce((s, r) => s + scoreRating(r), 0) / rated.length;
    cards.splice(cards.length - 1, 0, {num: avg.toFixed(1).replace('.', ','), lbl: 'Средний рейтинг'});
  }
  const leadInfo = leadBucketRows(data);
  if (leadInfo && leadInfo.hot) {
    cards.splice(cards.length - 1, 0, {num: leadInfo.hot, lbl: 'Горячих лидов'});
  }

  const socialKeys = Object.keys(SOCIALS);
  const hasSocial = r => socialKeys.some(p => r[p]);

  // Socials breakdown (overall, all cities)
  const socialCounts = socialKeys.map(p => ({
    name: SLABELS[p], count: data.filter(r => r[p]).length, color: SOCIALS[p]
  })).filter(s => s.count > 0).sort((a,b) => b.count - a.count);

  // Categories
  const catMap = {};
  data.forEach(r => (r.category||'').split(',').forEach(c => {
    const t = c.trim(); if (t) catMap[t] = (catMap[t]||0) + 1;
  }));
  const cats = Object.entries(catMap).sort((a,b)=>b[1]-a[1]).slice(0,10);

  // Per-city breakdown — records carry a city stamp from the backend.
  const byCity = {};
  data.forEach(r => {
    const c = (r.city || '').trim() || '—';
    (byCity[c] = byCity[c] || []).push(r);
  });
  const cityNames = Object.keys(byCity).filter(c => c !== '—');
  const cityCardsHtml = cityNames.length > 0 ? `<div class="stat-city-grid">`
    + cityNames.map(name => {
      const cd = byCity[name];
      const cityTotal = cd.length;
      const cityWithSo = cd.filter(hasSocial).length;
      const citySocials = socialKeys
        .map(p => ({p, count: cd.filter(r => r[p]).length}))
        .filter(s => s.count > 0)
        .sort((a,b) => b.count - a.count)
        .slice(0, 6);
      const chips = citySocials.length
        ? `<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:3px">`
          + citySocials.map(s => `<span style="background:${SOCIALS[s.p]};color:#fff;border-radius:10px;font-size:12px;padding:1px 6px;font-weight:600">${SLABELS[s.p]} ${s.count}</span>`).join('')
          + `</div>`
        : '';
      return `<div class="stat-city-card">
        <h4>${escapeHtml(name)}</h4>
        <div class="stat-mini-row"><span>Всего</span><span>${cityTotal}</span></div>
        ${socOn ? `<div class="stat-mini-row"><span>С соцсетями</span><span>${cityWithSo}</span></div>
        <div class="stat-mini-row"><span>Без соцсетей</span><span>${cityTotal - cityWithSo}</span></div>
        ${chips}` : ''}
      </div>`;
    }).join('') + `</div>` : '';


  // Show skipped cities if any
  let skippedHtml = '';
  if (skippedCities && skippedCities.length > 0) {
    skippedHtml = `<div class="stat-city-grid">`;
    skippedCities.forEach(sc => {
      skippedHtml += `<div class="stat-city-card" style="border-left:3px solid rgba(100,140,200,.6)">
        <h4>${escapeHtml(sc.name)}</h4>
        <div class="stat-mini-row"><span>Статус</span><span style="color:rgba(100,140,200,1)">Пропущен</span></div>
        <div class="stat-mini-row"><span>Записей собрано</span><span>${sc.records_found}</span></div>
      </div>`;
    });
    skippedHtml += `</div>`;
  }

  // Сетка карточек: три в ряд на широком экране. Разбивки больше не идут
  // одной длинной колонкой — каждая живёт в своей карточке, и вкладка
  // читается блоками. «Аналитика» (RPS, кэш) убрана: это служебные числа,
  // они не помогают выбрать бизнес для письма.
  const catBody = cats.length
    ? barRows(cats.map(([name, cnt], i) => ({label: name, count: cnt, color: CAT_COLORS[i%CAT_COLORS.length]})))
    : '<div class="no-data" style="padding:16px 12px">В этих записях категории не заполнены</div>';
  const socialBody = (socOn && socialCounts.length)
    ? donutHTML(socialCounts.map(s => ({label: s.name, count: s.count, color: s.color})), 'записей')
    : '<div class="no-data" style="padding:16px 12px">' + (socOn ? 'В этих записях соцсети не найдены' : 'Соцсети отключены в «Что парсить»') + '</div>';

  const panels = [
    cityCardsHtml ? statsPanelHTML('По городам', cityCardsHtml, 'stats-panel-cities') : '',
    statsPanelHTML('Топ категорий', catBody),
    statsPanelHTML('По соцсетям', socialBody),
    ratingSectionHTML(data),
    leadSectionHTML(data),
    coverageSectionHTML(data),
    newSectionHTML(data),
    skippedHtml ? statsPanelHTML('⏭ Пропущенные города', skippedHtml) : '',
  ].filter(Boolean).join('');

  const body = document.getElementById('stats-body');
  if (!body) return;
  body.innerHTML = `
    <div class="stat-cards">${cards.map(c =>
      `<div class="stat-card"${c.tip ? ` title="${escapeHtml(c.tip)}"` : ''}><div class="num">${c.num}</div><div class="lbl">${c.lbl}</div></div>`
    ).join('')}</div>
    <div class="stats-grid">${panels}</div>`;
  // «По городам»: в панели видно две карточки, остальные листаются внутри
  // неё. Высоту берём по самим карточкам: у города с соцсетями строка чипов
  // делает карточку выше, и фиксированное число обрезало бы её посередине.
  const cityGrid = body.querySelector('.stats-panel-cities .stat-city-grid');
  if (cityGrid && cityGrid.children.length > 2) {
    cityGrid.classList.add('is-scroll');
    const gap = parseFloat(getComputedStyle(cityGrid).rowGap) || 0;
    const two = cityGrid.children[0].offsetHeight + cityGrid.children[1].offsetHeight + gap;
    // 0 — панель ещё скрыта (вкладка не открыта): не загоняем список в ноль,
    // при открытии вкладки renderStats пересчитает высоту уже на месте.
    if (two > 0) cityGrid.style.maxHeight = two + 'px';
  }
  // Свежие файлы и отметки могли появиться только что — обновляем динамику,
  // но не во время прогона: там renderStats зовётся каждые 1.5 с, а обход
  // папки с пересчётом строк дешевле не становится.
  if (!isRunActive()) loadDailyDynamics();
}

// ═══════════════════════════════════════════
//  «Динамика по дням» (вкладка «Статистика»)
