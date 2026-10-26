// ═══════════════════════════════════════════
//  Сферы бизнеса: готовые запросы + история по сферам
//
//  Зачем: думать сферой («стоматология») проще, чем словами для поиска, а
//  Яндекс.Карты на «стоматология» и «зубной врач» отдают разные карточки.
//  Каталог приходит с сервера (/spheres), история — оттуда же: она собрана
//  из общей истории поиска, поэтому очистка «Истории» очищает и подписи.
//
//  Список открывается при фокусе в поле «Кого будем искать?». Кнопка
//  «Сферы» открывает редактор каталога: добавить сферу, поменять название
//  и слова. Показываем сразу, когда сферу парсили и по каким городам —
//  чтобы не гонять один и тот же город дважды.
// ═══════════════════════════════════════════

let _spheresCatalog = null;      // [{id, name, icon, queries}] — null, ещё не грузили
let _spheresHistory = {};        // id → {last_ts, cities, runs, results}
let _spheresPromise = null;
let _spheresLoadedAt = 0;

// 5 минут: история меняется только после прогона, чаще запрашивать незачем.
const SPHERES_TTL_MS = 5 * 60 * 1000;

function loadSpheres(force = false) {
  const fresh = _spheresCatalog && (Date.now() - _spheresLoadedAt < SPHERES_TTL_MS);
  if (fresh && !force) return Promise.resolve(_spheresCatalog);
  if (_spheresPromise) return _spheresPromise;
  _spheresPromise = fetch('/spheres')
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data || !data.ok) return _spheresCatalog || [];
      _spheresCatalog = Array.isArray(data.spheres) ? data.spheres : [];
      _spheresHistory = {};
      for (const h of (data.history || [])) {
        if (h && h.id) _spheresHistory[h.id] = h;
      }
      _spheresLoadedAt = Date.now();
      return _spheresCatalog;
    })
    .catch(() => _spheresCatalog || [])
    .finally(() => { _spheresPromise = null; });
  return _spheresPromise;
}

// 41 запуск / 2 запуска / 5 запусков — иначе подпись читается как опечатка.
function _runsWord(n) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'запуск';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'запуска';
  return 'запусков';
}

// «🕒 17.10.2026 · Москва, Казань · 3 запуска» либо «ещё не парсили».
function sphereHistoryLine(id) {
  const h = _spheresHistory[id];
  if (!h || !h.last_ts) return 'ещё не парсили';
  const d = new Date(h.last_ts * 1000).toLocaleDateString('ru-RU');
  const cities = (h.cities || []).filter(Boolean);
  const more = (h.cities_total || 0) > cities.length ? ` +${h.cities_total - cities.length}` : '';
  const where = cities.length ? cities.join(', ') + more : 'города не записаны';
  const runs = h.runs > 1 ? ` · ${h.runs} ${_runsWord(h.runs)}` : '';
  return `🕒 ${d} · ${where}${runs}`;
}

function _sphereSortKey(s) {
  const h = _spheresHistory[s.id];
  // Сначала недавно парсенные, затем ни разу не тронутые по алфавиту:
  // так повторный прогон по знакомой сфере виден сразу.
  return h && h.last_ts ? -h.last_ts : Number.MAX_SAFE_INTEGER;
}

function renderSphereDropdown() {
  const dd = document.getElementById('sphere-dropdown');
  if (!dd) return;
  const list = (_spheresCatalog || []).slice().sort((a, b) => {
    if (a.id === b.id) return 0;
    const ka = _sphereSortKey(a), kb = _sphereSortKey(b);
    if (ka !== kb) return ka - kb;
    return a.name.localeCompare(b.name, 'ru');
  });
  if (!list.length) {
    dd.innerHTML = '<div class="sphere-empty">Сферы не загрузились — проверьте соединение с приложением</div>';
    return;
  }
  dd.innerHTML = list.map(s => {
    const hist = sphereHistoryLine(s.id);
    const title = `${s.name}: ${(s.queries || []).join(', ')} · ${hist}`;
    return `<div class="city-option sphere-option" role="option" tabindex="0"
      data-sphere="${escapeHtml(s.id)}" title="${escapeHtml(title)}"
      onclick="applySphere('${s.id}')"
      onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();applySphere('${s.id}');}">
        <div class="city-option-top">
          <span class="city-option-name">${s.icon || '•'} ${escapeHtml(s.name)}</span>
          <span class="city-option-pop">${(s.queries || []).length} ${(s.queries || []).length === 1 ? 'слово' : 'слова'}</span>
        </div>
        <div class="city-option-hist">${escapeHtml(hist)}</div>
      </div>`;
  }).join('');
}

function positionSphereDropdown() {
  const inp = document.getElementById('f-queries');
  const dd = document.getElementById('sphere-dropdown');
  if (!inp || !dd || !dd.classList.contains('open')) return;
  const r = inp.getBoundingClientRect();
  dd.style.position = 'fixed';
  dd.style.top = (r.bottom + 4) + 'px';
  dd.style.left = r.left + 'px';
  dd.style.width = r.width + 'px';
  dd.style.maxHeight = Math.max(160, Math.min(340, window.innerHeight - r.bottom - 16)) + 'px';
  dd.style.zIndex = '9999';
}

// Кнопка «Сферы» больше не открывает тот же список, что и фокус в поле:
// она открывает редактор (добавить сферу, изменить название и слова).
function openSphereDropdown() {
  const dd = document.getElementById('sphere-dropdown');
  if (!dd) return;
  renderSphereDropdown();
  dd.classList.add('open');
  positionSphereDropdown();
}

function closeSphereDropdown() {
  const dd = document.getElementById('sphere-dropdown');

  if (!dd) return;
  dd.classList.remove('open');
}

// Слова сферы, которых ещё нет в поле: «кафе» + сфера «кафе, кофейня» →
// добавляем только «кофейня», чтобы ручной список не терялся.
function sphereWordsToAdd(sphere, current) {
  const norm = s => String(s || '').toLowerCase().replace(/ё/g, 'е')
    .replace(/\s+/g, ' ').trim();
  const have = new Set(String(current || '').split('\n').map(norm).filter(Boolean));
  return (sphere && sphere.queries || []).filter(q => q && !have.has(norm(q)));
}

// Выбор сферы: ДОПИСЫВАЕМ её слова, а не заменяем поле. Дальше обычный
// input-евент — счётчик запросов, сводка настройки и кнопка запуска сами.
function applySphere(id) {
  const sphere = (_spheresCatalog || []).find(s => s.id === id);
  const ta = document.getElementById('f-queries');
  if (!sphere || !ta) return;
  const add = sphereWordsToAdd(sphere, ta.value);
  if (!add.length) {
    closeSphereDropdown();
    ta.focus();
    if (typeof showToast === 'function') showToast('Слова этой сферы уже в поле', 'ok');
    return;
  }
  const head = String(ta.value || '').replace(/\s+$/, '');
  ta.value = (head ? head + '\n' : '') + add.join('\n');
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  closeSphereDropdown();
  ta.focus();
  if (typeof saveSettings === 'function') saveSettings();
}

// ── Редактор сфер ────────────────────────────
function _sphereEditorRow(s) {
  const name = escapeHtml(s.name || '');
  const words = escapeHtml((s.queries || []).join(', '));
  return `<div class="sphere-edit-row" data-id="${escapeHtml(s.id || '')}"
      data-icon="${escapeHtml(s.icon || '')}">
    <input class="sphere-edit-name" type="text" value="${name}"
           placeholder="Название сферы" aria-label="Название сферы">
    <input class="sphere-edit-words" type="text" value="${words}"
           placeholder="слова через запятую" aria-label="Слова для поиска">
    <button type="button" class="sphere-edit-del" title="Удалить сферу"
            aria-label="Удалить сферу ${name}">${UI_ICONS.x}</button>
  </div>`;
}

function _collectSphereRows() {
  const list = document.getElementById('spheres-list');
  if (!list) return [];
  return [...list.querySelectorAll('.sphere-edit-row')].map(row => ({
    id: row.dataset.id || '',
    icon: row.dataset.icon || '',
    name: (row.querySelector('.sphere-edit-name') || {}).value || '',
    queries: String((row.querySelector('.sphere-edit-words') || {}).value || '')
      .split(/[,;\n]/).map(s => s.trim()).filter(Boolean),
  }));
}

function closeSpheresEditor() {
  const overlay = document.getElementById('spheres-overlay');
  if (overlay) overlay.remove();
}

function openSpheresEditor() {
  closeSphereDropdown();   // список и редактор не показываем одновременно
  const existing = document.getElementById('spheres-overlay');
  if (existing) existing.remove();
  loadSpheres().then(() => {
    const overlay = document.createElement('div');
    overlay.id = 'spheres-overlay';
    overlay.className = 'ui-modal-overlay';
    overlay.innerHTML = `
      <div class="ui-modal spheres-modal" role="dialog" aria-modal="true"
           aria-labelledby="spheres-title">
        <h3 class="ui-modal-title" id="spheres-title">Сферы бизнеса</h3>
        <div class="spheres-hint">Название — как сфера называется в списке,
          слова — что именно искать (через запятую). Выбор сферы в поле
          запросов дописывает её слова, не стирая введённое.</div>
        <div class="spheres-list" id="spheres-list">
          ${(_spheresCatalog || []).map(_sphereEditorRow).join('')}
        </div>
        <button type="button" class="btn-sm spheres-add" id="spheres-add">${UI_ICONS.plus}Добавить сферу</button>
        <div class="ui-modal-btns">
          <button type="button" class="btn-sm spheres-reset" onclick="resetSpheresCatalog()"
                  title="Вернуть встроенный набор сфер">Сбросить</button>
          <button type="button" class="m-cancel" onclick="closeSpheresEditor()">Отмена</button>
          <button type="button" class="m-ok" id="spheres-save"
                  onclick="saveSpheresFromEditor()">Сохранить</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const list = overlay.querySelector('#spheres-list');
    overlay.querySelector('#spheres-add').addEventListener('click', () => {
      list.insertAdjacentHTML('beforeend', _sphereEditorRow({ name: '', queries: [] }));
      const rows = list.querySelectorAll('.sphere-edit-row');
      const last = rows[rows.length - 1];
      if (last) last.querySelector('.sphere-edit-name').focus();
    });
    list.addEventListener('click', e => {
      const del = e.target.closest('.sphere-edit-del');
      if (!del) return;
      const row = del.closest('.sphere-edit-row');
      if (row) row.remove();
    });
    overlay.addEventListener('click', e => { if (e.target === overlay) closeSpheresEditor(); });
    overlay.addEventListener('keydown', e => { if (e.key === 'Escape') closeSpheresEditor(); });
    if (typeof modalA11y === 'function') modalA11y(overlay);
  });
}

function saveSpheresFromEditor() {
  const items = _collectSphereRows();
  if (!items.length) {
    if (typeof showToast === 'function') showToast('Оставьте хотя бы одну сферу', 'warn');
    return;
  }
  const btn = document.getElementById('spheres-save');
  if (btn) btn.disabled = true;
  fetch('/spheres', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ spheres: items }),
  })
    .then(r => r.json().catch(() => ({})))
    .then(d => {
      if (!d || !d.ok) {
        if (typeof showToast === 'function') {
          showToast('Не сохранилось: ' + ((d && d.error) || 'сервер не ответил'), 'warn');
        }
        return;
      }
      _spheresCatalog = d.spheres || [];
      _spheresLoadedAt = Date.now();
      closeSpheresEditor();
      const dd = document.getElementById('sphere-dropdown');
      if (dd && dd.classList.contains('open')) renderSphereDropdown();
      if (typeof showToast === 'function') showToast('Сферы сохранены', 'ok');
    })
    .catch(() => {
      if (typeof showToast === 'function') showToast('Не сохранилось: нет связи с приложением', 'warn');
    })
    .finally(() => { if (btn) btn.disabled = false; });
}

function resetSpheresCatalog() {
  fetch('/spheres/reset', { method: 'POST' })
    .then(r => r.json().catch(() => ({})))
    .then(d => {
      if (!d || !d.ok) {
        if (typeof showToast === 'function') showToast('Не удалось сбросить сферы', 'warn');
        return;
      }
      _spheresCatalog = d.spheres || [];
      _spheresLoadedAt = Date.now();
      const list = document.getElementById('spheres-list');
      if (list) list.innerHTML = (_spheresCatalog).map(_sphereEditorRow).join('');
      if (typeof showToast === 'function') showToast('Вернули встроенный набор сфер', 'ok');
    })
    .catch(() => {
      if (typeof showToast === 'function') showToast('Не удалось сбросить сферы', 'warn');
    });
}

function initSpheres() {
  const ta = document.getElementById('f-queries');
  if (!ta || ta.dataset.spheresInit) return;
  ta.dataset.spheresInit = '1';

  // Элемент есть в разметке, но переносим его в <body> и позиционируем
  // fixed — аккордеон обрезает вложенные списки, как было и с городами.
  const dd = document.getElementById('sphere-dropdown');
  if (!dd) return;
  document.body.appendChild(dd);

  // Грузим не при открытии страницы, а при первом фокусе/клике: лишний
  // запрос на старте не нужен, а список всё равно открывается после ответа.
  ta.addEventListener('focus', () => {
    loadSpheres().then(() => openSphereDropdown());
  });
  ta.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeSphereDropdown();
  });

  if (btn) {
    btn.addEventListener('mousedown', e => e.preventDefault());  // не уводим фокус
    btn.addEventListener('click', e => {
      e.preventDefault();
      openSpheresEditor();
    });
  }

  document.addEventListener('mousedown', e => {
    if (!dd.classList.contains('open')) return;
    if (dd.contains(e.target) || e.target === ta || e.target === btn) return;
    closeSphereDropdown();
  });
  window.addEventListener('scroll', positionSphereDropdown, true);
  window.addEventListener('resize', positionSphereDropdown);
}

// Запускаемся после загрузки DOM: модуль подключается последним, а ранняя
// инициализация в 11-app-init.js выполняется раньше этого файла и не видит
// initSpheres (именно из-за этого список не открывался).
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSpheres);
} else {
  initSpheres();
}

// После прогона история изменилась — подписи должны обновиться, но не
// настолько часто, чтобы тянуть /spheres на каждую строку лога.
function refreshSpheresSoon() {
  if (!_spheresCatalog) return;
  _spheresLoadedAt = 0;
  loadSpheres(true).then(() => {
    const dd = document.getElementById('sphere-dropdown');
    if (dd && dd.classList.contains('open')) renderSphereDropdown();
  });
}
