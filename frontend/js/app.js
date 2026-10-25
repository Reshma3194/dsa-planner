import { api } from './api.js';
import { bar, closeMenu, fmtDate, h, icon, loading } from './ui.js';
import { dashboardView } from './views/dashboard.js';
import { planView } from './views/plan.js';
import { problemsView } from './views/problems.js';
import { openPlanForm } from './views/plan-form.js';
import { openProblemDrawer } from './views/problem-drawer.js';

const ROUTES = {
  '': { title: 'Today', icon: 'dashboard', view: dashboardView },
  plan: { title: 'Plan', icon: 'calendar', view: planView },
  problems: { title: 'Problems', icon: 'list', view: problemsView },
};

const routeKey = () => location.hash.replace(/^#\/?/, '').split('?')[0];

let main;
let miniPlan;
let navLinks;
let token = 0;
let sidebarTimer;

const ctx = {
  meta: { topics: [] },
  navigate(route, force = false) {
    const target = `#/${route}`;
    if (location.hash === target || (route === '' && (location.hash === '' || location.hash === '#/'))) {
      if (force) render();
    } else {
      location.hash = target;
    }
  },
  rerender: () => render({ keepScroll: true }),
  openPlanForm: () => openPlanForm(ctx),
  openProblem: (slug) => openProblemDrawer(slug, ctx),
  updateSidebar(dash) {
    if (!miniPlan) return;
    if (!dash || !dash.has_plan) {
      miniPlan.replaceChildren(h('span', { class: 'muted' }, 'No active plan'));
      return;
    }
    const p = dash.plan;
    const label = p.state === 'active' ? `Day ${p.day_number} of ${p.total_days}` : p.state === 'upcoming' ? `Starts ${fmtDate(p.start_date)}` : 'Plan complete';
    miniPlan.replaceChildren(
      h('div', { class: 'row' }, h('b', null, label), h('span', { class: 'muted' }, `${p.progress.pct}%`)),
      bar(p.progress.pct, true),
      h('div', { class: 'muted', style: { marginTop: '8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, p.name)
    );
  },
  refreshSidebar() {
    clearTimeout(sidebarTimer);
    sidebarTimer = setTimeout(() => api.dashboard().then(ctx.updateSidebar).catch(() => {}), 250);
  },
};

function errorCard(message, retry) {
  return h(
    'div',
    { class: 'page' },
    h('div', { class: 'empty' }, h('h2', null, 'Something went wrong'), h('p', null, message), h('button', { class: 'btn btn-primary', type: 'button', onclick: retry }, icon('refresh'), 'Try again'))
  );
}

async function render({ keepScroll = false } = {}) {
  const key = routeKey();
  const def = ROUTES[key] || ROUTES[''];
  const active = ROUTES[key] ? key : '';
  navLinks.forEach((a) => a.classList.toggle('active', a.dataset.route === active));
  document.title = `${def.title} · DSA Planner`;
  closeMenu();
  const mine = ++token;
  const y = window.scrollY;
  if (!keepScroll) main.replaceChildren(loading());
  try {
    const node = await def.view(ctx);
    if (mine !== token) return;
    main.replaceChildren(node);
    window.scrollTo(0, keepScroll ? y : 0);
    if (!keepScroll && typeof node.afterMount === 'function') node.afterMount();
  } catch (e) {
    if (mine !== token) return;
    main.replaceChildren(errorCard(e.message, () => render()));
  }
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem('dsa-theme', theme);
  } catch {
    /* storage unavailable */
  }
}

function buildShell() {
  const app = document.getElementById('app');
  app.className = 'app';
  navLinks = Object.entries(ROUTES).map(([key, r]) => h('a', { href: `#/${key}`, 'data-route': key }, icon(r.icon), h('span', null, r.title)));
  miniPlan = h('div', { class: 'mini-plan' }, h('span', { class: 'muted' }, 'Loading…'));
  const themeBtn = h('button', { class: 'btn btn-ghost btn-sm', type: 'button', 'aria-label': 'Toggle dark mode' });
  const paintTheme = () => {
    const dark = document.documentElement.dataset.theme === 'dark';
    themeBtn.replaceChildren(icon(dark ? 'sun' : 'moon'), dark ? 'Light mode' : 'Dark mode');
  };
  themeBtn.addEventListener('click', () => {
    setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
    paintTheme();
  });
  paintTheme();
  main = h('main', { class: 'main', id: 'main' });
  app.replaceChildren(
    h(
      'aside',
      { class: 'sidebar' },
      h('div', { class: 'brand' }, h('span', { class: 'brand-mark' }, 'D'), 'DSA Planner'),
      h('nav', { class: 'nav', 'aria-label': 'Main' }, navLinks),
      h('div', { class: 'sidebar-foot' }, miniPlan, themeBtn)
    ),
    main
  );
}

async function boot() {
  buildShell();
  try {
    ctx.meta = await api.meta();
  } catch (e) {
    main.replaceChildren(errorCard(e.message, () => location.reload()));
    return;
  }
  window.addEventListener('hashchange', () => render());
  await render();
  ctx.refreshSidebar();
}

boot();
