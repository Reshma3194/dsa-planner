// UI primitives. All DOM is built with h() / textContent, so user text (notes, names) is never parsed as HTML.

const SVG_NS = 'http://www.w3.org/2000/svg';

// Static, trusted SVG path data (24x24 grid, stroked).
const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  calendar: '<rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9.5h18M8 3v3M16 3v3"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  right: '<path d="m9 6 6 6-6 6"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.9-3M4 4v4h4M4 13a8 8 0 0 0 14.9 3M20 20v-4h-4"/>',
  download: '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
};

export function icon(name) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.75');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = ICONS[name] || '';
  return svg;
}

const DEFERRED = ['value', 'selected'];
const PROPS = ['checked', 'disabled', 'hidden', 'indeterminate'];

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

/** Tiny hyperscript: h('div', {class: 'x', onclick: fn}, child, ...). */
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  const deferred = [];
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (DEFERRED.includes(k)) deferred.push([k, v]);
    else if (PROPS.includes(k)) el[k] = v;
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  append(el, children);
  for (const [k, v] of deferred) el[k] = v; // after children so <select> options exist
  return el;
}

// ------------------------------------------------------------------ status model
export const STATUS = {
  todo: { label: 'Pending', long: 'Pending', desc: 'Not attempted yet' },
  solved: { label: 'Solved', long: 'Solved', desc: 'Solved on my own, no help' },
  hinted: { label: 'Hints', long: 'Solved with hints', desc: 'Needed hints or a nudge to finish' },
  redo: { label: 'Redo', long: 'Redo', desc: 'Used AI or the editorial, or could not finish alone' },
};
export const STATUS_ORDER = ['todo', 'solved', 'hinted', 'redo'];

// ------------------------------------------------------------------ formatting
export function parseDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}
export const fmtDate = (iso, opts = { weekday: 'short', day: 'numeric', month: 'short' }) =>
  new Intl.DateTimeFormat(undefined, opts).format(parseDate(iso));
export const fmtLong = (iso) => fmtDate(iso, { weekday: 'long', day: 'numeric', month: 'long' });
export function fmtMin(m) {
  if (m < 60) return `${m}m`;
  const hrs = Math.floor(m / 60);
  const rest = m % 60;
  return rest ? `${hrs}h ${rest}m` : `${hrs}h`;
}
export const plural = (n, word, many) => `${n} ${n === 1 ? word : many || word + 's'}`;
export const diffClass = (d) => `diff diff-${String(d).toLowerCase()}`;

// ------------------------------------------------------------------ toasts
let toastHost;
export function toast(message, kind = 'info', ms = 4200) {
  if (!toastHost) {
    toastHost = h('div', { class: 'toast-host', role: 'status', 'aria-live': 'polite' });
    document.body.append(toastHost);
  }
  const el = h('div', { class: `toast ${kind === 'error' ? 'error' : ''}` }, message);
  toastHost.append(el);
  setTimeout(() => el.remove(), kind === 'error' ? ms * 1.6 : ms);
}

// ------------------------------------------------------------------ popover menu
let openMenuState = null;

export function closeMenu() {
  if (!openMenuState) return;
  openMenuState.el.remove();
  document.removeEventListener('pointerdown', openMenuState.onDown, true);
  document.removeEventListener('keydown', openMenuState.onKey, true);
  window.removeEventListener('resize', closeMenu);
  window.removeEventListener('scroll', closeMenu, true);
  openMenuState.anchor.setAttribute('aria-expanded', 'false');
  openMenuState = null;
}

/** items: [{value, title, desc?, selected?}] */
export function openMenu(anchor, items, onSelect) {
  closeMenu();
  const buttons = items.map((it) =>
    h(
      'button',
      {
        class: 'menu-item',
        type: 'button',
        role: 'menuitem',
        onclick: () => {
          closeMenu();
          onSelect(it.value);
        },
      },
      h('span', { class: 't' }, it.title, it.selected ? icon('check') : null),
      it.desc ? h('span', { class: 'd' }, it.desc) : null
    )
  );
  const el = h('div', { class: 'menu', role: 'menu' }, buttons);
  document.body.append(el);
  const r = anchor.getBoundingClientRect();
  const mw = el.offsetWidth;
  const mh = el.offsetHeight;
  let left = Math.min(r.left, window.innerWidth - mw - 8);
  let top = r.bottom + 4;
  if (top + mh > window.innerHeight - 8) top = Math.max(8, r.top - mh - 4);
  el.style.left = `${Math.max(8, left)}px`;
  el.style.top = `${top}px`;

  const onDown = (e) => {
    if (!el.contains(e.target) && !anchor.contains(e.target)) closeMenu();
  };
  const onKey = (e) => {
    if (e.key === 'Escape') {
      closeMenu();
      anchor.focus();
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const i = buttons.indexOf(document.activeElement);
      const next = e.key === 'ArrowDown' ? (i + 1) % buttons.length : (i - 1 + buttons.length) % buttons.length;
      buttons[next].focus();
    }
  };
  document.addEventListener('pointerdown', onDown, true);
  document.addEventListener('keydown', onKey, true);
  window.addEventListener('resize', closeMenu);
  window.addEventListener('scroll', closeMenu, true);
  anchor.setAttribute('aria-expanded', 'true');
  openMenuState = { el, anchor, onDown, onKey };
  (buttons.find((_, i) => items[i].selected) || buttons[0]).focus();
}

/** A status pill that opens a menu. `onChange(newStatus, prevStatus)` should persist; throw to revert. */
export function statusButton(item, onChange) {
  const label = h('span', null, STATUS[item.status].label);
  const btn = h('button', { class: `pill pill-${item.status}`, type: 'button', 'aria-haspopup': 'menu', 'aria-expanded': 'false', title: 'Change status' }, label, icon('down'));
  const paint = () => {
    btn.className = `pill pill-${item.status}`;
    label.textContent = STATUS[item.status].label;
  };
  btn.addEventListener('click', () => {
    openMenu(
      btn,
      STATUS_ORDER.map((s) => ({ value: s, title: STATUS[s].long, desc: STATUS[s].desc, selected: item.status === s })),
      async (s) => {
        const prev = item.status;
        item.status = s;
        paint();
        try {
          await onChange(s, prev);
        } catch (e) {
          item.status = prev;
          paint();
          toast(e.message, 'error');
        }
      }
    );
  });
  return btn;
}

// ------------------------------------------------------------------ modal & drawer
function mountLayer(kind, label, build, opts = {}) {
  const previous = document.activeElement;
  const scrim = h('div', { class: `scrim ${kind}` });
  const close = () => {
    document.removeEventListener('keydown', onKey, true);
    scrim.remove();
    if (previous && previous.focus) previous.focus();
    if (opts.onClose) opts.onClose();
  };
  const onKey = (e) => {
    if (e.key === 'Escape' && !openMenuState) close();
  };
  const { body, footer } = build({ close });
  const head = h(
    'div',
    { class: kind === 'center' ? 'modal-head' : 'drawer-head' },
    h('h2', { class: 'modal-title' }, label),
    h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Close', onclick: close }, icon('x'))
  );
  let panel;
  if (kind === 'center') {
    panel = h('div', { class: `modal ${opts.size || ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': label }, head, h('div', { class: 'modal-body' }, body), footer ? h('div', { class: 'modal-foot' }, footer) : null);
  } else {
    panel = h('aside', { class: 'drawer', role: 'dialog', 'aria-modal': 'true', 'aria-label': label }, head, h('div', { class: 'drawer-body' }, body));
  }
  scrim.append(panel);
  scrim.addEventListener('pointerdown', (e) => {
    if (e.target === scrim) close();
  });
  document.addEventListener('keydown', onKey, true);
  document.body.append(scrim);
  const first = panel.querySelector('input, textarea, select, button:not(.icon-btn)');
  if (first) first.focus();
  return { close, panel };
}

export const openModal = (title, build, opts) => mountLayer('center', title, build, opts);
export const openDrawer = (title, build, opts) => mountLayer('right', title, build, opts);

export function confirmDialog({ title, message, confirmLabel = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (v) => {
      if (!settled) {
        settled = true;
        resolve(v);
      }
    };
    openModal(
      title,
      ({ close }) => ({
        body: h('p', { class: 'muted', style: { color: 'var(--text-2)' } }, message),
        footer: [
          h('button', { class: 'btn', type: 'button', onclick: () => { done(false); close(); } }, 'Cancel'),
          h('button', { class: `btn ${danger ? 'btn-danger' : 'btn-primary'}`, type: 'button', onclick: () => { done(true); close(); } }, confirmLabel),
        ],
      }),
      { size: 'small', onClose: () => done(false) }
    );
  });
}

// ------------------------------------------------------------------ building blocks
export function pageHeader({ title, sub, actions }) {
  return h(
    'div',
    { class: 'page-head' },
    h('div', null, h('h1', { class: 'page-title' }, title), sub ? h('p', { class: 'page-sub' }, sub) : null),
    actions && actions.length ? h('div', { class: 'page-actions' }, actions) : null
  );
}

export function card({ title, meta, actions, className = '' }, ...children) {
  const head =
    title || meta || actions
      ? h(
          'div',
          { class: 'card-head' },
          h('div', { class: 'card-title' }, title),
          h('div', { class: 'card-meta' }, meta, actions)
        )
      : null;
  return h('section', { class: `card ${className}` }, head, children);
}

export const bar = (pct, thin = false) =>
  h('div', { class: `bar ${thin ? 'thin' : ''}`, role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(pct) }, h('i', { style: { width: `${Math.max(0, Math.min(100, pct))}%` } }));

export function stat(label, value, small, sub, pct) {
  return h(
    'div',
    { class: 'stat' },
    h('div', { class: 'stat-label' }, label),
    h('div', { class: 'stat-value' }, value, small ? h('small', null, small) : null),
    sub ? h('div', { class: 'stat-sub' }, sub) : null,
    pct !== undefined ? bar(pct) : null
  );
}

export function emptyState({ title, text, action }) {
  return h('div', { class: 'empty' }, h('h2', null, title), h('p', null, text), action || null);
}

export const loading = (text = 'Loading') => h('div', { class: 'loading' }, h('span', { class: 'spinner' }), text);

/**
 * One problem row. variant 'plan' (status, title, level, minutes, link) or 'list' (adds topic and plan flag).
 */
export function problemRow(item, { ctx, onStatus, variant = 'plan', review = false }) {
  const isList = variant === 'list';
  const sub = [item.pattern, review ? 're-solve without hints' : null].filter(Boolean).join(' · ');
  return h(
    'div',
    { class: `prow ${isList ? 'wide' : ''} ${review ? 'prow-review' : ''}`, role: 'listitem' },
    statusButton(item, onStatus),
    h(
      'div',
      { style: { minWidth: 0 } },
      h('button', { class: 'prow-title', type: 'button', title: item.title, onclick: () => ctx.openProblem(item.slug) }, item.title),
      h('div', { class: 'prow-sub' }, sub)
    ),
    h('span', { class: diffClass(item.difficulty) }, item.difficulty),
    isList ? h('span', { class: 'hide-sm muted' }, item.topic) : null,
    isList
      ? h('span', { class: 'hide-sm' }, item.in_plan ? h('span', { class: 'tag tag-accent' }, 'In plan') : null)
      : h('span', { class: 'prow-min hide-sm' }, item.minutes ? `${item.minutes}m` : ''),
    h('a', { class: 'icon-btn', href: item.url, target: '_blank', rel: 'noopener noreferrer', 'aria-label': `Open ${item.title} on LeetCode`, title: 'Open on LeetCode' }, icon('external'))
  );
}

/** Mini bar chart of planned minutes per day (study days dark, review days accent). */
export function sparkBars(days) {
  const n = Math.max(days.length, 1);
  const max = Math.max(...days.map((d) => d.planned_minutes), 1);
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${n * 6} 46`);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('class', 'sparkbars');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Planned minutes per day');
  days.forEach((d, i) => {
    const hgt = Math.max(2, (d.planned_minutes / max) * 44);
    const r = document.createElementNS(SVG_NS, 'rect');
    r.setAttribute('x', i * 6);
    r.setAttribute('y', 46 - hgt);
    r.setAttribute('width', 4.2);
    r.setAttribute('height', hgt);
    r.setAttribute('rx', 1);
    r.style.fill = d.kind === 'review' ? 'var(--accent)' : 'var(--text-3)';
    svg.append(r);
  });
  return svg;
}
