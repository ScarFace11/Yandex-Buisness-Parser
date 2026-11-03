// ═══════════════════════════════════════════
//  «Ещё настройки» и объём сбора
// ═══════════════════════════════════════════
// Сайдбор отвечает на два вопроса: что искать и сколько собирать. Всё
// остальное — что парсить, глубина, фильтры, форматы — живёт в отдельном окне,
// где его ищут, а не на первом экране рядом с обязательными полями.

// Что входит в вариант: название, описание и значения формы. Название и
// описание можно переписать — под свою работу, а не под наши слова.
const EFFORT_DEFAULTS = {
  fast:     { name: 'Быстро',    note: 'первые 20 организаций с города', pages: 1, candidates: 20,  vk: false },
  normal:   { name: 'Обычный',   note: 'две страницы с города',          pages: 2, candidates: 200, vk: false },
  thorough: { name: 'Тщательно', note: 'все страницы и полные карточки', pages: 5, candidates: 600, vk: true },
  custom:   { name: 'Своё',      note: 'ваши настройки — откройте шестерёнку', pages: 2, candidates: 200, vk: false },
};
const EFFORT_ORDER = ['fast', 'normal', 'thorough', 'custom'];
const EFFORT_STORE = 'effort-presets';
let _editingEffort = null;

function currentEffort() {
  try {
    const saved = localStorage.getItem('search-effort');
    return EFFORT_ORDER.includes(saved) ? saved : 'normal';
  } catch (e) { return 'normal'; }
}

function loadEffortPresets() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(EFFORT_STORE) || '{}') || {}; }
  catch (e) { saved = {}; }
  const map = {};
  EFFORT_ORDER.forEach(key => {
    map[key] = Object.assign({}, EFFORT_DEFAULTS[key], saved[key] || {});
  });
  return map;
}

function saveEffortPresets(map) {
  try { localStorage.setItem(EFFORT_STORE, JSON.stringify(map)); } catch (e) {}
}

function effortPreset(key) {
  const map = loadEffortPresets();
  return map[key] || map.normal;
}

function effortOrgWord(n) {
  const tail = n % 100;
  if (tail >= 11 && tail <= 14) return 'организаций';
  const last = n % 10;
  if (last === 1) return 'организация';
  if (last >= 2 && last <= 4) return 'организации';
  return 'организаций';
}

// Сколько получится: города × запросы × страницы × 50, но не больше лимита.
// Цифра приблизительная — так и подписана, зато честно реагирует на правку
// городов, ключей и варианта объёма.
function estimateRun() {
  const qEl = document.getElementById('f-queries');
  const queries = Math.max(1, qEl
    ? qEl.value.split('\n').map(s => s.trim()).filter(Boolean).length
    : 1);
  const cities = Math.max(1, (typeof selectedCities !== 'undefined' && selectedCities.length)
    ? selectedCities.length : 1);
  const num = (id, fallback) => {
    const el = document.getElementById(id);
    const value = Number(el && el.value);
    return Number.isFinite(value) && value > 0 ? value : fallback;
  };
  const pages = num('f-pages', 1);
  const cap = num('f-max-candidates', 200);
  const workers = num('f-workers', 20);
  const orgs = Math.min(cap, cities * queries * pages * 50);
  // 3,6 карточки в минуту на поток — темп браузерного сбора карточек.
  const minutes = Math.max(1, Math.round(orgs / (workers * 3.6)));
  return { orgs, minutes };
}

function updateEffortEstimate() {
  const el = document.getElementById('effort-estimate');
  if (!el) return;
  const est = estimateRun();
  el.textContent = `≈ ${est.orgs} ${effortOrgWord(est.orgs)}, ~${est.minutes} мин`;
}

// Карточки живут данными: переименовали — сразу видно, перезагрузили — осталось.
function renderEffortCards() {
  const presets = loadEffortPresets();
  const active = currentEffort();
  document.querySelectorAll('[data-effort-item]').forEach(item => {
    const key = item.dataset.effortItem;
    const preset = presets[key];
    if (!preset) return;
    const name = item.querySelector('[data-effort-name]');
    const note = item.querySelector('[data-effort-note]');
    if (name) name.textContent = preset.name;
    if (note) note.textContent = preset.note;
    const on = key === active;
    item.classList.toggle('active', on);
    const btn = item.querySelector('.effort-opt');
    if (btn) btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    const gear = item.querySelector('.effort-edit');
    if (gear) gear.setAttribute('aria-label', `Настроить вариант «${preset.name}»`);
  });
}

function syncEffortButtons() {
  renderEffortCards();
}

// Выбор варианта выставляет те же поля формы, что и раньше: варианты не
// заменяют настройки, а заполняют их — поправить руками по-прежнему можно.
function setSearchEffort(name) {
  const key = EFFORT_ORDER.includes(name) ? name : 'normal';
  const preset = effortPreset(key);
  try { localStorage.setItem('search-effort', key); } catch (e) {}
  const pages = document.getElementById('f-pages');
  if (pages) pages.value = preset.pages;
  const cap = document.getElementById('f-max-candidates');
  if (cap) cap.value = preset.candidates;
  const vk = document.getElementById('f-vk-check');
  if (vk && vk.checked !== !!preset.vk) {
    vk.checked = !!preset.vk;
    if (typeof onVkCheckChange === 'function') onVkCheckChange();
  }
  renderEffortCards();
  updateEffortEstimate();
}

// ── Редактор карточки ─────────────────────────────────────────
function updateEditorEstimate() {
  const el = document.getElementById('ee-estimate');
  if (!el) return;
  const num = (id, fallback) => {
    const node = document.getElementById(id);
    const value = Number(node && node.value);
    return Number.isFinite(value) && value > 0 ? value : fallback;
  };
  const pages = num('ee-pages', 1);
  const cap = num('ee-candidates', 200);
  const orgs = Math.min(cap, pages * 50);
  el.textContent = `За один город и один запрос: до ${orgs} ${effortOrgWord(orgs)}.`;
}

function openEffortEditor(key) {
  const modal = document.getElementById('effort-editor');
  if (!modal) return;
  const preset = effortPreset(key);
  _editingEffort = key;
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  };
  set('ee-name', preset.name);
  set('ee-note', preset.note);
  set('ee-pages', preset.pages);
  set('ee-candidates', preset.candidates);
  const vk = document.getElementById('ee-vk');
  if (vk) vk.checked = !!preset.vk;
  const title = document.getElementById('ee-title');
  if (title) title.textContent = `Настроить вариант «${preset.name}»`;
  updateEditorEstimate();
  lockPageScroll();
  modal.hidden = false;
  const name = document.getElementById('ee-name');
  if (name) { name.focus(); name.select(); }
}

function closeEffortEditor() {
  const modal = document.getElementById('effort-editor');
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  const key = _editingEffort;
  _editingEffort = null;
  unlockPageScroll();
  const gear = key ? document.querySelector(`[data-effort-edit="${key}"]`) : null;
  if (gear) gear.focus();
}

function saveEffortEditor() {
  if (!_editingEffort) return;
  const key = _editingEffort;
  const text = id => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const clamp = (id, min, max, fallback) => {
    const el = document.getElementById(id);
    const value = Number(el && el.value);
    if (!Number.isFinite(value) || value <= 0) return fallback;
    return Math.min(max, Math.max(min, Math.round(value)));
  };
  const vk = document.getElementById('ee-vk');
  const map = loadEffortPresets();
  map[key] = {
    name: text('ee-name').slice(0, 24) || EFFORT_DEFAULTS[key].name,
    note: text('ee-note').slice(0, 90) || EFFORT_DEFAULTS[key].note,
    pages: clamp('ee-pages', 1, 20, EFFORT_DEFAULTS[key].pages),
    candidates: clamp('ee-candidates', 1, 10000, EFFORT_DEFAULTS[key].candidates),
    vk: !!(vk && vk.checked),
  };
  saveEffortPresets(map);
  closeEffortEditor();
  renderEffortCards();
  // Правили выбранный вариант — сразу применяем новые значения к форме.
  if (currentEffort() === key) setSearchEffort(key);
  if (typeof showToast === 'function') showToast('Вариант сохранён', 'success');
}

// ── Блокировка прокрутки страницы под окном ──────────────────
// Без неё колесо мыши прокручивало сайдбор под модалкой, а страница после
// закрытия оказывалась в другом месте — окно «прыгало».
let _openModals = 0;

function lockPageScroll() {
  _openModals += 1;
  if (_openModals > 1) return;
  const gap = window.innerWidth - document.documentElement.clientWidth;
  document.body.classList.add('app-modal-open');
  if (gap > 0) document.body.style.paddingRight = `${gap}px`;
}

function unlockPageScroll() {
  _openModals = Math.max(0, _openModals - 1);
  if (_openModals > 0) return;
  document.body.classList.remove('app-modal-open');
  document.body.style.paddingRight = '';
}

// ── Окно «Ещё настройки» ─────────────────────────────────────
function setMoreSettingsTab(name) {
  const modal = document.getElementById('more-settings');
  if (!modal) return;
  modal.querySelectorAll('.ms-tab[data-ms-tab]').forEach(tab => {
    const on = tab.dataset.msTab === name;
    tab.classList.toggle('active', on);
    tab.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  modal.querySelectorAll('.ms-pane[data-ms-pane]').forEach(pane => {
    pane.hidden = pane.dataset.msPane !== name;
  });
}

function openMoreSettings(tab) {
  const modal = document.getElementById('more-settings');
  if (!modal) return;
  lockPageScroll();
  modal.hidden = false;
  setMoreSettingsTab(tab || 'data');
  updateEffortEstimate();
  const close = modal.querySelector('.ms-close');
  if (close) close.focus();
}

function closeMoreSettings() {
  const modal = document.getElementById('more-settings');
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  unlockPageScroll();
  const link = document.getElementById('btn-more-settings');
  if (link) link.focus();
}

document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  const editor = document.getElementById('effort-editor');
  if (editor && !editor.hidden) { closeEffortEditor(); return; }
  closeMoreSettings();
});

(function initEffort() {
  const boot = () => {
    ['f-pages', 'f-max-candidates', 'f-workers', 'f-queries'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('input', updateEffortEstimate);
    });
    // Города добавляются и убираются чипами — следим за списком, а не за
    // каждым обработчиком: иначе счётчик отставал бы от реального выбора.
    const box = document.getElementById('city-select-box');
    if (box && window.MutationObserver) {
      new MutationObserver(updateEffortEstimate).observe(box, { childList: true, subtree: true });
    }
    syncEffortButtons();
    updateEffortEstimate();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

// ── Пресеты фильтрации ───────────────────────────────────────
// Пресет — это набор тех же переключателей, что ниже в окне. Он не «прячет»
// настройки: всё, что он выставил, видно и можно поправить руками.
const FILTER_PRESETS = {
  strict: { score: 50, parseMode: 'without_website', socialMode: 'with_socials', collapse: true },
  normal: { score: 35, parseMode: 'without_website', socialMode: 'all', collapse: false },
  wide:   { score: 0,  parseMode: 'all',             socialMode: 'all', collapse: false },
};

function syncFilterPresetButtons(name) {
  document.querySelectorAll('.flt-preset[data-filter-preset]').forEach(btn => {
    const on = btn.dataset.filterPreset === name;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
}

function applyFilterPreset(name) {
  const preset = FILTER_PRESETS[name];
  if (!preset) return;
  if (typeof setMinScore === 'function') setMinScore(preset.score);
  if (typeof setParseMode === 'function') setParseMode(preset.parseMode);
  if (typeof setSocialMode === 'function') setSocialMode(preset.socialMode);
  const collapse = document.getElementById('f-collapse-chains');
  if (collapse) collapse.checked = preset.collapse;
  syncFilterPresetButtons(name);
}
