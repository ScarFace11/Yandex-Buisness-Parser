// ═══════════════════════════════════════════
//  «Ещё настройки» и объём сбора
// ═══════════════════════════════════════════
// Сайдбор отвечает на два вопроса: что искать и сколько собирать. Всё
// остальное — что парсить, глубина, фильтры, форматы — живёт в отдельном окне,
// где его ищут, а не на первом экране рядом с обязательными полями.

const EFFORT_PRESETS = {
  fast:     { pages: 1, candidates: 100, vk: false },
  normal:   { pages: 2, candidates: 200, vk: false },
  thorough: { pages: 5, candidates: 600, vk: true },
};

function currentEffort() {
  try { return localStorage.getItem('search-effort') || 'normal'; }
  catch (e) { return 'normal'; }
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

function syncEffortButtons() {
  const active = currentEffort();
  document.querySelectorAll('.effort-opt[data-effort]').forEach(btn => {
    const on = btn.dataset.effort === active;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
}

function setSearchEffort(name) {
  const key = EFFORT_PRESETS[name] ? name : 'normal';
  const preset = EFFORT_PRESETS[key];
  try { localStorage.setItem('search-effort', key); } catch (e) {}
  const pages = document.getElementById('f-pages');
  if (pages) pages.value = preset.pages;
  const cap = document.getElementById('f-max-candidates');
  if (cap) cap.value = preset.candidates;
  const vk = document.getElementById('f-vk-check');
  if (vk && vk.checked !== preset.vk) {
    vk.checked = preset.vk;
    if (typeof onVkCheckChange === 'function') onVkCheckChange();
  }
  syncEffortButtons();
  updateEffortEstimate();
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
  const link = document.getElementById('btn-more-settings');
  if (link) link.focus();
}

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeMoreSettings();
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
