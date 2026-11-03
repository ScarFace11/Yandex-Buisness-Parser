// ═══════════════════════════════════════════
//  Browser Notifications
// ═══════════════════════════════════════════
// ── Настройки: чтение / запись / состояние ───────────────────
// Ключ и форма — `notifications_settings`:
//   {enabled, city_complete, search_complete}
// Битый JSON, чужой тип поля или недоступный localStorage не должны
// оставлять пользователя без уведомлений вообще — откатываемся к дефолтам.
function _notifyFlag(value, fallback) {
  return typeof value === 'boolean' ? value : fallback;
}

// Громкость — доля 0…1. Ни число строкой, ни мусор из старой версии
// настроек не должны превращать звук в «то играет, то нет».
function _notifyVolume(value, fallback) {
  const num = (typeof value === 'number') ? value : parseFloat(value);
  if (!isFinite(num)) return fallback;
  return Math.min(1, Math.max(0, num));
}

// Пресет проверяем по реестру: удалённый в новой версии id не должен
// оставлять пользователя без звука.
function _notifySound(value, fallback) {
  return (typeof value === 'string' && Object.prototype.hasOwnProperty.call(SOUND_PRESETS, value))
    ? value : fallback;
}

function loadNotifySettings() {
  let raw = null;
  try {
    if (typeof localStorage !== 'undefined' && localStorage) raw = localStorage.getItem(NOTIFY_KEY);
  } catch (e) { raw = null; }        // приватный режим: настройки доживут до перезагрузки
  let parsed = null;
  try { parsed = raw ? JSON.parse(raw) : null; } catch (e) { parsed = null; }
  const src = (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) ? parsed : {};
  notifySettings = {
    enabled:         _notifyFlag(src.enabled,         NOTIFY_DEFAULTS.enabled),
    city_complete:   _notifyFlag(src.city_complete,   NOTIFY_DEFAULTS.city_complete),
    search_complete: _notifyFlag(src.search_complete, NOTIFY_DEFAULTS.search_complete),
    volume:          _notifyVolume(src.volume,        VOLUME_DEFAULT),
    sound_city:      _notifySound(src.sound_city,     SOUND_DEFAULTS.city_complete),
    sound_search:    _notifySound(src.sound_search,   SOUND_DEFAULTS.search_complete),
  };
  notifyDraft = Object.assign({}, notifySettings);
  _syncNotifyGlobals();
  return notifySettings;
}

function saveNotifySettings() {
  try {
    if (typeof localStorage !== 'undefined' && localStorage) {
      localStorage.setItem(NOTIFY_KEY, JSON.stringify(notifySettings));
    }
  } catch (e) { /* нет доступа к хранилищу — молча живём до перезагрузки */ }
  _syncNotifyGlobals();
  updateNotifyBtn();
  return notifySettings;
}

// Старый глобал остаётся мастер-флагом: его читают sendNotification
// и урезанные функции в node-тестах.
function _syncNotifyGlobals() {
  notificationsEnabled = !!notifySettings.enabled;
}

function notifyAllowed(kind) {
  return !!notifySettings.enabled && !!notifySettings[kind];
}

// all_off | partial | all_on — нужно кнопке и подписи состояния
function notifyState() {
  if (!notifySettings.enabled) return 'all_off';
  const on = ['city_complete', 'search_complete'].filter(k => notifySettings[k]).length;
  if (on === 0) return 'all_off';
  return on === 2 ? 'all_on' : 'partial';
}

function notifyStateLabel() {
  // Короткая подпись: режимы (города/поиск) перечислены в tooltip, в шапке
  // им хватает точки-индикатора и слова «Уведомления».
  const st = notifyState();
  if (st === 'all_off') return 'Уведомления';
  if (st === 'all_on')  return 'Уведомления';
  return 'Уведомления';
}

// Подпись кнопки показывает и состояние типов, и проблему с разрешением:
// раньше в состоянии «запрещено» состояние типов пропадало вовсе.
function notifyStateTitle() {
  const c = notifySettings.city_complete ? 'вкл' : 'выкл';
  const s = notifySettings.search_complete ? 'вкл' : 'выкл';
  let t = `Города: ${c} · Поиск: ${s}. Клик — настройки.`;
  if (!('Notification' in window)) {
    t = 'Браузер не поддерживает системные уведомления — покажем тост. ' + t;
  } else if (Notification.permission === 'denied') {
    t = 'Уведомления запрещены в браузере — покажем тост вместо окна. ' + t;
  }
  return t;
}

function updateNotifyBtn() {
  const btn  = document.getElementById('btn-notify');
  const icon = document.getElementById('notify-icon');
  const txt  = document.getElementById('notify-txt');
  if (!btn || !icon || !txt) return;
  const st   = notifyState();
  const warn = !('Notification' in window) || Notification.permission === 'denied';
  btn.className = warn ? 'denied' : (notifySettings.enabled ? 'granted' : '');
  icon.innerHTML = st === 'all_off' ? UI_ICONS.bellOff : UI_ICONS.bell;
  // Точка-индикатор: зелёная — хоть один тип уведомлений включён, серая —
  // все выключены. Подпись в шапке одна («Уведомления»), состояние — точкой
  // и в tooltip: длинный режим «Уведомления: поиск» удлинял шапку.
  const dot = st === 'all_off' ? ' is-off' : '';
  txt.innerHTML = escapeHtml(notifyStateLabel())
    + `<i class="notify-dot${dot}" aria-hidden="true"></i>`
    + (warn ? ' ' + UI_ICONS.warn : '');
  btn.title        = notifyStateTitle();
  const pop = document.getElementById('notify-pop');
  btn.setAttribute('aria-expanded', pop && !pop.hidden ? 'true' : 'false');
}

function _renderNotifyPermHint() {
  const el = document.getElementById('notify-perm-hint');
  if (!el) return;
  let msg = '';
  if (!('Notification' in window)) {
    msg = 'Браузер не поддерживает системные уведомления: вместо окна покажем тост. Звук работает.';
  } else if (Notification.permission === 'denied') {
    msg = 'Браузер запретил уведомления: окна не показываются, вместо них — тост. Звук работает. '
        + 'Разрешить можно в настройках браузера для этой страницы.';
  } else if (Notification.permission === 'default') {
    msg = 'Разрешение на уведомления спросим при первом сохранении. Звук работает и без него.';
  }
  el.textContent = msg;
  el.hidden = !msg;
}

// ── Отправка: окно, иначе тост (событие не теряется) ─────────
// Окно уходит, только когда браузер разрешил уведомления; если нет — тост,
// а подсказку про разрешение добавляем один раз, чтобы не повторяться.
function sendNotification(title, body) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return false;
  if (!notificationsEnabled) return false;
  try {
    const n = new Notification(title, {body});
    n.onclick = () => { window.focus(); n.close(); };
    return true;
  } catch (e) { return false; }   // браузер может блокировать без service worker
}

function fmtDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (total < 60) return `${total} сек`;
  const m = Math.floor(total / 60);
  if (m < 60) return `${m} мин ${String(total % 60).padStart(2, '0')} сек`;
  return `${Math.floor(m / 60)} ч ${String(m % 60).padStart(2, '0')} мин`;
}

function _notifyOrgWord(n) {
  return (typeof pluralNum === 'function')
    ? pluralNum(n, 'организация', 'организации', 'организаций')
    : 'организаций';
}

function _notifyBoth(title, body) {
  if (sendNotification(title, body)) return true;
  const hint = _notifyHintShown ? '' : ' Разрешите уведомления в браузере, чтобы получать окна.';
  _notifyHintShown = true;
  try { showToast(`${title} — ${body}${hint}`, 'info'); } catch (e) { /* тостов нет (тесты) */ }
  return false;
}

function notifyCityComplete(info) {
  if (!notifyAllowed('city_complete')) return false;
  playCityDoneSound();
  const skipped = info.status === 'skipped';
  const title = skipped
    ? `⏭ Город «${info.name}» пропущен`
    : `🏙 Город «${info.name}» обработан`;
  const body = `${info.idx}/${info.total} · Найдено: ${info.records} ${_notifyOrgWord(info.records)}`;
  _notifyBoth(title, body);
  return true;
}

function notifySearchComplete(info) {
  if (!notifyAllowed('search_complete')) return false;
  playDoneSound();
  const body = `Городов: ${info.cities} · Найдено: ${info.found} ${_notifyOrgWord(info.found)}`
             + ` · ${fmtDuration(info.seconds)}`;
  _notifyBoth('✅ Поиск завершён', body);
  return true;
}

// ── Completion sounds (Web Audio API — тоны генерируются кодом) ──
// Один общий контекст на всю страницу: прежний код создавал новый
// AudioContext на каждый сигнал, упирался в лимит браузера и не всегда
// успевал разблокироваться после жеста.
let _audioCtx = null;

function audioCtx() {
  if (_audioCtx) return _audioCtx;
  const Ctor = window.AudioContext || window.webkitAudioContext;
  if (!Ctor) return null;
  try { _audioCtx = new Ctor(); } catch (e) { return null; }
  return _audioCtx;
}

// Autoplay-политика: контекст стартует «suspended» до первого жеста.
function unlockAudio() {
  const ctx = audioCtx();
  if (ctx && ctx.state === 'suspended' && typeof ctx.resume === 'function') {
    try { ctx.resume(); } catch (e) { /* браузер не дал — тишина */ }
  }
}

function _tone(ctx, freq, at, dur, gain, type) {
  try {
    const osc = ctx.createOscillator();
    const g   = ctx.createGain();
    osc.connect(g);
    g.connect(ctx.destination);
    osc.type = type || 'sine';
    osc.frequency.value = freq;
    // Громкость 0 — это валидная настройка (звук выключен), а exponentialRamp
    // от нуля браузеры считают ошибкой: держим нижнюю границу.
    g.gain.setValueAtTime(Math.max(0.0001, gain), at);
    g.gain.exponentialRampToValueAtTime(0.001, at + dur);
    osc.start(at);
    osc.stop(at + dur);
  } catch (e) { /* Web Audio unavailable */ }
}

// notes: частоты или пары [основная, обертон]; opts: gain/step/tail/type/volume
function _chime(notes, opts) {
  const ctx = audioCtx();
  if (!ctx) return false;
  unlockAudio();
  const o = opts || {};
  const vol = _notifyVolume(o.volume, 1);          // множитель громкости (0…1)
  const gain = (o.gain || 0.2) * vol;
  const step = o.step || 0.15, tail = o.tail || 0.35;
  notes.forEach((note, i) => {
    const pair = Array.isArray(note);
    const at = ctx.currentTime + i * step;
    _tone(ctx, pair ? note[0] : note, at, tail, gain, o.type || 'sine');
    if (pair && note[1]) _tone(ctx, note[1], at, tail, gain * 0.35, 'triangle');
  });
  return true;
}

// Пресет по id (неизвестный — дефолт своего типа, чтобы звук не пропадал).
function _preset(id, fallback) {
  return SOUND_PRESETS[id] || SOUND_PRESETS[fallback] || SOUND_PRESETS[SOUND_DEFAULTS.city_complete];
}

function _soundKey(kind) {
  return kind === 'search' ? 'sound_search' : 'sound_city';
}

// Единая точка воспроизведения: пресет и громкость берутся из настроек, а
// для предпросмотра — из черновика попапа (слышно ровно то, что сохранится).
function playNotifySound(kind, opts) {
  const o = opts || {};
  const src = o.draft ? notifyDraft : notifySettings;
  const fallback = kind === 'search' ? SOUND_DEFAULTS.search_complete : SOUND_DEFAULTS.city_complete;
  const id = _notifySound(src[_soundKey(kind)], fallback);
  const preset = _preset(id, fallback);
  return _chime(preset.notes, {
    gain: preset.gain, step: preset.step, tail: preset.tail, type: preset.type,
    volume: _notifyVolume(src.volume, VOLUME_DEFAULT),
  });
}

// Город: по умолчанию мягкий короткий «динь»; поиск — финальная мелодия.
function playCityDoneSound() {
  return playNotifySound('city');
}

function playDoneSound() {
  return playNotifySound('search');
}

// Кнопка «▶ Прослушать» в попапе — играет выбранный в черновике звук.
function previewNotifySound(kind) {
  return playNotifySound(kind, { draft: true });
}

// ── Попап настроек ──────────────────────────────────
function _renderNotifyPopover() {
  notifyDraft = Object.assign({}, notifySettings);
  _setSwitch(document.getElementById('notify-master'), notifyDraft.enabled);
  _syncSubSwitches();
  _renderSoundPickers();
  _renderNotifyPermHint();
  _syncNotifySaveBtn();
}

// ── Звук: пресет на каждый тип + громкость ──────────────────
// Варианты списка берём из реестра пресетов: подписи живут в одном месте,
// и добавленный пресет появляется в попапе сам.
function _fillSoundSelect(sel, value) {
  if (!sel) return;
  sel.innerHTML = '';                    // перерисовка не должна копить опции
  Object.keys(SOUND_PRESETS).forEach(id => {
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = SOUND_PRESETS[id].label;
    opt.selected = (id === value);
    sel.appendChild(opt);
  });
  sel.value = value;
}

function _renderSoundPickers() {
  _fillSoundSelect(document.getElementById('notify-sound-city'), notifyDraft.sound_city);
  _fillSoundSelect(document.getElementById('notify-sound-search'), notifyDraft.sound_search);
  _renderVolume();
}

function _renderVolume() {
  const pct = Math.round(_notifyVolume(notifyDraft.volume, VOLUME_DEFAULT) * 100);
  const el  = document.getElementById('notify-volume');
  const out = document.getElementById('notify-vol-val');
  if (el) el.value = String(pct);
  if (out) out.textContent = pct + '%';
}

// Смена пресета сразу его проигрывает — выбор звука без прослушивания
// был бы выбором наугад.
function notifySoundChanged(kind) {
  const key     = _soundKey(kind);
  const sel     = document.getElementById('notify-sound-' + (kind === 'search' ? 'search' : 'city'));
  const fallback = kind === 'search' ? SOUND_DEFAULTS.search_complete : SOUND_DEFAULTS.city_complete;
  if (key in notifyDraft) notifyDraft[key] = _notifySound(sel ? sel.value : '', fallback);
  _syncNotifySaveBtn();
  previewNotifySound(kind);
}

function _volumeFromSlider(el) {
  const raw = el ? parseFloat(el.value) : NaN;
  if (!isFinite(raw)) return VOLUME_DEFAULT;
  return Math.min(1, Math.max(0, raw / 100));
}

// oninput — только цифра рядом с ползунком; onchange (отпустили) — прослушка.
function notifyVolumeInput() {
  notifyDraft.volume = _volumeFromSlider(document.getElementById('notify-volume'));
  _renderVolume();
  _syncNotifySaveBtn();
}

function notifyVolumeCommit() {
  notifyVolumeInput();
  previewNotifySound('city');
}

function _setSwitch(el, on) {
  if (!el) return;
  el.classList.toggle('on', !!on);
  el.setAttribute('aria-checked', on ? 'true' : 'false');
}

// Подтумблеры спят, пока выключен мастер, но их значения в черновике живут:
// включили мастер обратно — выбор типов вернулся.
function _syncSubSwitches() {
  [['notify-city', 'city_complete'], ['notify-search', 'search_complete']].forEach(([id, key]) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = !notifyDraft.enabled;
    _setSwitch(el, notifyDraft[key]);
  });
}

function notifyDraftDirty() {
  return notifyDraft.enabled         !== notifySettings.enabled
      || notifyDraft.city_complete   !== notifySettings.city_complete
      || notifyDraft.search_complete !== notifySettings.search_complete
      || _notifyVolume(notifyDraft.volume, VOLUME_DEFAULT)
         !== _notifyVolume(notifySettings.volume, VOLUME_DEFAULT)
      || notifyDraft.sound_city      !== notifySettings.sound_city
      || notifyDraft.sound_search    !== notifySettings.sound_search;
}

function _syncNotifySaveBtn() {
  const btn = document.getElementById('notify-save');
  if (btn) btn.disabled = !notifyDraftDirty();
}

function toggleNotifySetting(key) {
  if (!(key in notifyDraft)) return;
  if (key !== 'enabled' && !notifyDraft.enabled) return;   // спят вместе с мастером
  notifyDraft[key] = !notifyDraft[key];
  const id = key === 'enabled' ? 'notify-master'
           : (key === 'city_complete' ? 'notify-city' : 'notify-search');
  _setSwitch(document.getElementById(id), notifyDraft[key]);
  _syncSubSwitches();
  _syncNotifySaveBtn();
}

function toggleNotifyPopover(ev) {
  if (ev && typeof ev.stopPropagation === 'function') ev.stopPropagation();
  const pop = document.getElementById('notify-pop');
  if (!pop) return;
  if (pop.hidden) openNotifyPopover(); else closeNotifyPopover();
}

function openNotifyPopover() {
  const pop = document.getElementById('notify-pop');
  if (!pop) return;
  _renderNotifyPopover();
  pop.hidden = false;
  updateNotifyBtn();
  const first = document.getElementById('notify-master');
  if (first && typeof first.focus === 'function') first.focus();
}

// Закрытие без «Сохранить» — откат черновика к сохранённым настройкам.
function closeNotifyPopover() {
  const pop = document.getElementById('notify-pop');
  if (!pop || pop.hidden) return;
  notifyDraft = Object.assign({}, notifySettings);
  pop.hidden = true;
  updateNotifyBtn();
}

function saveNotifySettingsFromPopover() {
  notifySettings = Object.assign({}, notifyDraft);
  saveNotifySettings();
  _renderNotifyPermHint();
  closeNotifyPopover();
  try { showToast('Настройки сохранены', 'success'); } catch (e) { /* тесты */ }
  // Разрешение спрашиваем ПОСЛЕ применения — жест есть, а звук уже включён.
  if (notifySettings.enabled && ('Notification' in window) && Notification.permission === 'default') {
    Notification.requestPermission().then(() => { updateNotifyBtn(); _renderNotifyPermHint(); });
  }
  return notifySettings;
}

// Клик вне попапа и Esc — то же, что «Отмена»: изменения не применяются.
// Обработчики именованные: их текст проверяют node-тесты.
function _notifyOutsideClick(e) {
  const pop = document.getElementById('notify-pop');
  const btn = document.getElementById('btn-notify');
  if (!pop || pop.hidden) return;
  if (pop.contains(e.target) || (btn && btn.contains(e.target))) return;
  closeNotifyPopover();
}

function _notifyEscape(e) {
  const pop = document.getElementById('notify-pop');
  if (e && e.key === 'Escape' && pop && !pop.hidden) closeNotifyPopover();
}

document.addEventListener('mousedown', _notifyOutsideClick);
