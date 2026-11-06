/* SmartPark console — no build step, no external dependencies. */
'use strict';

// ================================================================== state & utils
const S = {
  me: null, settings: null, classes: {}, kinds: [], samples: [], health: null,
  cleanup: null, view: null, es: null, chat: [], chatBusy: false,
  mapMode: lsGet('sp-map') || 'plan',
};
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const cur = () => (S.settings && S.settings.currency) || '₹';
const money = (v) => cur() + Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const nowS = () => Date.now() / 1000;
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
function dur(min) {
  min = Math.max(0, Math.floor(min));
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  if (h < 24) return `${h}h ${String(m).padStart(2, '0')}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}
const clock = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const dateTime = (ts) => ts ? new Date(ts * 1000).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';
function ago(ts) {
  const s = nowS() - ts;
  if (s < 45) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return dateTime(ts);
}
function fareJS(minutes, t) {
  if (!t || minutes <= t.grace_min) return 0;
  const days = Math.floor(minutes / 1440), rem = minutes - days * 1440;
  let total = days * t.daily_cap;
  if (rem > 0) total += Math.min(t.daily_cap, t.first_hour + Math.ceil(Math.max(0, rem - 60) / 60) * t.per_hour);
  return Math.round(total * 100) / 100;
}
const tariff = (cls) => S.settings.tariffs[cls] || S.settings.tariffs.car;
const isAdmin = () => S.me && S.me.role === 'admin';
const media = (src) => `/media?src=${encodeURIComponent(src)}`;
const cleanPlate = (s) => String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
function prettyPlate(p) {
  p = cleanPlate(p);
  let m = p.match(/^([A-Z]{2})(\d{2})([A-Z]{0,3})(\d{4})$/);
  if (m) return m.slice(1).filter(Boolean).join(' ');
  m = p.match(/^(\d{2})(BH)(\d{4})([A-Z]{1,2})$/);
  return m ? m.slice(1).join(' ') : p;
}
const looksLikePlate = (p) => /^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{3,4}$/.test(p) || /^\d{2}BH\d{4}[A-Z]{1,2}$/.test(p) || (p.length >= 6 && /\d/.test(p) && /[A-Z]/.test(p));
const SHORT_CLASS = { car: 'Car', bike: 'Bike', ev: 'EV', large: 'Van / SUV' };
const CLASS_ICON = { car: 'car', bike: 'bike', ev: 'zap', large: 'truck' };
const KIND_LABEL = { standard: 'Standard', ev: 'EV charging', accessible: 'Accessible', large: 'Large vehicle', bike: 'Two-wheeler' };
const greeting = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'; };

const ICONS = {
  grid: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  gate: '<path d="M4 21V5"/><path d="M4 8h16l-1.5 4H4"/><path d="M8 8l-1.5 4M12 8l-1.5 4M16 8l-1.5 4"/><path d="M2 21h5"/>',
  in: '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><path d="m10 17 5-5-5-5"/><path d="M15 12H3"/>',
  out: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
  ticket: '<path d="M3 9a3 3 0 0 0 0 6v3a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3a3 3 0 0 0 0-6V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2Z"/><path d="M13 5v2M13 11v2M13 17v2"/>',
  video: '<path d="m16 13 5.2 3.5a.5.5 0 0 0 .8-.4V7.9a.5.5 0 0 0-.8-.4L16 11"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
  camera: '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3Z"/><circle cx="12" cy="13" r="3"/>',
  gear: '<path d="M12.2 2h-.4a2 2 0 0 0-2 2v.2a2 2 0 0 1-1 1.7l-.4.3a2 2 0 0 1-2 0l-.2-.1a2 2 0 0 0-2.7.7l-.2.4a2 2 0 0 0 .7 2.7l.2.1a2 2 0 0 1 1 1.7v.5a2 2 0 0 1-1 1.8l-.2.1a2 2 0 0 0-.7 2.7l.2.4a2 2 0 0 0 2.7.7l.2-.1a2 2 0 0 1 2 0l.4.3a2 2 0 0 1 1 1.7v.2a2 2 0 0 0 2 2h.4a2 2 0 0 0 2-2v-.2a2 2 0 0 1 1-1.7l.4-.3a2 2 0 0 1 2 0l.2.1a2 2 0 0 0 2.7-.7l.2-.4a2 2 0 0 0-.7-2.7l-.2-.1a2 2 0 0 1-1-1.8v-.5a2 2 0 0 1 1-1.7l.2-.1a2 2 0 0 0 .7-2.7l-.2-.4a2 2 0 0 0-2.7-.7l-.2.1a2 2 0 0 1-2 0l-.4-.3a2 2 0 0 1-1-1.7V4a2 2 0 0 0-2-2Z"/><circle cx="12" cy="12" r="3"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  spark: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9Z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8Z"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  print: '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  alert: '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3Z"/><path d="M12 9v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  car: '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>',
  bike: '<circle cx="18.5" cy="17.5" r="3.5"/><circle cx="5.5" cy="17.5" r="3.5"/><circle cx="15" cy="5" r="1"/><path d="M12 17.5V14l-3-3 4-3 2 3h2"/>',
  zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
  truck: '<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/>',
  access: '<circle cx="16" cy="4" r="1"/><path d="m18 19 1-7-6 1"/><path d="m5 8 3-3 5.5 3-2.36 3.5"/><path d="M4.24 14.5a5 5 0 0 0 6.88 6"/><path d="M13.76 17.5a5 5 0 0 0-6.88-6"/>',
  pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  move: '<path d="M5 9l-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20"/>',
  ban: '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
  layers: '<path d="m12 2 10 5-10 5L2 7Z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
  cash: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/>',
  card: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
  qr: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3"/>',
  gift: '<path d="M20 12v10H4V12"/><path d="M2 7h20v5H2z"/><path d="M12 22V7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7zM12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
};
const icon = (n, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ''}</svg>`;

// ================================================================== api
class ApiError extends Error { constructor(msg, status, data) { super(msg); this.status = status; this.data = data || {}; } }
async function api(path, { method = 'GET', body, form, raw } = {}) {
  const opts = { method, headers: { 'X-SmartPark': '1' }, credentials: 'same-origin' };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json'; }
  let res;
  try { res = await fetch(path, opts); } catch (e) { throw new ApiError("Can't reach the SmartPark server. Is it running?", 0); }
  if (raw) return res;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && path !== '/api/login') renderLogin();
    throw new ApiError(data.error || data.detail?.[0]?.msg || `Request failed (${res.status})`, res.status, data);
  }
  return data;
}

// ================================================================== feedback
function toast(msg, kind = 'ok') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.innerHTML = `${icon(kind === 'error' ? 'alert' : 'check')}<span>${esc(msg)}</span>`;
  $('#toasts').append(el);
  setTimeout(() => { el.style.transition = 'opacity .3s, transform .3s'; el.style.opacity = '0'; el.style.transform = 'translateY(-6px)'; setTimeout(() => el.remove(), 300); }, kind === 'error' ? 5000 : 2600);
}
const fail = (e) => toast(e.message || String(e), 'error');

function modal({ title, body, actions = '', wide = false, onClose }) {
  const scrim = document.createElement('div');
  scrim.className = 'scrim';
  scrim.innerHTML = `<div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
    <div class="modal-h"><h2>${esc(title)}</h2><button class="btn quiet icon sm" data-x aria-label="Close">${icon('x')}</button></div>
    <div class="modal-b">${body}</div>${actions ? `<div class="modal-f">${actions}</div>` : ''}</div>`;
  const prev = document.activeElement;
  let closed = false;
  const close = () => { if (closed) return; closed = true; scrim.remove(); document.removeEventListener('keydown', onKey, true); onClose && onClose(); prev && prev.focus && prev.focus(); };
  const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(); } };
  scrim.addEventListener('mousedown', (e) => { if (e.target === scrim) close(); });
  $('[data-x]', scrim).onclick = close;
  document.addEventListener('keydown', onKey, true);
  document.body.append(scrim);
  const f = $('.modal-b input, .modal-b select, .modal-b textarea', scrim) || $('.modal-f .btn.primary', scrim);
  f && f.focus();
  return { el: scrim, close };
}
function confirmBox(title, text, okLabel = 'Confirm', danger = false) {
  return new Promise((resolve) => {
    let answered = false;
    const m = modal({ title, body: `<p class="muted" style="font-size:14.5px">${text}</p>`,
      actions: `<button class="btn" data-no>Cancel</button><button class="btn ${danger ? 'danger solid' : 'primary'}" data-yes>${esc(okLabel)}</button>`,
      onClose: () => { if (!answered) resolve(false); } });
    $('[data-no]', m.el).onclick = () => m.close();
    $('[data-yes]', m.el).onclick = () => { answered = true; resolve(true); m.close(); };
    $('[data-yes]', m.el).focus();
  });
}
function promptBox(title, label, value = '', { type = 'text', okLabel = 'Save' } = {}) {
  return new Promise((resolve) => {
    let answered = false;
    const m = modal({ title, body: `<label class="f">${esc(label)}<input class="input" id="pv" type="${type}" value="${esc(value)}"></label>`,
      actions: `<button class="btn" data-no>Cancel</button><button class="btn primary" data-yes>${esc(okLabel)}</button>`,
      onClose: () => { if (!answered) resolve(null); } });
    const done = () => { answered = true; resolve($('#pv', m.el).value); m.close(); };
    $('[data-no]', m.el).onclick = () => m.close();
    $('[data-yes]', m.el).onclick = done;
    $('#pv', m.el).addEventListener('keydown', (e) => { if (e.key === 'Enter') done(); });
  });
}
const tipEl = (() => { const t = document.createElement('div'); t.className = 'tip'; document.body.append(t); return t; })();
function showTip(html, x, y) {
  tipEl.innerHTML = html; tipEl.classList.add('on');
  const r = tipEl.getBoundingClientRect();
  let left = x + 14, top = y + 14;
  if (left + r.width > innerWidth - 8) left = x - r.width - 14;
  if (top + r.height > innerHeight - 8) top = y - r.height - 14;
  tipEl.style.left = `${Math.max(8, left)}px`; tipEl.style.top = `${Math.max(8, top)}px`;
}
const hideTip = () => tipEl.classList.remove('on');

// ================================================================== lot map
/** opts: highlight (slot id), route, detections, pick (bool), mode, compact */
function lotMap(lot, opts = {}) {
  const img = lot.lot_image || { w: 1000, h: 1000 };
  const W = 1000, H = Math.round(1000 * img.h / img.w);
  const photo = (opts.mode || S.mapMode) === 'photo';
  const tall = lot.orientation !== 'wide';
  const P = [];
  P.push(`<defs><pattern id="hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="10" height="10" fill="var(--closed-soft)"/><line x1="0" y1="0" x2="0" y2="10" stroke="var(--closed)" stroke-width="2" opacity=".5"/></pattern></defs>`);
  if (photo) {
    P.push(`<image href="${media(img.src)}" x="0" y="0" width="${W}" height="${H}" preserveAspectRatio="none"/>`);
    P.push(`<rect width="${W}" height="${H}" fill="#06080c" opacity=".3"/>`);
  } else {
    P.push(`<rect width="${W}" height="${H}" fill="var(--lot)"/>`);
    const rows = {};
    for (const s of lot.slots) {
      const [a, b] = tall ? [s.box[1], s.box[3]] : [s.box[0], s.box[2]];
      const r = rows[s.row] || (rows[s.row] = [a, b]);
      r[0] = Math.min(r[0], a); r[1] = Math.max(r[1], b);
    }
    const spans = Object.keys(rows).sort((a, b) => a - b).map((k) => rows[k]);
    for (let i = 0; i + 1 < spans.length; i++) {  // driving lanes between rows
      const mid = (spans[i][1] + spans[i + 1][0]) / 2;
      P.push(tall ? `<line x1="0" x2="${W}" y1="${mid * H}" y2="${mid * H}" stroke="var(--lot-line)" stroke-width="3" stroke-dasharray="24 18"/>`
        : `<line y1="0" y2="${H}" x1="${mid * W}" x2="${mid * W}" stroke="var(--lot-line)" stroke-width="3" stroke-dasharray="24 18"/>`);
    }
  }
  for (const s of lot.slots) {
    const [x1, y1, x2, y2] = s.box;
    const g = photo ? 4 : 7;
    const x = x1 * W + g, y = y1 * H + g, w = (x2 - x1) * W - 2 * g, h = (y2 - y1) * H - 2 * g;
    const k = ['free', 'parked', 'untracked', 'closed'].includes(s.status) ? s.status : 'free';
    const target = opts.highlight === s.id;
    const pickable = opts.pick && (s.status === 'free' || s.status === 'untracked');
    const dim = opts.pick && !pickable && !target;
    const stroke = target ? 'var(--route)' : `var(--${k})`;
    const fill = photo ? (target ? 'var(--route)' : `var(--${k})`) : (k === 'closed' ? 'url(#hatch)' : target ? 'var(--route)' : `var(--${k}-soft)`);
    const fillOp = photo ? (target ? 0.38 : k === 'free' ? 0.22 : 0.28) : (target ? 0.22 : 1);
    const short = Math.min(w, h);
    const fs = Math.max(14, short * (opts.compact ? 0.3 : 0.26));
    const parts = [`<rect class="r" x="${x}" y="${y}" width="${w}" height="${h}" rx="${Math.min(12, short * 0.14)}" fill="${fill}" fill-opacity="${fillOp}" stroke="${stroke}" stroke-width="${target ? 4 : 2.5}"/>`];
    const occupied = s.status === 'parked' || s.status === 'untracked';
    if (!photo && occupied) {  // car glyph, pointing along the bay
      const col = `var(--${k})`;
      const cw = tall ? w * 0.56 : w * 0.72, ch = tall ? h * 0.66 : h * 0.56;
      const cx = x + (w - cw) / 2, cy = y + (h - ch) / 2 + (tall ? h * 0.08 : 0);
      const rr = Math.min(cw, ch) * 0.28;
      parts.push(`<rect x="${cx}" y="${cy}" width="${cw}" height="${ch}" rx="${rr}" fill="${col}" opacity=".9"/>`);
      parts.push(tall ? `<rect x="${cx + cw * 0.14}" y="${cy + ch * 0.2}" width="${cw * 0.72}" height="${ch * 0.17}" rx="${cw * 0.1}" fill="var(--surface)" opacity=".85"/>`
        : `<rect x="${cx + cw * 0.63}" y="${cy + ch * 0.14}" width="${cw * 0.17}" height="${ch * 0.72}" rx="${ch * 0.1}" fill="var(--surface)" opacity=".85"/>`);
    }
    const lx = x + w / 2;
    if (photo) {
      const lw = fs * (0.62 * s.label.length + 0.9), lh = fs * 1.35;
      parts.push(`<rect x="${lx - lw / 2}" y="${y + h / 2 - lh / 2}" width="${lw}" height="${lh}" rx="${lh / 2}" fill="#07090d" opacity=".72"/>`);
      parts.push(`<text x="${lx}" y="${y + h / 2 + fs * 0.36}" text-anchor="middle" font-size="${fs}" font-weight="700" fill="#fff">${esc(s.label)}</text>`);
    } else if (occupied) {
      const sf = fs * 0.62;
      parts.push(tall ? `<text x="${lx}" y="${y + Math.max(sf * 1.25, h * 0.1)}" text-anchor="middle" font-size="${sf}" font-weight="700" fill="var(--text-2)">${esc(s.label)}</text>`
        : `<text x="${x + sf * 1.4}" y="${y + h / 2 + sf * 0.36}" text-anchor="middle" font-size="${sf}" font-weight="700" fill="var(--text-2)">${esc(s.label)}</text>`);
    } else {
      parts.push(`<text x="${lx}" y="${y + h / 2 + fs * 0.36}" text-anchor="middle" font-size="${fs}" font-weight="700" fill="${k === 'closed' ? 'var(--muted)' : `var(--${k})`}">${esc(s.label)}</text>`);
    }
    if (s.kind !== 'standard') {
      const glyph = { ev: '⚡', accessible: '♿', large: 'L', bike: '2W' }[s.kind];
      parts.push(`<text x="${x + w - 8}" y="${y + h - 10}" text-anchor="end" font-size="${Math.max(12, fs * 0.55)}" fill="${photo ? '#fff' : 'var(--text-2)'}">${glyph}</text>`);
    }
    if (s.ghost) parts.push(`<circle cx="${x + w - 11}" cy="${y + 11}" r="7" fill="var(--danger)" stroke="var(--surface)" stroke-width="2"/>`);
    P.push(`<g class="b ${target ? 'target' : ''} ${dim ? 'dim' : ''}" data-id="${s.id}" tabindex="0" role="button" aria-label="Bay ${esc(s.label)}, ${s.status}">${parts.join('')}</g>`);
  }
  if (opts.detections) {
    for (const d of opts.detections) {
      const [a, b, c, e] = d.box;
      P.push(`<rect class="det" x="${a * W}" y="${b * H}" width="${(c - a) * W}" height="${(e - b) * H}" rx="5" stroke="${d.cls === 'car' ? '#f5b13d' : '#3ccf86'}"/>`);
    }
  }
  if (opts.route && opts.route.points) {
    const pts = opts.route.points.map(([px, py]) => `${(px * W).toFixed(1)},${(py * H).toFixed(1)}`).join(' ');
    P.push(`<polyline class="route-bg" points="${pts}"/><polyline class="route" points="${pts}"/>`);
  }
  const ent = lot.entrance;
  if (ent) {
    const ex = Math.min(W - 20, Math.max(20, ent.x * W)), ey = Math.min(H - 20, Math.max(20, ent.y * H));
    P.push(`<g pointer-events="none"><circle cx="${ex}" cy="${ey}" r="19" fill="var(--route)" stroke="var(--surface)" stroke-width="4"/>
      <path d="M${ex - 7} ${ey} h14 M${ex + 1} ${ey - 6} l6 6 -6 6" stroke="#03141a" stroke-width="3.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></g>`);
  }
  return `<div class="lotmap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Parking lot map">${P.join('')}</svg></div>`;
}
function bayTip(s) {
  const out = [`<b>Bay ${esc(s.label)}</b>${s.kind !== 'standard' ? ` · ${esc(KIND_LABEL[s.kind])}` : ''}`];
  if (s.status === 'parked') {
    const m = (nowS() - s.ticket.entry_at) / 60;
    out.push(`${esc(s.ticket.display)}`, `${dur(m)} · ${money(fareJS(m, tariff(s.ticket.vehicle_class)))} so far`);
  } else if (s.status === 'untracked') out.push('Camera sees a car here with no ticket');
  else if (s.status === 'closed') out.push('Closed');
  else out.push('Free');
  if (s.ghost) out.push('Camera shows this bay empty');
  return out.join('<br>');
}
function wireMap(root, lot, onClick) {
  const svg = $('svg', root);
  if (!svg) return;
  const byId = Object.fromEntries(lot.slots.map((s) => [String(s.id), s]));
  svg.addEventListener('mousemove', (e) => { const g = e.target.closest('.b'); if (g) showTip(bayTip(byId[g.dataset.id]), e.clientX, e.clientY); else hideTip(); });
  svg.addEventListener('mouseleave', hideTip);
  const act = (e) => { const g = e.target.closest('.b'); if (g && onClick) { hideTip(); onClick(byId[g.dataset.id], e); } };
  svg.addEventListener('click', act);
  svg.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); act(e); } });
}
function mapLegend(lot) {
  const c = lot.counts;
  const item = (k, label, n) => `<span><i style="background:var(--${k})"></i>${label} <b style="color:var(--text)">${n}</b></span>`;
  return `<div class="maplegend">${item('free', 'Free', c.free)}${item('parked', 'Ticketed', c.parked)}${c.untracked ? item('untracked', 'No ticket', c.untracked) : ''}${c.closed ? item('closed', 'Closed', c.closed) : ''}</div>`;
}
function mapToggle() {
  return `<div class="seg" data-mapmode><button class="${S.mapMode === 'plan' ? 'on' : ''}" data-m="plan">${icon('layers')}Plan</button><button class="${S.mapMode === 'photo' ? 'on' : ''}" data-m="photo">${icon('image')}Camera</button></div>`;
}
function wireMapToggle(root, rerender) {
  $$('[data-mapmode] button', root).forEach((b) => b.onclick = () => { S.mapMode = b.dataset.m; lsSet('sp-map', S.mapMode); rerender(); });
}

// ================================================================== charts
function chartOccupancy(stats) {
  const data = stats.hours;
  if (!data.length || !data.some((d) => d.count)) return `<div class="empty">${icon('clock')}<span>No cars yet today</span></div>`;
  const W = 560, H = 190, L = 28, R = 8, T = 14, B = 24;
  const cap = stats.capacity || 1;
  const maxY = Math.max(cap, ...data.map((d) => d.count));
  const xs = (i) => L + (data.length === 1 ? (W - L - R) / 2 : i * (W - L - R) / (data.length - 1));
  const ys = (v) => T + (H - T - B) * (1 - v / maxY);
  const line = data.map((d, i) => `${xs(i).toFixed(1)},${ys(d.count).toFixed(1)}`).join(' ');
  const area = `${xs(0)},${ys(0)} ${line} ${xs(data.length - 1)},${ys(0)}`;
  const ticks = [0, Math.round(maxY / 2), maxY];
  const xt = data.filter((d, i) => d.hour % 4 === 0 || i === data.length - 1);
  return `<div class="chart" data-chart="occ"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cars in the lot per hour today">
    <g class="grid">${ticks.map((t) => `<line x1="${L}" x2="${W - R}" y1="${ys(t)}" y2="${ys(t)}"/>`).join('')}</g>
    <g class="axis">${ticks.map((t) => `<text x="${L - 8}" y="${ys(t) + 4}" text-anchor="end">${t}</text>`).join('')}
      ${xt.map((d) => `<text x="${xs(data.indexOf(d))}" y="${H - 4}" text-anchor="middle">${String(d.hour).padStart(2, '0')}:00</text>`).join('')}</g>
    <line class="cap" x1="${L}" x2="${W - R}" y1="${ys(cap)}" y2="${ys(cap)}"/><text class="cap-label" x="${W - R}" y="${ys(cap) - 6}" text-anchor="end">capacity ${cap}</text>
    <polygon class="area" points="${area}"/><polyline class="line" points="${line}"/>
    <line class="xh" y1="${T}" y2="${H - B}"/><circle class="dotm" r="5"/>
    <rect class="hit" x="${L}" y="0" width="${W - L - R}" height="${H}"/></svg></div>`;
}
function wireOccupancy(root, stats) {
  const el = $('[data-chart="occ"]', root); if (!el) return;
  const svg = $('svg', el), data = stats.hours;
  const W = 560, H = 190, L = 28, R = 8, T = 14, B = 24;
  const maxY = Math.max(stats.capacity || 1, ...data.map((d) => d.count));
  const xs = (i) => L + (data.length === 1 ? (W - L - R) / 2 : i * (W - L - R) / (data.length - 1));
  const ys = (v) => T + (H - T - B) * (1 - v / maxY);
  const hit = $('.hit', svg), xh = $('.xh', svg), dot = $('.dotm', svg);
  hit.addEventListener('mousemove', (e) => {
    const r = svg.getBoundingClientRect();
    const vx = (e.clientX - r.left) * W / r.width;
    const i = Math.max(0, Math.min(data.length - 1, Math.round((vx - L) / ((W - L - R) / Math.max(1, data.length - 1)))));
    const d = data[i];
    xh.setAttribute('x1', xs(i)); xh.setAttribute('x2', xs(i)); xh.style.opacity = .4;
    dot.setAttribute('cx', xs(i)); dot.setAttribute('cy', ys(d.count)); dot.style.opacity = 1;
    showTip(`<b>${String(d.hour).padStart(2, '0')}:00 – ${String(d.hour + 1).padStart(2, '0')}:00</b><br>${plural(d.count, 'car')} in the lot`, e.clientX, e.clientY);
  });
  hit.addEventListener('mouseleave', () => { hideTip(); xh.style.opacity = 0; dot.style.opacity = 0; });
}
function chartRevenue(stats) {
  const data = stats.days;
  if (!data.some((d) => d.revenue > 0)) return `<div class="empty">${icon('cash')}<span>No payments in the last 7 days yet</span></div>`;
  const W = 560, H = 190, L = 44, R = 8, T = 18, B = 24;
  const maxY = Math.max(1, ...data.map((d) => d.revenue));
  const p = Math.pow(10, Math.floor(Math.log10(maxY))), nice = Math.ceil(maxY / p) * p;
  const bw = (W - L - R) / data.length;
  const ys = (v) => T + (H - T - B) * (1 - v / nice);
  const ticks = [0, nice / 2, nice];
  const max = data.reduce((a, b) => (b.revenue > a.revenue ? b : a), data[0]);
  const fmt = (t) => cur() + (t >= 1000 ? `${+(t / 1000).toFixed(1)}k` : t);
  const bars = data.map((d, i) => {
    const x = L + i * bw + bw * 0.24, w = bw * 0.52, y = ys(d.revenue), h = Math.max(0, ys(0) - y);
    const today = i === data.length - 1, r = Math.min(4, w / 2, h);
    const path = h > 0 ? `M${x},${ys(0)} V${y + r} q0,-${r} ${r},-${r} H${x + w - r} q${r},0 ${r},${r} V${ys(0)} Z` : '';
    const label = (today || d === max) && d.revenue > 0 ? `<text class="val" x="${x + w / 2}" y="${y - 6}" text-anchor="middle">${esc(money(d.revenue))}</text>` : '';
    const day = today ? 'Today' : new Date(d.start * 1000).toLocaleDateString([], { weekday: 'short' });
    return `<path class="bar ${today ? '' : 'past'}" d="${path}"/>${label}<text x="${x + w / 2}" y="${H - 4}" text-anchor="middle" fill="var(--faint)" font-size="11">${day}</text>
      <rect class="hit" data-i="${i}" x="${L + i * bw}" y="${T}" width="${bw}" height="${H - T - B}"/>`;
  }).join('');
  return `<div class="chart" data-chart="rev"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Revenue per day, last 7 days">
    <g class="grid">${ticks.map((t) => `<line x1="${L}" x2="${W - R}" y1="${ys(t)}" y2="${ys(t)}"/>`).join('')}</g>
    <g class="axis">${ticks.map((t) => `<text x="${L - 8}" y="${ys(t) + 4}" text-anchor="end">${esc(fmt(t))}</text>`).join('')}</g>${bars}</svg></div>`;
}
function wireRevenue(root, stats) {
  const el = $('[data-chart="rev"]', root); if (!el) return;
  $$('.hit', el).forEach((h) => {
    h.addEventListener('mousemove', (e) => {
      const d = stats.days[+h.dataset.i];
      showTip(`<b>${new Date(d.start * 1000).toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' })}</b><br>${money(d.revenue)} · ${plural(d.sessions, 'exit')}`, e.clientX, e.clientY);
    });
    h.addEventListener('mouseleave', hideTip);
  });
}

// ================================================================== auth
const authBrand = (sub) => `<div class="brand" style="padding:0"><img src="/static/icon.svg" alt="" width="34" height="34"><div><b>SmartPark</b><span>${sub}</span></div></div>`;
function renderLogin() {
  stopStream(); S.me = null;
  $('#app').innerHTML = `<div class="auth"><div class="form"><form id="login" class="card" autocomplete="on">
    ${authBrand('Operator console')}<h1>Welcome back</h1>
    <label class="f">Username<input class="input" name="username" autocomplete="username" required autofocus></label>
    <label class="f">Password<input class="input" name="password" type="password" autocomplete="current-password" required></label>
    <div class="err" id="err"></div><button class="btn primary xl block" type="submit">Sign in</button></form></div></div>`;
  $('#login').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target), btn = $('button[type=submit]', e.target);
    btn.disabled = true; $('#err').textContent = '';
    try { await api('/api/login', { method: 'POST', body: { username: f.get('username'), password: f.get('password') } }); await start(); }
    catch (err) { $('#err').textContent = err.message; btn.disabled = false; }
  };
}
function renderSetup() {
  $('#app').innerHTML = `<div class="auth"><div class="form"><form id="setup" class="card">
    ${authBrand('First-time setup')}<h1>Set up your lot</h1>
    <p class="muted" style="margin-top:-8px">You'll be the admin. You can add staff later.</p>
    <label class="f">Lot name<input class="input" name="lot_name" value="SmartPark Central" maxlength="60"></label>
    <label class="f">Your name<input class="input" name="name" required maxlength="60" autofocus></label>
    <label class="f">Username<input class="input" name="username" required maxlength="40" autocomplete="username" pattern="[A-Za-z0-9._]+"></label>
    <label class="f">Password <small>8+ characters with a number or symbol</small><input class="input" name="password" type="password" minlength="8" required autocomplete="new-password"></label>
    <div class="err" id="err"></div><button class="btn primary xl block" type="submit">Create and open console</button></form></div></div>`;
  $('#setup').onsubmit = async (e) => {
    e.preventDefault();
    try { await api('/api/setup', { method: 'POST', body: Object.fromEntries(new FormData(e.target)) }); await start(); }
    catch (err) { $('#err').textContent = err.message; }
  };
}

// ================================================================== shell & routing
const VIEWS = [
  ['overview', 'Overview', 'grid'], ['gate', 'Gate', 'gate'], ['tickets', 'Tickets', 'ticket'],
  ['lot', 'Lot camera', 'video'], ['settings', 'Settings', 'gear'],
];
const ALIASES = { dashboard: 'overview', entry: 'gate', exit: 'gate' };
function renderShell() {
  const initials = S.me.name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
  $('#app').innerHTML = `<div class="app">
    <aside class="rail">
      <div class="brand"><img src="/static/icon.svg" alt=""><div><b>SmartPark</b><span id="lotname">${esc(S.settings.lot_name)}</span></div></div>
      <nav class="nav" aria-label="Main">${VIEWS.map(([id, label, ic]) => `<a href="#/${id}" data-v="${id}" class="${id === 'settings' ? 'hide-m' : ''}">${icon(ic)}<span>${label}</span>${id === 'overview' ? '<i class="badge" id="navbadge" hidden></i>' : ''}</a>`).join('')}</nav>
      <div class="grow"></div>
      <div class="rail-foot">
        <div class="row" style="justify-content:space-between"><span class="status" id="vstatus"><i></i><span>Vision</span></span>
          <button class="btn quiet sm icon" id="theme" aria-label="Toggle theme"></button></div>
        <div class="me"><div class="avatar">${esc(initials)}</div><div class="who"><b>${esc(S.me.name)}</b><span>${S.me.role === 'admin' ? 'Admin' : 'Operator'}</span></div>
          <button class="btn quiet sm icon" id="logout" title="Sign out" aria-label="Sign out">${icon('out')}</button></div>
      </div>
    </aside>
    <div class="main-col">
      <header class="mtop"><img src="/static/icon.svg" alt=""><b>${esc(S.settings.lot_name)}</b><span class="status" id="vstatus-m"><i></i></span><button class="btn quiet sm icon" id="theme-m" aria-label="Toggle theme"></button><a class="btn quiet sm icon" href="#/settings" aria-label="Settings">${icon('gear')}</a></header>
      <main class="page" id="view"></main>
    </div></div>
    <button class="fab" id="ask">${icon('spark')}<span>Ask</span></button>
    <aside class="drawer" id="drawer" aria-label="Assistant"></aside>`;
  $$('.nav a').forEach((a) => a.addEventListener('click', (e) => {
    if (currentView() === a.dataset.v && !location.hash.includes('?')) { e.preventDefault(); route(); }
  }));
  $('#logout').onclick = async () => { await api('/api/logout', { method: 'POST' }).catch(() => {}); renderLogin(); };
  $('#theme').onclick = toggleTheme; $('#theme-m').onclick = toggleTheme;
  $('#ask').onclick = toggleAssistant;
  updateStatus(); syncThemeIcon();
}
const isDark = () => (document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches);
function toggleTheme() { document.documentElement.dataset.theme = isDark() ? 'light' : 'dark'; lsSet('sp-theme', document.documentElement.dataset.theme); syncThemeIcon(); }
function syncThemeIcon() { ['#theme', '#theme-m'].forEach((id) => { const b = $(id); if (b) b.innerHTML = icon(isDark() ? 'sun' : 'moon'); }); }
function updateStatus() {
  if (!S.health) return;
  const st = S.health.vision.state;
  const cls = `status ${st === 'ready' ? 'ok' : st === 'loading' ? 'busy' : 'bad'}`;
  const text = st === 'ready' ? 'Cameras ready' : st === 'loading' ? 'Starting cameras…' : 'Vision off';
  const a = $('#vstatus'); if (a) { a.className = cls; a.title = S.health.vision.detail || ''; $('span', a).textContent = text; }
  const b = $('#vstatus-m'); if (b) { b.className = cls; b.title = text; }
}
function setBadge(n) { const b = $('#navbadge'); if (!b) return; b.hidden = !n; b.textContent = n; }
const visionReady = () => S.health && S.health.vision.state === 'ready';
const currentView = () => { const n = location.hash.replace(/^#\/?/, '').split('?')[0] || 'overview'; return ALIASES[n] || n; };
const hashParams = () => new URLSearchParams(location.hash.split('?')[1] || '');
function head(title, sub = '', actions = '') {
  return `<div class="page-head"><div><h1>${title}</h1>${sub ? `<p>${sub}</p>` : ''}</div>${actions ? `<div class="actions">${actions}</div>` : ''}</div>`;
}

async function route() {
  let view = currentView();
  if (!VIEWS.find((v) => v[0] === view)) view = 'overview';
  if (S.cleanup) { try { S.cleanup(); } catch (e) { /* ignore */ } S.cleanup = null; }
  S.view = view;
  hideTip();
  $$('.nav a').forEach((a) => a.classList.toggle('on', a.dataset.v === view));
  document.title = `${VIEWS.find((v) => v[0] === view)[1]} · SmartPark`;
  const el = $('#view');
  el.innerHTML = '';
  window.scrollTo(0, 0);
  try { S.cleanup = (await Views[view](el)) || null; } catch (e) { fail(e); }
}

// ================================================================== live updates
let refreshTimer = null;
function startStream() {
  stopStream();
  const es = new EventSource('/api/stream');
  es.onmessage = (ev) => {
    let msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.type === 'vision') api('/api/health').then((h) => { S.health = h; updateStatus(); refreshView(); }).catch(() => {});
    if (msg.type === 'settings') api('/api/me').then((m) => { S.settings = m.settings; const l = $('#lotname'); if (l) l.textContent = S.settings.lot_name; }).catch(() => {});
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshView, 200);
  };
  S.es = es;
}
function refreshView() { const v = Views[S.view]; if (v && v.refresh && !$('.scrim')) v.refresh(); }
function stopStream() { if (S.es) { S.es.close(); S.es = null; } }
setInterval(() => {
  const t = nowS();
  $$('[data-since]').forEach((el) => { el.textContent = dur((t - +el.dataset.since) / 60); });
  $$('[data-fare-since]').forEach((el) => { el.textContent = money(fareJS((t - +el.dataset.fareSince) / 60, tariff(el.dataset.cls))); });
  $$('[data-clock]').forEach((el) => { el.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); });
}, 1000);

// ================================================================== ticket modal & printing
async function openTicket(id) {
  let t, lot;
  try { [t, lot] = await Promise.all([api(`/api/tickets/${id}`), api('/api/lot')]); } catch (e) { return fail(e); }
  const parked = t.status === 'parked';
  const body = `<div class="stack">
    <div class="row"><span class="plate xl">${esc(t.display)}</span><div class="spacer"></div>
      <span class="tag ${t.status}">${parked ? 'Parked' : t.status === 'closed' ? `Paid · ${esc((t.pay_method || '').toUpperCase())}` : 'Void'}</span></div>
    <div class="facts">
      <div><div class="k">Bay</div><div class="v">${esc(t.slot_label)}</div></div>
      <div><div class="k">${parked ? 'Parked for' : 'Stayed'}</div><div class="v" ${parked ? `data-since="${t.entry_at}"` : ''}>${dur(t.minutes)}</div></div>
      <div><div class="k">${parked ? 'Fare so far' : 'Paid'}</div><div class="v" ${parked ? `data-fare-since="${t.entry_at}" data-cls="${t.vehicle_class}"` : ''}>${money(parked ? t.quote.total : t.fare)}</div></div>
    </div>
    <div class="muted small">${esc(t.class_name)} · in ${dateTime(t.entry_at)}${t.exit_at ? ` · out ${dateTime(t.exit_at)}` : ''} · ticket <span class="mono">${esc(t.code)}</span> · by ${esc(t.created_by_name || '—')}</div>
    ${t.notes ? `<div class="notice info">${icon('info')}<span>${esc(t.notes)}</span></div>` : ''}
    <div class="${t.entry_image && parked ? 'grid2' : ''}">
      ${t.entry_image ? `<img src="${media('data:' + t.entry_image)}" alt="Entry photo" style="width:100%;border-radius:14px;aspect-ratio:4/3;object-fit:cover;background:#000">` : ''}
      ${parked ? lotMap(lot, { highlight: t.slot_id, route: t.route, compact: true }) : ''}
    </div></div>`;
  const actions = [
    `<button class="btn" data-print>${icon('print')}${parked ? 'Print ticket' : 'Print receipt'}</button>`,
    parked && isAdmin() ? `<button class="btn danger" data-void>${icon('ban')}Void</button>` : '',
    '<div class="spacer"></div>',
    parked ? `<button class="btn" data-move>${icon('move')}Move bay</button>` : '',
    parked ? `<button class="btn primary" data-exit>${icon('out')}Check out</button>` : '',
  ].join('');
  const m = modal({ title: parked ? 'Parked car' : 'Ticket', body, actions, wide: true });
  $('[data-print]', m.el).onclick = () => (parked ? printTicket(t) : printReceipt(t));
  const ex = $('[data-exit]', m.el); if (ex) ex.onclick = () => { m.close(); location.hash = `#/gate?t=${t.id}`; };
  const mv = $('[data-move]', m.el); if (mv) mv.onclick = () => { m.close(); moveDialog(t); };
  const vd = $('[data-void]', m.el); if (vd) vd.onclick = async () => {
    const reason = await promptBox('Void this ticket?', 'Reason (kept in the log)', 'Entered by mistake', { okLabel: 'Void ticket' });
    if (reason === null) return;
    try { await api(`/api/tickets/${t.id}/void`, { method: 'POST', body: { reason } }); m.close(); toast('Ticket voided'); } catch (e) { fail(e); }
  };
}
async function moveDialog(t) {
  const lot = await api('/api/lot');
  const m = modal({ title: `Move ${t.display}`, wide: true, body: `<p class="muted" style="margin-bottom:14px">Pick a free bay.</p><div id="mv">${lotMap(lot, { pick: true, highlight: t.slot_id })}</div>` });
  wireMap($('#mv', m.el), lot, async (s) => {
    if (s.status !== 'free' && s.status !== 'untracked') return;
    try { await api(`/api/tickets/${t.id}/move`, { method: 'POST', body: { slot_id: s.id } }); m.close(); toast(`Moved to ${s.label}`); } catch (e) { fail(e); }
  });
}
function printSlip(html) {
  const area = $('#print-area');
  area.innerHTML = html;
  Promise.all($$('img', area).map((i) => (i.complete ? 0 : new Promise((r) => { i.onload = i.onerror = r; })))).then(() => window.print());
}
function printTicket(t) {
  printSlip(`<div class="slip"><h1>${esc(S.settings.lot_name)}</h1><div class="c">Parking ticket</div>
    <div class="pl">${esc(t.display)}</div><div class="big">Bay ${esc(t.slot_label)}</div>
    <table><tr><td>Ticket</td><td>${esc(t.code)}</td></tr><tr><td>In</td><td>${dateTime(t.entry_at)}</td></tr>
    <tr><td>Rate</td><td>${money(t.tariff.first_hour)} first hour, ${money(t.tariff.per_hour)}/h after</td></tr></table>
    <img src="/api/tickets/${t.id}/code.svg" alt=""><div class="ft">Show this at the exit · first ${t.tariff.grace_min} min free</div></div>`);
}
function printReceipt(t) {
  printSlip(`<div class="slip"><h1>${esc(S.settings.lot_name)}</h1><div class="c">Receipt</div>
    <div class="pl">${esc(t.display)}</div><div class="big">${money(t.fare)}</div>
    <table><tr><td>Ticket</td><td>${esc(t.code)}</td></tr><tr><td>Bay</td><td>${esc(t.slot_label)}</td></tr>
    <tr><td>In</td><td>${dateTime(t.entry_at)}</td></tr><tr><td>Out</td><td>${dateTime(t.exit_at)}</td></tr>
    <tr><td>Stayed</td><td>${dur(t.minutes)}</td></tr><tr><td>Paid by</td><td>${esc((t.pay_method || '').toUpperCase())}</td></tr></table>
    <div class="ft">Thank you for parking with us</div></div>`);
}

// ================================================================== views
const Views = {};

// ---------------------------------------------------------------- Overview
Views.overview = async (el) => {
  const draw = async () => {
    const [lot, st] = await Promise.all([api('/api/lot'), api('/api/stats')]);
    if (!el.isConnected) return;
    const c = lot.counts, now = nowS();
    const untracked = lot.slots.filter((s) => s.status === 'untracked');
    const ghosts = lot.slots.filter((s) => s.ghost);
    const longs = lot.slots.filter((s) => s.ticket && now - s.ticket.entry_at > 86400);
    setBadge(untracked.length + ghosts.length);
    const todo = [];
    if (untracked.length) todo.push(`<div class="it"><div class="ic">${icon('car')}</div><div><b>${plural(untracked.length, 'car')} without a ticket</b><p>Seen by the lot camera. Tap a bay to ticket it.</p>
      <div class="chips">${untracked.map((s) => `<button data-slot="${s.id}">${esc(s.label)}</button>`).join('')}</div></div></div>`);
    if (ghosts.length) todo.push(`<div class="it"><div class="ic danger">${icon('alert')}</div><div><b>${plural(ghosts.length, 'ticket')} with an empty bay</b><p>The driver may have left without paying.</p>
      <div class="chips">${ghosts.map((s) => `<button data-t="${s.ticket.id}">${esc(s.label)} · ${esc(s.ticket.plate.slice(-4))}</button>`).join('')}</div></div></div>`);
    if (longs.length) todo.push(`<div class="it"><div class="ic info">${icon('clock')}</div><div><b>${plural(longs.length, 'car')} parked over 24 hours</b>
      <div class="chips">${longs.map((s) => `<button data-t="${s.ticket.id}">${esc(s.label)} · ${esc(s.ticket.plate.slice(-4))}</button>`).join('')}</div></div></div>`);
    if (S.health.vision.state === 'error') todo.push(`<div class="it"><div class="ic danger">${icon('video')}</div><div><b>Cameras unavailable</b><p>${esc(S.health.vision.detail)}</p></div></div>`);
    const next = c.free ? await api('/api/assign/preview?vehicle_class=car').then((r) => r.slot).catch(() => null) : null;
    if (!el.isConnected) return;

    el.innerHTML = `${head(`${greeting()}, ${esc(S.me.name.split(' ')[0])}`, `${esc(lot.lot_name)} · <span data-clock>${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>${lot.last_scan ? ` · camera checked ${ago(lot.last_scan.at)}` : ''}`,
      `<a class="btn primary xl" href="#/gate">${icon('gate')}Open gate <span class="key" style="margin-left:4px">G</span></a>`)}
      <section class="hero">
        <div class="card stat main"><div class="label">Free bays</div>
          <div class="value">${c.free}<small> of ${lot.capacity}</small></div>
          <div class="capbar">${c.parked ? `<i style="flex:${c.parked};background:var(--parked)"></i>` : ''}${c.untracked ? `<i style="flex:${c.untracked};background:var(--untracked)"></i>` : ''}${c.free ? `<i style="flex:${c.free};background:var(--free)"></i>` : ''}${c.closed ? `<i style="flex:${c.closed};background:var(--closed)"></i>` : ''}</div>
          <div class="capkey"><span><i style="background:var(--parked)"></i><b>${c.parked}</b> ticketed</span>${c.untracked ? `<span><i style="background:var(--untracked)"></i><b>${c.untracked}</b> no ticket</span>` : ''}<span><i style="background:var(--free)"></i><b>${c.free}</b> free</span>${next ? `<span>Next car → <b>${esc(next.label)}</b></span>` : ''}</div></div>
        <div class="card stat"><div class="label">Collected today</div><div class="value">${esc(money(st.revenue_today))}</div><div class="meta">${plural(st.exits_today, 'paid exit')}</div></div>
        <div class="card stat"><div class="label">On the meter</div><div class="value">${esc(money(st.projected))}</div><div class="meta">if every parked car left now</div></div>
        <div class="card stat"><div class="label">Cars in today</div><div class="value">${st.entries_today}</div><div class="meta">${st.avg_stay_min != null ? `avg stay ${dur(st.avg_stay_min)}` : 'no completed stays yet'}</div></div>
      </section>
      <section class="overview">
        <div class="card"><div class="card-h"><h3>Live lot</h3><div class="end">${mapToggle()}</div></div>
          <div class="card-b"><div id="omap">${lot.slots.length ? lotMap(lot) : `<div class="empty">${icon('layers')}<b>No lot layout yet</b><span>Map it from the Lot camera page.</span></div>`}</div>
          <div class="row" style="margin-top:14px">${mapLegend(lot)}<div class="spacer"></div><a class="btn sm quiet" href="#/lot">${icon('scan')}Check camera</a></div></div></div>
        <div class="side">
          <div class="card"><div class="card-h"><h3>Needs attention</h3>${todo.length ? `<span class="tag warn">${todo.length}</span>` : ''}</div>
            ${todo.length ? `<div class="todo" style="margin-top:6px">${todo.join('')}</div>` : `<div class="allclear" style="margin-top:12px"><div class="ic">${icon('check')}</div><div><b style="color:var(--text)">All clear</b><div class="small">Every car the camera sees has a ticket.</div></div></div>`}</div>
          <div class="card"><div class="card-h"><h3>Recent</h3></div><div class="card-b flush feed">${st.activity.length ? st.activity.slice(0, 8).map((a) => `
            <div class="it" ${a.ticket_id ? `data-t="${a.ticket_id}"` : ''}><span class="dot ${a.kind}"></span><span>${esc(a.message)}</span><time>${clock(a.at)}</time></div>`).join('') : '<div class="empty">Nothing yet</div>'}</div></div>
        </div>
      </section>
      <section class="charts">
        <div class="card"><div class="card-h"><h3>Cars in the lot today</h3>${st.peak ? `<span class="meta">peak ${String(st.peak.hour).padStart(2, '0')}:00</span>` : ''}</div><div class="card-b">${chartOccupancy(st)}</div></div>
        <div class="card"><div class="card-h"><h3>Revenue this week</h3><span class="meta">${esc(money(st.days.reduce((a, d) => a + d.revenue, 0)))}</span></div><div class="card-b">${chartRevenue(st)}</div></div>
      </section>`;
    wireMap($('#omap', el), lot, (s) => {
      if (s.ticket) openTicket(s.ticket.id);
      else if (s.status === 'untracked' || s.status === 'free') location.hash = `#/gate?slot=${s.id}`;
    });
    wireMapToggle(el, draw);
    wireOccupancy(el, st); wireRevenue(el, st);
    $$('.feed [data-t], .todo [data-t]', el).forEach((r) => r.onclick = () => openTicket(r.dataset.t));
    $$('.todo [data-slot]', el).forEach((b) => b.onclick = () => { location.hash = `#/gate?slot=${b.dataset.slot}`; });
  };
  await draw();
  Views.overview.refresh = () => draw().catch(() => {});
};

// ---------------------------------------------------------------- Gate (check in + check out)
Views.gate = async (el) => {
  const params = hashParams();
  const G = {
    mode: 'idle', ticket: null, pick: null, cls: 'car', accessible: false, slot: params.get('slot') ? +params.get('slot') : null,
    image: null, ocrConf: null, preview: null, cands: [], box: null, size: null, reading: false, readMs: null,
    camOn: lsGet('sp-cam') === '1', stream: null, seq: 0, done: null, lot: null, busy: false,
  };
  G.lot = await api('/api/lot');

  el.innerHTML = `${head('Gate', 'Type or scan a plate. Parked cars check out, new cars check in.')}
    <div class="platebar">${icon('search')}
      <input id="pin" placeholder="Number plate, last 4 digits or ticket code" autocomplete="off" spellcheck="false" maxlength="16" aria-label="Number plate">
      <button class="btn quiet icon" id="clr" title="Clear (Esc)" aria-label="Clear" hidden>${icon('x')}</button>
      <button class="btn" id="camBtn">${icon('camera')}<span>Camera</span></button>
      <label class="btn" title="Read a photo">${icon('upload')}<span>Photo</span><input type="file" accept="image/*" hidden id="file"></label>
    </div>
    <div class="gate-hint"><span><span class="key">Enter</span>confirm</span><span><span class="key">Esc</span>clear</span><span><span class="key">Space</span>capture with camera</span><span><span class="key">Ctrl V</span>paste a photo</span></div>
    <div class="gate">
      <div class="stack">
        <div class="card" id="mediaCard"></div>
        <div class="card"><div class="card-h"><h3>Parked now</h3><span class="meta" id="pcount"></span></div><div class="card-b flush scroll"><div class="list" id="plist"></div></div></div>
      </div>
      <div class="card decision" id="dec"></div>
    </div>`;
  const pin = $('#pin', el);

  // ---- media (camera / photo)
  function stopCam() { if (G.stream) { G.stream.getTracks().forEach((t) => t.stop()); G.stream = null; } }
  function drawMedia() {
    const mc = $('#mediaCard', el); if (!mc) return;
    $('#camBtn', el).classList.toggle('primary', G.camOn);
    if (G.preview) {
      stopCam();
      mc.innerHTML = `<div class="card-b stack tight"><div class="media"><img id="shot" src="${G.preview}" alt="Vehicle photo">${G.reading ? '<div class="scanline"></div>' : ''}<div id="pbox"></div>
        <div class="bar"><button class="btn sm" id="retake">${icon(G.camOn ? 'camera' : 'x')}${G.camOn ? 'Retake' : 'Remove photo'}</button></div></div>
        <div id="cands">${candsHtml()}</div></div>`;
      $('#retake', mc).onclick = () => { clearPhoto(); drawMedia(); };
      $$('.cand', mc).forEach((b) => b.onclick = () => choose(G.cands.find((c) => c.plate === b.dataset.p)));
      placeBox();
      return;
    }
    if (G.camOn) {
      mc.innerHTML = `<div class="card-b"><div class="media"><video id="vid" playsinline muted></video><div class="hint" id="camhint">${icon('camera')}<span>Starting camera…</span></div>
        <div class="bar"><button class="shutter" id="snap" aria-label="Capture" title="Capture (Space)"></button></div></div></div>`;
      startCam();
      $('#snap', mc).onclick = capture;
      return;
    }
    stopCam();
    mc.innerHTML = `<div class="card-b"><div class="drop" id="drop" role="button" tabindex="0">${icon('image')}<b>Drop a photo of the car</b><span class="small">or click to choose · turn on the camera · paste works too</span></div></div>`;
    const drop = $('#drop', mc);
    drop.onclick = () => $('#file', el).click();
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('over'); };
    drop.ondragleave = () => drop.classList.remove('over');
    drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('over'); const f = e.dataTransfer.files[0]; f && readPhoto(f); };
  }
  function startCam() {
    if (G.stream) { const v = $('#vid', el); if (v) { v.srcObject = G.stream; v.play(); $('#camhint', el)?.remove(); } return; }
    if (!navigator.mediaDevices?.getUserMedia) { const h = $('#camhint', el); if (h) h.innerHTML = `${icon('camera')}<span>No camera access in this browser. Use a photo instead.</span>`; return; }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
      .then((s) => {
        if (S.view !== 'gate' || !G.camOn || G.preview) { s.getTracks().forEach((t) => t.stop()); return; }
        G.stream = s; const v = $('#vid', el); if (v) { v.srcObject = s; v.play(); } $('#camhint', el)?.remove();
      })
      .catch((err) => { const h = $('#camhint', el); if (h) h.innerHTML = `${icon('camera')}<span>${err.name === 'NotAllowedError' ? 'Camera permission is blocked. Allow it in the browser, or use a photo.' : 'No camera found. Use a photo instead.'}</span>`; });
  }
  function capture() {
    const v = $('#vid', el);
    if (!G.stream || !v || !v.videoWidth) return;
    const c = document.createElement('canvas'); c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext('2d').drawImage(v, 0, 0);
    c.toBlob((b) => b && readPhoto(b), 'image/jpeg', 0.92);
  }
  function clearPhoto() { if (G.preview) URL.revokeObjectURL(G.preview); G.preview = null; G.image = null; G.cands = []; G.box = null; G.ocrConf = null; }
  function placeBox() {
    const pb = $('#pbox', el), img = $('#shot', el);
    if (!pb || !img || !G.box || !G.size) return;
    const fit = () => {
      const r = img.getBoundingClientRect(), s = Math.min(r.width / G.size[0], r.height / G.size[1]);
      const ox = (r.width - G.size[0] * s) / 2, oy = (r.height - G.size[1] * s) / 2;
      const [x1, y1, x2, y2] = G.box;
      pb.className = 'box';
      Object.assign(pb.style, { left: `${ox + x1 * s - 6}px`, top: `${oy + y1 * s - 6}px`, width: `${(x2 - x1) * s + 12}px`, height: `${(y2 - y1) * s + 12}px` });
    };
    img.complete ? fit() : (img.onload = fit);
  }
  function candsHtml() {
    if (G.reading) return `<div class="row muted small">${icon('scan')} Reading plate…</div>`;
    if (!G.preview) return '';
    if (!visionReady()) return `<div class="notice">${icon('alert')}<span>The plate reader is ${S.health.vision.state === 'loading' ? 'still starting' : 'off'}. Type the plate; the photo is kept with the ticket.</span></div>`;
    if (!G.cands.length) return `<div class="notice">${icon('alert')}<span>Couldn't find a plate. Try a closer, straighter shot, or type it.</span></div>`;
    return `<div class="small muted">Plate reader${G.readMs ? ` · ${(G.readMs / 1000).toFixed(1)}s` : ''} · tap to use another reading</div>
      <div class="cands">${G.cands.map((c) => {
        const pct = Math.round(c.score * 100);
        return `<button class="cand ${cleanPlate(pin.value) === c.plate ? 'on' : ''}" data-p="${esc(c.plate)}"><span class="plate">${esc(c.display)}</span><span class="conf ${pct >= 75 ? 'hi' : pct >= 50 ? 'mid' : ''}">${pct}%</span>${c.parked ? `<span class="tag parked">in ${esc(c.parked.slot)}</span>` : ''}</button>`;
      }).join('')}</div>`;
  }
  async function readPhoto(blob) {
    clearPhoto();
    G.preview = URL.createObjectURL(blob); G.reading = visionReady();
    drawMedia();
    const fd = new FormData(); fd.append('image', blob, 'vehicle.jpg');
    if (!visionReady()) {  // keep the photo with the ticket even without OCR
      api('/api/plate/read', { method: 'POST', form: fd }).then((r) => { G.image = r.image; }).catch(() => {});
      pin.focus(); return;
    }
    try {
      const r = await api('/api/plate/read', { method: 'POST', form: fd });
      G.image = r.image; G.cands = r.candidates; G.size = r.size; G.readMs = r.ms;
      G.reading = false; drawMedia();
      const best = r.candidates.find((c) => c.parked) || r.candidates[0];
      if (best) choose(best); else pin.focus();
    } catch (e) { G.reading = false; drawMedia(); fail(e); pin.focus(); }
  }
  function choose(c) {
    if (!c) return;
    pin.value = c.display; G.ocrConf = c.ocr_conf; G.box = c.box;
    placeBox(); $$('.cand', el).forEach((b) => b.classList.toggle('on', b.dataset.p === c.plate));
    lookup();
  }

  // ---- lookup decides the mode
  async function lookup() {
    const raw = pin.value.trim(), v = cleanPlate(raw);
    $('#clr', el).hidden = !raw;
    const seq = ++G.seq;
    if (!v) { G.ticket = null; await loadPick(); if (seq === G.seq) setMode('idle'); return; }
    const r = await api(`/api/tickets/find?q=${encodeURIComponent(raw)}`).catch(() => ({}));
    if (seq !== G.seq) return;
    if (r.ticket) { G.ticket = r.ticket; setMode('exit'); return; }
    if (looksLikePlate(v)) { await loadPick(); if (seq === G.seq) setMode('entry'); return; }
    setMode('nomatch');
  }
  async function loadPick() {
    const q = G.slot ? `vehicle_class=${G.cls}&slot_id=${G.slot}` : `vehicle_class=${G.cls}&accessible=${G.accessible}`;
    const r = await api(`/api/assign/preview?${q}`).catch(() => ({}));
    G.pick = r.slot || null;
  }
  function setMode(m) { G.mode = m; drawDecision(); }

  // ---- decision panel
  function drawDecision() {
    const d = $('#dec', el); if (!d) return;
    const lot = G.lot, c = lot.counts;
    const kicker = (color, text) => `<div class="kicker"><span class="pill" style="background:var(--${color})"></span>${text}</div>`;
    if (G.mode === 'idle') {
      const slot = G.slot && lot.slots.find((s) => s.id === G.slot);
      d.innerHTML = `${kicker('free', 'Ready for the next car')}
        <div class="idle-big">${c.free}<small> bays free</small></div>
        ${slot ? `<div class="notice info">${icon('pin')}<span>Checking in the car in bay <b>${esc(slot.label)}</b>. Type or scan its plate. <a href="#/gate" id="unslot">Cancel</a></span></div>`
          : G.pick ? `<div class="baybox"><div class="baytile">${esc(G.pick.label)}</div><div><b>Next car goes to ${esc(G.pick.label)}</b><p>Nearest free bay from the entrance</p></div></div>`
          : `<div class="baybox"><div class="baytile full">Full</div><div><b>The lot is full</b><p>Cars can still check out.</p></div></div>`}
        <div class="divider"></div>
        <div class="keys"><div><span class="key">Plate</span>checks a new car in, or a parked car out</div><div><span class="key">1234</span>last 4 digits find a parked car fast</div><div><span class="key">Camera</span>reads the plate for you</div></div>`;
      const u = $('#unslot', d); if (u) u.onclick = (e) => { e.preventDefault(); G.slot = null; history.replaceState(null, '', '#/gate'); lookup(); };
      return;
    }
    if (G.mode === 'nomatch') {
      d.innerHTML = `${kicker('closed', 'No match')}<h2>No parked car matches “${esc(pin.value.trim())}”</h2>
        <p class="muted">Keep typing the full plate to check a new car in.</p>`;
      return;
    }
    if (G.mode === 'entry') {
      const p = G.pick;
      d.innerHTML = `${kicker('parked', 'Check in')}
        <span class="plate xl" style="justify-self:start">${esc(prettyPlate(pin.value))}</span>
        <div class="classes" id="cls">${Object.keys(S.classes).map((k) => `<button class="choice ${G.cls === k ? 'on' : ''}" data-c="${k}">${icon(CLASS_ICON[k])}${esc(SHORT_CLASS[k] || S.classes[k])}</button>`).join('')}</div>
        <label class="switch"><input type="checkbox" id="acc" ${G.accessible ? 'checked' : ''}>${icon('access')}Needs an accessible bay</label>
        ${p ? `<div class="baybox"><div class="baytile">${esc(p.label)}</div><div><b>${G.slot ? `Bay ${esc(p.label)}, chosen by you` : `Send to bay ${esc(p.label)}`}</b>
            <p>${esc(KIND_LABEL[p.kind])} bay · ${money(tariff(G.cls).first_hour)} first hour, ${money(tariff(G.cls).per_hour)}/h after</p>
            ${G.slot ? '<button class="btn sm quiet" id="nearest" style="margin:4px 0 0 -12px">Use the nearest bay instead</button>' : '<p class="small" style="margin-top:2px">Tap another bay on the map to change it.</p>'}</div></div>`
          : `<div class="baybox"><div class="baytile full">Full</div><div><b>No suitable bay free</b><p>Tap any bay on the map to override.</p></div></div>`}
        <input class="input" id="note" maxlength="200" placeholder="Note (optional), e.g. keys left with security">
        <button class="btn primary xl block" id="go" ${p ? '' : 'disabled'}>${icon('in')}Check in to ${p ? esc(p.label) : '—'}<span class="key" style="margin-left:6px">Enter</span></button>
        <div id="emap">${lotMap(lot, { highlight: p && p.slot_id, route: p && p.route, pick: true, compact: true })}</div>`;
      $$('#cls .choice', d).forEach((b) => b.onclick = async () => { G.cls = b.dataset.c; G.slot = null; await loadPick(); drawDecision(); });
      $('#acc', d).onchange = async (e) => { G.accessible = e.target.checked; G.slot = null; await loadPick(); drawDecision(); };
      const n = $('#nearest', d); if (n) n.onclick = async () => { G.slot = null; await loadPick(); drawDecision(); };
      wireMap($('#emap', d), lot, async (s) => { if (s.status === 'free' || s.status === 'untracked') { G.slot = s.id; await loadPick(); drawDecision(); } });
      $('#go', d).onclick = checkIn;
      return;
    }
    if (G.mode === 'exit') {
      const t = G.ticket;
      d.innerHTML = `${kicker('free', 'Check out')}
        <div class="row"><span class="plate xl">${esc(t.display)}</span><div class="spacer"></div><span class="bay" style="height:36px;min-width:52px;font-size:16px">${esc(t.slot_label)}</span></div>
        <div><div class="fare" data-fare-since="${t.entry_at}" data-cls="${t.vehicle_class}">${money(t.quote.total)}</div>
          <div class="muted" style="margin-top:8px">${esc(t.quote.lines.join(' · '))}</div></div>
        <div class="fareline"><div>Parked for<b data-since="${t.entry_at}">${dur(t.minutes)}</b></div><div>Came in<b>${clock(t.entry_at)}</b></div><div>Vehicle<b>${esc(SHORT_CLASS[t.vehicle_class])}</b></div></div>
        <div class="paybtns"><button class="btn primary" data-m="upi">${icon('qr')}UPI</button><button class="btn" data-m="cash">${icon('cash')}Cash</button><button class="btn" data-m="card">${icon('card')}Card</button></div>
        <div class="row">${isAdmin() ? `<button class="btn sm quiet" data-m="waived">${icon('gift')}Waive fare</button>` : ''}<div class="spacer"></div><button class="btn sm quiet" id="details">Ticket details</button></div>
        ${t.entry_image ? `<img src="${media('data:' + t.entry_image)}" alt="Photo at entry" style="width:100%;max-height:220px;object-fit:cover;border-radius:14px;background:#000">` : ''}`;
      $$('[data-m]', d).forEach((b) => b.onclick = () => pay(b.dataset.m));
      $('#details', d).onclick = () => openTicket(t.id);
      return;
    }
    if (G.mode === 'doneIn') {
      const t = G.done;
      d.innerHTML = `<div class="row" style="gap:16px"><div class="done-ic">${icon('check')}</div><div><h2>Checked in</h2><p class="muted">Ticket <span class="mono">${esc(t.code)}</span> · ${clock(t.entry_at)}</p></div></div>
        <div class="baybox"><div class="baytile">${esc(t.slot_label)}</div><div><b>Send ${esc(t.display)} to bay ${esc(t.slot_label)}</b><p>First ${t.tariff.grace_min} min free, then ${money(t.tariff.first_hour)} for the first hour</p></div></div>
        ${lotMap(G.lot, { highlight: t.slot_id, route: t.route, compact: true })}
        <div class="row"><button class="btn" id="pr">${icon('print')}Print ticket</button><div class="spacer"></div><button class="btn primary xl" id="nx">Next car<span class="key" style="margin-left:6px">Enter</span></button></div>`;
      $('#pr', d).onclick = () => printTicket(t);
      $('#nx', d).onclick = reset;
      return;
    }
    if (G.mode === 'doneOut') {
      const t = G.done;
      d.innerHTML = `<div class="row" style="gap:16px"><div class="done-ic">${icon('check')}</div><div><h2>${t.status === 'void' ? 'Voided' : `Paid by ${esc((t.pay_method || '').toUpperCase())}`}</h2><p class="muted">${esc(t.display)} left bay ${esc(t.slot_label)}</p></div></div>
        <div class="fare">${money(t.fare)}</div>
        <div class="fareline"><div>Stayed<b>${dur(t.minutes)}</b></div><div>In<b>${clock(t.entry_at)}</b></div><div>Out<b>${clock(t.exit_at)}</b></div></div>
        <div class="row"><button class="btn" id="pr">${icon('print')}Print receipt</button><div class="spacer"></div><button class="btn primary xl" id="nx">Next car<span class="key" style="margin-left:6px">Enter</span></button></div>`;
      $('#pr', d).onclick = () => printReceipt(t);
      $('#nx', d).onclick = reset;
    }
  }

  async function checkIn() {
    if (G.busy || G.mode !== 'entry' || !G.pick) return;
    G.busy = true;
    const btn = $('#go', el); if (btn) btn.disabled = true;
    try {
      const t = await api('/api/tickets', { method: 'POST', body: {
        plate: pin.value, vehicle_class: G.cls, accessible: G.accessible, slot_id: G.slot || null,
        image: G.image, ocr_conf: G.ocrConf, notes: $('#note', el)?.value || null } });
      G.done = t; G.lot = await api('/api/lot');
      setMode('doneIn'); drawParked();
      $('#nx', el)?.focus();
    } catch (e) { fail(e); if (btn) btn.disabled = false; if (e.status === 409) lookup(); }
    finally { G.busy = false; }
  }
  async function pay(method) {
    const t = G.ticket;
    if (method === 'upi') {
      if (!t.upi_ready) {
        if (!(await confirmBox('No UPI ID set up', isAdmin() ? 'Add your UPI ID in Settings to show a payment QR. Mark this as paid by UPI anyway?' : 'Ask an admin to add a UPI ID in Settings. Mark this as paid by UPI anyway?', 'Mark as paid'))) return;
      } else {
        const ok = await new Promise((res) => {
          let answered = false;
          const m = modal({ title: 'Scan to pay', body: `<div class="stack" style="justify-items:center;text-align:center">
              <div class="fare" style="font-size:44px" data-fare-since="${t.entry_at}" data-cls="${t.vehicle_class}">${money(fareJS((nowS() - t.entry_at) / 60, tariff(t.vehicle_class)))}</div>
              <div class="qr lg"><img src="/api/tickets/${t.id}/upi.svg?ts=${Date.now()}" alt="UPI payment QR"></div>
              <p class="muted">Any UPI app · pays ${esc(S.settings.payee_name)}</p></div>`,
            actions: `<button class="btn" data-no>Cancel</button><button class="btn primary" data-ok>${icon('check')}Payment received</button>`,
            onClose: () => { if (!answered) res(false); } });
          $('[data-no]', m.el).onclick = () => m.close();
          $('[data-ok]', m.el).onclick = () => { answered = true; res(true); m.close(); };
        });
        if (!ok) return;
      }
    } else if (method === 'waived') {
      if (!(await confirmBox('Waive this fare?', 'The car leaves with nothing charged. This is recorded in the activity log.', 'Waive fare', true))) return;
    }
    try {
      G.done = await api(`/api/tickets/${t.id}/close`, { method: 'POST', body: { method } });
      G.lot = await api('/api/lot');
      setMode('doneOut'); drawParked();
      $('#nx', el)?.focus();
    } catch (e) { fail(e); }
  }
  function reset() {
    clearPhoto(); pin.value = ''; G.ticket = null; G.done = null; G.cls = 'car'; G.accessible = false; G.slot = null;
    if (location.hash !== '#/gate') history.replaceState(null, '', '#/gate');
    drawMedia(); lookup(); pin.focus();
  }

  // ---- parked list
  async function drawParked() {
    const d = await api('/api/tickets?status=parked&limit=200');
    const list = $('#plist', el); if (!list) return;
    $('#pcount', el).textContent = d.total ? d.total : '';
    const items = d.items.sort((a, b) => a.entry_at - b.entry_at);
    list.innerHTML = items.length ? items.map((t) => `<button data-id="${t.id}"><span class="bay">${esc(t.slot_label)}</span>
      <span><span class="plate">${esc(t.display)}</span><div class="sub"><span data-since="${t.entry_at}">${dur((nowS() - t.entry_at) / 60)}</span></div></span>
      <span class="amt" data-fare-since="${t.entry_at}" data-cls="${t.vehicle_class}">${money(t.fare_now)}</span></button>`).join('')
      : `<div class="empty">${icon('car')}<span>No cars parked</span></div>`;
    $$('button', list).forEach((b) => b.onclick = () => { const t = items.find((x) => x.id === +b.dataset.id); pin.value = t.display; lookup(); pin.focus(); });
  }

  // ---- events
  let typeTimer;
  pin.addEventListener('input', () => { clearTimeout(typeTimer); typeTimer = setTimeout(lookup, 180); });
  $('#clr', el).onclick = () => reset();
  $('#camBtn', el).onclick = () => { G.camOn = !G.camOn; lsSet('sp-cam', G.camOn ? '1' : '0'); if (G.camOn) clearPhoto(); else stopCam(); drawMedia(); };
  $('#file', el).onchange = (e) => { const f = e.target.files[0]; if (f) readPhoto(f); e.target.value = ''; };
  const onPaste = (e) => { const f = [...(e.clipboardData?.files || [])].find((x) => x.type.startsWith('image/')); if (f) { e.preventDefault(); readPhoto(f); } };
  const onKey = (e) => {
    if ($('.scrim') || e.ctrlKey || e.metaKey || e.altKey) return;
    const inField = e.target.matches('input, textarea, select');
    if (e.key === 'Enter' && !e.target.matches('textarea, a, .b') && !(e.target.matches('button') && e.target.id !== 'nx' && e.target.id !== 'go')) {
      if (G.mode === 'entry') { e.preventDefault(); checkIn(); }
      else if (G.mode === 'doneIn' || G.mode === 'doneOut') { e.preventDefault(); reset(); }
      return;
    }
    if (e.key === 'Escape') { e.preventDefault(); reset(); return; }
    if (e.code === 'Space' && G.camOn && G.stream && (!inField || (e.target === pin && !pin.value))) { e.preventDefault(); capture(); return; }
    if (!inField && e.key.length === 1 && /[a-z0-9]/i.test(e.key)) {  // typing anywhere goes to the plate box
      if (G.mode === 'doneIn' || G.mode === 'doneOut') { clearPhoto(); drawMedia(); pin.value = ''; }
      pin.focus();
    }
  };
  document.addEventListener('paste', onPaste);
  document.addEventListener('keydown', onKey);

  drawMedia(); drawParked();
  if (params.get('t')) {
    const t = await api(`/api/tickets/${params.get('t')}`).catch(() => null);
    if (t && t.status === 'parked') pin.value = t.display;
  }
  await lookup();
  pin.focus();

  Views.gate.refresh = async () => {
    G.lot = await api('/api/lot');
    drawParked();
    if (G.mode === 'idle' || G.mode === 'entry') { await loadPick(); if (G.mode === 'idle' || G.mode === 'entry') drawDecision(); }
  };
  return () => { stopCam(); clearPhoto(); document.removeEventListener('paste', onPaste); document.removeEventListener('keydown', onKey); };
};

// ---------------------------------------------------------------- Tickets
Views.tickets = async (el) => {
  const T = { status: 'parked', q: '', range: 'all', page: 0, size: 25 };
  el.innerHTML = `${head('Tickets', 'Every car in and out.', `<a class="btn" id="csv">${icon('download')}Export CSV</a>`)}
    <div class="toolbar">
      <div class="seg" id="st"><button data-s="parked">Parked</button><button data-s="history">History</button></div>
      <div class="search">${icon('search')}<input class="input" id="tq" placeholder="Search plate, ticket or bay"></div>
      <select class="input" id="rng" style="width:auto"><option value="all">All time</option><option value="today">Today</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select>
    </div>
    <div class="card"><div class="table-wrap" id="tbl"></div><div class="pager" id="pg"></div></div>`;
  const rangeArgs = () => {
    if (T.range === 'all') return '';
    const d = new Date(); d.setHours(0, 0, 0, 0);
    return `&frm=${Math.floor(T.range === 'today' ? d.getTime() / 1000 : d.getTime() / 1000 - (+T.range - 1) * 86400)}`;
  };
  async function draw() {
    $$('#st button', el).forEach((b) => b.classList.toggle('on', b.dataset.s === T.status));
    const qs = `status=${T.status}&q=${encodeURIComponent(T.q)}${rangeArgs()}`;
    $('#csv', el).href = `/api/tickets/export.csv?${qs}`;
    const d = await api(`/api/tickets?${qs}&limit=${T.size}&offset=${T.page * T.size}`);
    if (!$('#tbl', el)) return;
    const hist = T.status === 'history';
    $('#tbl', el).innerHTML = d.items.length ? `<table class="t"><thead><tr><th>Plate</th><th>Bay</th><th>Vehicle</th><th>In</th>
      ${hist ? '<th>Out</th><th>Stayed</th><th>Status</th><th class="r">Fare</th>' : '<th>Parked for</th><th class="r">Fare so far</th>'}</tr></thead><tbody>
      ${d.items.map((t) => `<tr data-id="${t.id}"><td><span class="plate">${esc(t.display)}</span></td><td><span class="bay">${esc(t.slot_label)}</span></td>
        <td class="muted">${esc(SHORT_CLASS[t.vehicle_class] || t.vehicle_class)}</td><td class="num">${dateTime(t.entry_at)}</td>
        ${hist ? `<td class="num">${dateTime(t.exit_at)}</td><td class="num">${dur((t.exit_at - t.entry_at) / 60)}</td>
          <td><span class="tag ${t.status}">${t.status === 'closed' ? esc((t.pay_method || 'paid').toUpperCase()) : 'Void'}</span></td><td class="r num"><b>${money(t.fare)}</b></td>`
          : `<td class="num" data-since="${t.entry_at}">${dur((nowS() - t.entry_at) / 60)}</td><td class="r num"><b data-fare-since="${t.entry_at}" data-cls="${t.vehicle_class}">${money(t.fare_now)}</b></td>`}</tr>`).join('')}
      </tbody></table>` : `<div class="empty">${icon('ticket')}<b>${T.q ? 'Nothing matches that search' : hist ? 'No finished tickets yet' : 'No cars parked'}</b></div>`;
    const pages = Math.max(1, Math.ceil(d.total / T.size));
    $('#pg', el).innerHTML = `<span>${plural(d.total, 'ticket')}${hist ? ` · ${money(d.revenue)} collected` : ''}</span>
      <span class="row"><button class="btn sm" id="pv" ${T.page ? '' : 'disabled'}>Previous</button><span class="num">${T.page + 1} / ${pages}</span><button class="btn sm" id="nx" ${T.page + 1 < pages ? '' : 'disabled'}>Next</button></span>`;
    $('#pv', el).onclick = () => { T.page--; draw(); };
    $('#nx', el).onclick = () => { T.page++; draw(); };
    $$('tbody tr', el).forEach((r) => r.onclick = () => openTicket(r.dataset.id));
  }
  $$('#st button', el).forEach((b) => b.onclick = () => { T.status = b.dataset.s; T.page = 0; draw(); });
  let tm; $('#tq', el).oninput = (e) => { clearTimeout(tm); tm = setTimeout(() => { T.q = e.target.value.trim(); T.page = 0; draw(); }, 220); };
  $('#rng', el).onchange = (e) => { T.range = e.target.value; T.page = 0; draw(); };
  await draw();
  Views.tickets.refresh = () => draw().catch(() => {});
};

// ---------------------------------------------------------------- Lot camera
Views.lot = async (el) => {
  const L = { dets: null, result: null, editing: false, entrance: false, busy: false };
  let lot;
  async function draw() {
    lot = await api('/api/lot');
    if (!el.isConnected) return;
    const c = lot.counts;
    const title = L.editing ? 'Tap a bay to change its type or close it' : L.entrance ? 'Tap where cars drive in' : 'Lot';
    el.innerHTML = `${head('Lot camera', lot.last_scan ? `Last checked ${ago(lot.last_scan.at)}` : 'Check the overhead camera to find cars without a ticket.',
      isAdmin() ? `<button class="btn ${L.editing ? 'primary' : ''}" id="edit">${icon('edit')}${L.editing ? 'Done' : 'Edit bays'}</button><button class="btn ${L.entrance ? 'primary' : ''}" id="ent">${icon('pin')}${L.entrance ? 'Cancel' : 'Move entrance'}</button>` : '')}
      <div class="lotpage">
        <div class="card"><div class="card-h"><h3>${title}</h3><div class="end">${mapToggle()}</div></div>
          <div class="card-b"><div id="lmap">${lot.slots.length ? lotMap(lot, { detections: L.dets }) : `<div class="empty">${icon('layers')}<b>No layout yet</b></div>`}</div>
          <div class="row" style="margin-top:14px">${mapLegend(lot)}${L.dets ? `<div class="spacer"></div><span class="maplegend"><span><i style="border:2px dashed #f5b13d"></i>Car seen</span><span><i style="border:2px dashed #3ccf86"></i>Empty seen</span></span>` : ''}</div></div></div>
        <div class="stack">
          <div class="card"><div class="card-h"><h3>Check the camera</h3></div><div class="card-b stack">
            <label class="drop" id="drop">${icon('upload')}<b>Upload an overhead photo</b><span class="small">The model marks which bays really have a car</span><input type="file" accept="image/*" hidden id="file"></label>
            <div><div class="small muted" style="margin-bottom:8px">Or try a sample frame</div>
              <div class="samples">${S.samples.map((s) => `<button data-s="${esc(s.name)}" title="${esc(s.name)}"><img src="${media(s.src)}" alt="${esc(s.name)}" loading="lazy"></button>`).join('')}</div></div>
            ${!visionReady() ? `<div class="notice">${icon('alert')}<span>${S.health.vision.state === 'loading' ? 'Cameras are starting. This takes about 10 seconds.' : 'Vision is unavailable.'}</span></div>` : ''}
            <div id="scanres"></div></div></div>
          <div class="card"><div class="card-h"><h3>Bays</h3></div><div class="card-b stack">
            <div class="minis"><div><b>${lot.capacity}</b><span>open</span></div><div><b>${c.untracked}</b><span>no ticket</span></div><div><b>${c.closed}</b><span>closed</span></div></div>
            <div class="row"><button class="btn sm" id="clear" ${lot.last_scan ? '' : 'disabled'}>${icon('x')}Clear camera data</button>
              ${isAdmin() ? `<button class="btn sm" id="remap">${icon('layers')}Re-map lot</button>` : ''}</div></div></div>
        </div></div>`;
    wireMapToggle(el, draw);
    wireMap($('#lmap', el), lot, onBay);
    const svg = $('#lmap svg', el);
    if (L.entrance && svg) {
      $('#lmap .lotmap', el).classList.add('entrance-mode');
      svg.addEventListener('click', async (e) => {
        e.stopPropagation();
        const r = svg.getBoundingClientRect();
        try { await api('/api/settings', { method: 'PUT', body: { entrance: { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height } } }); L.entrance = false; toast('Entrance moved. Routes now start here.'); draw(); } catch (err) { fail(err); }
      }, { capture: true });
    }
    if (L.result) drawResult();
    $('#file', el).onchange = (e) => e.target.files[0] && runScan({ file: e.target.files[0] });
    const drop = $('#drop', el);
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('over'); };
    drop.ondragleave = () => drop.classList.remove('over');
    drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('over'); e.dataTransfer.files[0] && runScan({ file: e.dataTransfer.files[0] }); };
    $$('.samples button', el).forEach((b) => b.onclick = () => runScan({ sample: b.dataset.s }));
    $('#clear', el).onclick = async () => { await api('/api/lot/clear-camera', { method: 'POST' }).catch(fail); L.dets = null; L.result = null; draw(); };
    const rm = $('#remap', el); if (rm) rm.onclick = remap;
    const ed = $('#edit', el); if (ed) ed.onclick = () => { L.editing = !L.editing; L.entrance = false; draw(); };
    const en = $('#ent', el); if (en) en.onclick = () => { L.entrance = !L.entrance; L.editing = false; draw(); };
  }
  function onBay(s) {
    if (L.entrance) return;
    if (L.editing) return editBay(s);
    if (s.ticket) openTicket(s.ticket.id);
    else location.hash = `#/gate?slot=${s.id}`;
  }
  function editBay(s) {
    const m = modal({ title: `Bay ${s.label}`,
      body: `<div class="stack"><label class="f">Type<select class="input" id="kind">${S.kinds.map((k) => `<option value="${k}" ${k === s.kind ? 'selected' : ''}>${esc(KIND_LABEL[k])}</option>`).join('')}</select></label>
        <label class="switch"><input type="checkbox" id="en" ${s.enabled ? 'checked' : ''}>Open for parking</label>
        <p class="muted small">EVs go to EV bays first; other cars only use them when nothing else is free. Accessible bays are kept for drivers who need them.</p></div>`,
      actions: `<button class="btn" data-c>Cancel</button><button class="btn primary" data-s>Save</button>` });
    $('[data-c]', m.el).onclick = () => m.close();
    $('[data-s]', m.el).onclick = async () => {
      try { await api(`/api/slots/${s.id}`, { method: 'PATCH', body: { kind: $('#kind', m.el).value, enabled: $('#en', m.el).checked } }); m.close(); draw(); } catch (e) { fail(e); }
    };
  }
  async function runScan({ file, sample }) {
    if (!visionReady()) return toast('Cameras are still starting. Try again in a few seconds.', 'error');
    if (L.busy) return;
    L.busy = true;
    $('#scanres', el).innerHTML = `<div class="row muted small">${icon('scan')} Looking at the lot…</div>`;
    const fd = new FormData();
    if (file) fd.append('image', file); else fd.append('sample', sample);
    try { L.result = await api('/api/lot/scan', { method: 'POST', form: fd }); L.dets = L.result.detections; S.mapMode = 'photo'; await draw(); }
    catch (e) { fail(e); const r = $('#scanres', el); if (r) r.innerHTML = ''; } finally { L.busy = false; }
  }
  function drawResult() {
    const r = L.result, box = $('#scanres', el); if (!box) return;
    box.innerHTML = `<div class="minis"><div><b>${r.cars}</b><span>with a car</span></div><div><b>${r.free}</b><span>empty</span></div><div><b>${r.untracked.length}</b><span>no ticket</span></div></div>
      ${r.untracked.length ? `<div class="notice" style="margin-top:12px">${icon('alert')}<span>No ticket for the cars in <b>${r.untracked.map(esc).join(', ')}</b>. Tap one on the map to ticket it.</span></div>` : `<div class="notice info" style="margin-top:12px">${icon('check')}<span>Every car the camera sees has a ticket.</span></div>`}
      ${r.ghosts.length ? `<div class="notice danger" style="margin-top:10px">${icon('alert')}<span>Ticketed but empty: <b>${r.ghosts.map(esc).join(', ')}</b>. The driver may have left without paying.</span></div>` : ''}
      ${r.stray ? `<p class="muted small" style="margin-top:8px">${plural(r.stray, 'car')} seen outside any bay.</p>` : ''}`;
  }
  async function remap() {
    const m = modal({ title: 'Re-map the lot', wide: true,
      body: `<div class="stack"><p class="muted">Pick a clear overhead frame. The model finds every bay and rebuilds the layout. Bay types reset, and all tickets must be closed first.</p>
        <div class="samples">${S.samples.map((s) => `<button data-s="${esc(s.name)}"><img src="${media(s.src)}" alt=""></button>`).join('')}</div>
        <label class="drop">${icon('upload')}<b>Or upload a frame</b><input type="file" hidden accept="image/*" id="rf"></label></div>` });
    const go = async (fd) => {
      if (!visionReady()) return toast('Cameras are still starting.', 'error');
      try { const r = await api('/api/lot/calibrate', { method: 'POST', form: fd }); m.close(); toast(`Mapped ${r.bays} bays`); L.dets = null; L.result = null; draw(); } catch (e) { fail(e); }
    };
    $$('.samples button', m.el).forEach((b) => b.onclick = () => { const fd = new FormData(); fd.append('sample', b.dataset.s); go(fd); });
    $('#rf', m.el).onchange = (e) => { const fd = new FormData(); fd.append('image', e.target.files[0]); go(fd); };
  }
  await draw();
  Views.lot.refresh = () => { if (!L.busy) draw().catch(() => {}); };
};

// ---------------------------------------------------------------- Settings
Views.settings = async (el) => {
  const st = S.settings, admin = isAdmin(), dis = admin ? '' : 'disabled';
  el.innerHTML = `${head('Settings', admin ? 'Prices, payments and your team.' : 'Only admins can change these.', admin ? `<button class="btn primary" id="save">${icon('check')}Save changes</button>` : '')}
    <div class="settings">
      <div class="stack">
        <div class="card"><div class="card-h"><h3>Prices</h3><span class="meta">first hour flat, then each started hour</span></div><div class="card-b">
          <table class="tariffs"><thead><tr><th></th><th>Free min</th><th>1st hour</th><th>Per hour</th><th>Daily max</th><th>3 hours</th></tr></thead><tbody>
          ${Object.keys(S.classes).map((k) => { const t = st.tariffs[k]; return `<tr data-c="${k}"><td>${esc(SHORT_CLASS[k])}</td>
            ${['grace_min', 'first_hour', 'per_hour', 'daily_cap'].map((f) => `<td><input class="input" type="number" min="0" step="${f === 'grace_min' ? 1 : 0.5}" data-f="${f}" value="${t[f]}" ${dis} aria-label="${k} ${f}"></td>`).join('')}
            <td class="ex num">${money(fareJS(180, t))}</td></tr>`; }).join('')}</tbody></table></div></div>
        <div class="card"><div class="card-h"><h3>Lot & payments</h3></div><div class="card-b stack">
          <label class="f">Lot name<input class="input" id="lot_name" value="${esc(st.lot_name)}" maxlength="60" ${dis}></label>
          <label class="f">UPI ID <small>shown as a QR code at checkout</small><input class="input" id="upi_id" value="${esc(st.upi_id)}" placeholder="yourname@okaxis" ${dis}></label>
          <div class="grid2"><label class="f">Payee name<input class="input" id="payee_name" value="${esc(st.payee_name)}" maxlength="60" ${dis}></label>
            <label class="f">Currency<input class="input" id="currency" value="${esc(st.currency)}" maxlength="4" ${dis}></label></div>
        </div></div>
      </div>
      <div class="stack">
        ${admin ? `<div class="card"><div class="card-h"><h3>Team</h3><div class="end"><button class="btn sm" id="adduser">${icon('plus')}Add</button></div></div><div class="card-b flush" id="team"></div></div>` : ''}
        <div class="card"><div class="card-h"><h3>System</h3></div><div class="card-b"><dl class="kv">
          <dt>Version</dt><dd>${esc(S.health.version)}</dd>
          <dt>Cameras</dt><dd>${esc(S.health.vision.detail || S.health.vision.state)}</dd>
          <dt>Assistant</dt><dd>${S.health.ai ? 'Gemini' : 'Built-in (add GEMINI_API_KEY for Gemini)'}</dd>
          <dt>Shortcuts</dt><dd><span class="key">G</span> gate · <span class="key">O</span> overview · <span class="key">T</span> tickets · <span class="key">L</span> lot</dd>
        </dl></div></div>
      </div></div>`;
  $$('.tariffs tr[data-c] input', el).forEach((i) => i.oninput = () => {
    const tr = i.closest('tr'); $('.ex', tr).textContent = money(fareJS(180, Object.fromEntries($$('input', tr).map((x) => [x.dataset.f, +x.value || 0]))));
  });
  if (!admin) return;
  $('#save', el).onclick = async () => {
    const tariffs = Object.fromEntries($$('.tariffs tr[data-c]', el).map((tr) => [tr.dataset.c, Object.fromEntries($$('input', tr).map((x) => [x.dataset.f, +x.value || 0]))]));
    try {
      S.settings = await api('/api/settings', { method: 'PUT', body: { lot_name: $('#lot_name', el).value, currency: $('#currency', el).value, payee_name: $('#payee_name', el).value, upi_id: $('#upi_id', el).value, tariffs } });
      $('#lotname').textContent = S.settings.lot_name;
      toast('Saved');
    } catch (e) { fail(e); }
  };
  async function team() {
    const users = await api('/api/users');
    const box = $('#team', el); if (!box) return;
    box.innerHTML = users.map((u, i) => `<div style="display:flex;align-items:center;gap:12px;padding:12px 20px;${i ? 'border-top:1px solid var(--line)' : ''}">
      <div class="avatar">${esc(u.name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase())}</div>
      <div style="flex:1;min-width:0"><b>${esc(u.name)}</b> ${u.active ? '' : '<span class="tag void">inactive</span>'}<div class="small muted">@${esc(u.username)} · ${u.role}</div></div>
      ${u.id === S.me.id ? '<span class="small muted">you</span>' : `<button class="btn sm quiet" data-pw="${u.id}">Reset password</button><button class="btn sm quiet" data-act="${u.id}" data-on="${u.active ? 0 : 1}">${u.active ? 'Deactivate' : 'Activate'}</button>`}</div>`).join('');
    $$('[data-act]', box).forEach((b) => b.onclick = async () => { try { await api(`/api/users/${b.dataset.act}`, { method: 'PATCH', body: { active: b.dataset.on === '1' } }); team(); } catch (e) { fail(e); } });
    $$('[data-pw]', box).forEach((b) => b.onclick = async () => {
      const pw = await promptBox('Reset password', 'New password (8+ characters with a number or symbol)', '', { okLabel: 'Set password' });
      if (!pw) return;
      try { await api(`/api/users/${b.dataset.pw}`, { method: 'PATCH', body: { password: pw } }); toast('Password updated'); } catch (e) { fail(e); }
    });
  }
  $('#adduser', el).onclick = () => {
    const m = modal({ title: 'Add a team member', body: `<form class="stack" id="uf">
      <label class="f">Name<input class="input" name="name" required maxlength="60"></label>
      <label class="f">Username<input class="input" name="username" required maxlength="40" pattern="[A-Za-z0-9._]+"></label>
      <label class="f">Temporary password<input class="input" name="password" type="text" minlength="8" required></label>
      <label class="f">Role<select class="input" name="role"><option value="operator">Operator: gate, tickets, camera</option><option value="admin">Admin: everything, including settings</option></select></label></form>`,
      actions: `<button class="btn" data-c>Cancel</button><button class="btn primary" data-s>Add</button>` });
    $('[data-c]', m.el).onclick = () => m.close();
    $('[data-s]', m.el).onclick = async () => {
      const f = $('#uf', m.el); if (!f.reportValidity()) return;
      try { await api('/api/users', { method: 'POST', body: Object.fromEntries(new FormData(f)) }); m.close(); toast('Added'); team(); } catch (e) { fail(e); }
    };
  };
  await team();
};

// ================================================================== assistant
function toggleAssistant() {
  const d = $('#drawer');
  if (d.classList.contains('on')) { d.classList.remove('on'); return; }
  d.innerHTML = `<div class="drawer-h">${icon('spark')}<h3>Ask SmartPark</h3><span class="tag">${S.health.ai ? 'Gemini' : 'Built-in'}</span><button class="btn quiet icon sm" id="cx" aria-label="Close">${icon('x')}</button></div>
    <div class="chat" id="chat"></div>
    <div class="suggest" id="sug">${['How many bays are free?', 'Any problems?', "Today's money", 'Price for 3 hours?', 'Who has been parked longest?'].map((s) => `<button>${esc(s)}</button>`).join('')}</div>
    <form class="composer" id="cf"><input class="input" id="ci" placeholder="Ask about the lot…" autocomplete="off" maxlength="500"><button class="btn primary icon" aria-label="Send">${icon('send')}</button></form>`;
  d.classList.add('on');
  $('#cx').onclick = () => d.classList.remove('on');
  $$('#sug button').forEach((b) => b.onclick = () => ask(b.textContent));
  $('#cf').onsubmit = (e) => { e.preventDefault(); const v = $('#ci').value.trim(); if (v) { $('#ci').value = ''; ask(v); } };
  drawChat(); $('#ci').focus();
}
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
function drawChat() {
  const c = $('#chat'); if (!c) return;
  c.innerHTML = S.chat.length ? S.chat.map((m, i) => `<div class="msg ${m.role} ${S.chatBusy && i === S.chat.length - 1 && m.role === 'assistant' ? 'typing' : ''}">${md(m.content)}</div>`).join('')
    : `<div class="empty">${icon('spark')}<span>Ask about free bays, a plate, prices, money or problems. Answers come from the live lot.</span></div>`;
  c.scrollTop = c.scrollHeight;
}
async function ask(text) {
  if (S.chatBusy) return;
  S.chat.push({ role: 'user', content: text }, { role: 'assistant', content: '' });
  S.chatBusy = true; drawChat();
  try {
    const res = await api('/api/assistant', { method: 'POST', body: { messages: S.chat.slice(0, -1).slice(-12) }, raw: true });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || 'Assistant error');
    const reader = res.body.getReader(), dec = new TextDecoder();
    for (;;) { const { done, value } = await reader.read(); if (done) break; S.chat[S.chat.length - 1].content += dec.decode(value, { stream: true }); drawChat(); }
  } catch (e) { S.chat[S.chat.length - 1].content = `Sorry: ${e.message}`; }
  S.chatBusy = false; drawChat();
}

// ================================================================== boot
document.addEventListener('keydown', (e) => {
  if (!S.me || e.ctrlKey || e.metaKey || e.altKey || e.target.matches('input, textarea, select') || $('.scrim')) return;
  if (S.view === 'gate') return;  // the gate captures typing for the plate box
  const v = { g: 'gate', e: 'gate', x: 'gate', o: 'overview', d: 'overview', t: 'tickets', l: 'lot' }[e.key.toLowerCase()];
  if (v) { e.preventDefault(); location.hash = `#/${v}`; }
});
window.addEventListener('hashchange', () => { if (S.me) route(); });

async function start() {
  try { S.health = await api('/api/health'); } catch (e) {
    $('#app').innerHTML = `<div class="boot"><div class="card" style="padding:28px;max-width:420px;text-align:center"><div class="empty">${icon('alert')}<b>${esc(e.message)}</b></div><button class="btn" onclick="location.reload()">Try again</button></div></div>`;
    return;
  }
  if (S.health.setup_needed) return renderSetup();
  let me;
  try { me = await api('/api/me'); } catch (e) { if (e.status === 401) return renderLogin(); return fail(e); }
  S.me = me.user; S.settings = me.settings; S.classes = me.classes; S.kinds = me.slot_kinds; S.samples = me.samples;
  renderShell();
  startStream();
  if (S.health.vision.state === 'loading') {
    const poll = setInterval(async () => {
      try { S.health = await api('/api/health'); updateStatus(); if (S.health.vision.state !== 'loading') { clearInterval(poll); refreshView(); } } catch (e) { /* ignore */ }
    }, 3000);
  }
  if (!location.hash || location.hash === '#' || location.hash === '#/') history.replaceState(null, '', '#/overview');
  route();
}
start();
