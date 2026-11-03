// ═══════════════════════════════════════════
//  «Ещё настройки» и объём сбора
// ═══════════════════════════════════════════
// Сайдбор отвечает на два вопроса: что искать и сколько собирать. Всё
// остальное — что парсить, глубина, фильтры, форматы — живёт в отдельном окне,
// где его ищут, а не на первом экране рядом с обязательными полями.

// Что входит в вариант: название, описание и значения формы. Название и
// описание можно переписать — под свою работу, а не под наши слова.
// Это семена первого запуска: дальше список карточек живёт в браузере, а
// удалённая карточка обратно не возвращается.
const EFFORT_DEFAULTS = {
  fast:     { name: 'Быстро',    note: 'первые 20 организаций с города', pages: 1, candidates: 20,  vk: false },
  normal:   { name: 'Обычный',   note: 'две страницы с города',          pages: 2, candidates: 200, vk: false },
  thorough: { name: 'Тщательно', note: 'все страницы и полные карточки', pages: 5, candidates: 600, vk: true },
  custom:   { name: 'Своё',      note: 'ваши настройки',                 pages: 2, candidates: 200, vk: false },
};
const EFFORT_ORDER = ['fast', 'normal', 'thorough', 'custom'];
const EFFORT_STORE = 'effort-cards';
const EFFORT_LEGACY_STORE = 'effort-presets';
let _editingEffort = null;

function _effortClamp(value, min, max, fallback) {
  const num = Math.round(Number(value));
  if (!Number.isFinite(num) || num <= 0) return fallback;
  return Math.min(max, Math.max(min, num));
}

// Список карточек — данные: добавили, переименовали, удалили — так и осталось.
// Старый формат (четыре пресета в effort-presets) читается один раз.
function loadEffortCards() {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(EFFORT_STORE) || 'null'); } catch (e) { saved = null; }
  if (!Array.isArray(saved) || !saved.length) {
    let legacy = {};
    try { legacy = JSON.parse(localStorage.getItem(EFFORT_LEGACY_STORE) || '{}') || {}; } catch (e) { legacy = {}; }
    saved = EFFORT_ORDER.map(key => Object.assign({ key }, EFFORT_DEFAULTS[key], legacy[key] || {}));
  }
  return saved.map(card => ({
    key: String(card.key || ''),
    name: String(card.name || 'Вариант').slice(0, 24),
    note: String(card.note || '').slice(0, 90),
    pages: _effortClamp(card.pages, 1, 20, 2),
    candidates: _effortClamp(card.candidates, 1, 10000, 200),
    vk: !!card.vk,
  })).filter(card => card.key);
}

function saveEffortCards(cards) {
  try { localStorage.setItem(EFFORT_STORE, JSON.stringify(cards)); } catch (e) {}
}

function effortCard(key) {
  const cards = loadEffortCards();
  return cards.find(card => card.key === key) || cards[0] || null;
}

function currentEffort() {
  let saved = '';
  try { saved = localStorage.getItem('search-effort') || ''; } catch (e) { saved = ''; }
  const cards = loadEffortCards();
  return cards.some(card => card.key === saved) ? saved : (cards[0] || {}).key;
}

function effortOrgWord(n) {
  const tail = n % 100;
  if (tail >= 11 && tail <= 14) return 'организаций';
  const last = n % 10;
  if (last === 1) return 'организация';
  if (last >= 2 && last <= 4) return 'организации';
  return 'организаций';
}

// Счётчик под карточками: та же модель, что у сводки (searchVolumeEstimate).
function updateEffortEstimate() {
  const el = document.getElementById('effort-estimate');
  if (!el) return;
  const est = searchVolumeEstimate();
  el.textContent = est.total
    ? `до ${est.total.toLocaleString('ru-RU')} ${effortOrgWord(est.total)}, ~${est.minutes} мин`
    : 'Выберите город и запрос — посчитаю объём';
}

// Карточки рисуются из списка: количество, названия и состав — всё данные.
function renderEffortCards() {
  const host = document.getElementById('effort-choices');
  if (!host) return;
  const active = currentEffort();
  host.innerHTML = loadEffortCards().map(card => {
    const on = card.key === active;
    const key = escapeHtml(card.key);
    return `<div class="effort-item${on ? ' active' : ''}" data-effort-item="${key}">
      <button type="button" class="effort-opt" data-effort="${key}"
              onclick="setSearchEffort('${key}')" aria-pressed="${on ? 'true' : 'false'}">
        <span class="effort-name" data-effort-name>${escapeHtml(card.name)}</span>
        <span class="effort-note" data-effort-note>${escapeHtml(card.note)}</span>
      </button>
      <button type="button" class="effort-edit" data-effort-edit="${key}"
              onclick="openEffortVariant('${key}')"
              aria-label="Настроить вариант «${escapeHtml(card.name)}»"
              title="Название, описание и состав прогона">
        <svg class="ico" aria-hidden="true"><use href="#i-gear"/></svg>
      </button>
    </div>`;
  }).join('');
  updateEffortEstimate();
}

function syncEffortButtons() {
  renderEffortCards();
}

// Выбор варианта выставляет те же поля формы, что и раньше: варианты не
// заменяют настройки, а заполняют их — поправить руками по-прежнему можно.
function setSearchEffort(name) {
  const card = effortCard(name);
  if (!card) return;
  try { localStorage.setItem('search-effort', card.key); } catch (e) {}
  const pages = document.getElementById('f-pages');
  if (pages) pages.value = card.pages;
  const cap = document.getElementById('f-max-candidates');
  if (cap) cap.value = card.candidates;
  const vk = document.getElementById('f-vk-check');
  if (vk && vk.checked !== !!card.vk) {
    vk.checked = !!card.vk;
    if (typeof onVkCheckChange === 'function') onVkCheckChange();
  }
  renderEffortCards();
}

// ── Вариант в общем окне настроек ────────────────────────────
// Шестерёнка открывает то же окно, что и чипы сводки: одна геометрия, одна
// шапка, один подвал. Отдельного маленького диалога больше нет.
function updateEditorEstimate() {
  const el = document.getElementById('ee-estimate');
  if (!el) return;
  const est = searchVolumeEstimate({
    pages: _effortClamp((document.getElementById('ee-pages') || {}).value, 1, 20, 2),
    cap: _effortClamp((document.getElementById('ee-candidates') || {}).value, 1, 10000, 200),
  });
  el.textContent = est.total
    ? `Этот вариант: до ${est.total.toLocaleString('ru-RU')} ${effortOrgWord(est.total)}, ~${est.minutes} мин`
    : 'Выберите город и запрос в сайдборе — покажу, сколько получится';
}

function fillEffortEditor(key) {
  const card = effortCard(key);
  if (!card) return;
  _editingEffort = card.key;
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  };
  set('ee-name', card.name);
  set('ee-note', card.note);
  set('ee-pages', card.pages);
  set('ee-candidates', card.candidates);
  const vk = document.getElementById('ee-vk');
  if (vk) vk.checked = !!card.vk;
  const del = document.getElementById('ee-delete');
  if (del) del.disabled = loadEffortCards().length <= 1;
  updateEditorEstimate();
}

function openEffortVariant(key) {
  _editingEffort = key;
  openMoreSettings('effort');
}

function readEffortEditor() {
  const text = id => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  return {
    name: text('ee-name').slice(0, 24) || 'Вариант',
    note: text('ee-note').slice(0, 90),
    pages: _effortClamp((document.getElementById('ee-pages') || {}).value, 1, 20, 2),
    candidates: _effortClamp((document.getElementById('ee-candidates') || {}).value, 1, 10000, 200),
    vk: !!(document.getElementById('ee-vk') || {}).checked,
  };
}

// Сохраняем по ходу правки: отдельной кнопки «Сохранить» нет, иначе «Готово»
// закрывало бы окно с потерянными правками.
function saveEffortEditor() {
  if (!_editingEffort) return;
  const cards = loadEffortCards();
  const card = cards.find(item => item.key === _editingEffort);
  if (!card) return;
  Object.assign(card, readEffortEditor());
  saveEffortCards(cards);
  const active = currentEffort() === card.key;
  renderEffortCards();
  if (active) setSearchEffort(card.key);
}

function addEffortCard() {
  const cards = loadEffortCards();
  const base = effortCard(_editingEffort) || cards[0] || { pages: 2, candidates: 200, vk: false };
  const key = 'card-' + Date.now().toString(36);
  cards.push({
    key, name: 'Свой вариант', note: 'мои настройки',
    pages: base.pages, candidates: base.candidates, vk: !!base.vk,
  });
  saveEffortCards(cards);
  renderEffortCards();
  fillEffortEditor(key);
  if (typeof showToast === 'function') showToast('Карточка добавлена', 'success');
}

function deleteEffortCard() {
  const cards = loadEffortCards();
  if (cards.length <= 1) {
    if (typeof showToast === 'function') showToast('Последнюю карточку удалить нельзя', 'warning');
    return;
  }
  const key = _editingEffort || currentEffort();
  const wasActive = currentEffort() === key;
  const rest = cards.filter(card => card.key !== key);
  saveEffortCards(rest);
  const next = rest[0].key;
  if (wasActive) setSearchEffort(next);
  renderEffortCards();
  fillEffortEditor(next);
  if (typeof showToast === 'function') showToast('Карточка удалена', 'success');
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

function openMoreSettings(tab, effortKey) {
  const modal = document.getElementById('more-settings');
  if (!modal) return;
  // Шестерёнка открывает вкладку «Вариант» с этой карточкой; чипы сводки —
  // свои разделы, там вариант не трогаем.
  if (tab === 'effort' || effortKey) {
    fillEffortEditor(effortKey || _editingEffort || currentEffort());
  }
  lockPageScroll();
  modal.hidden = false;
  setMoreSettingsTab(tab || 'effort');
  updateEffortEstimate();
  const close = modal.querySelector('.ms-close');
  if (close) close.focus();
}

function closeMoreSettings() {
  const modal = document.getElementById('more-settings');
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  unlockPageScroll();
  // Возвращаем фокус на шестерёнку того варианта, который правили.
  const gear = document.querySelector(`[data-effort-edit="${currentEffort()}"]`);
  if (gear) gear.focus();
}

document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
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
    // Правка варианта сохраняется сразу — слушаем сами поля.
    ['ee-name', 'ee-note', 'ee-pages', 'ee-candidates', 'ee-vk'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      const onEdit = () => { saveEffortEditor(); updateEditorEstimate(); };
      el.addEventListener('input', onEdit);
      el.addEventListener('change', onEdit);
    });
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
