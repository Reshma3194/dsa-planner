import { api } from '../api.js';
import { STATUS, STATUS_ORDER, h, icon, pageHeader, problemRow, toast } from '../ui.js';

// Filters survive navigating away and back.
const filters = { q: '', topic: '', difficulty: '', status: '' };

export async function problemsView(ctx) {
  const page = h('div', { class: 'page' });
  const subtitle = h('span', null, 'Loading…');
  page.append(pageHeader({ title: 'Problems', sub: subtitle }));

  const results = h('div', { class: 'card' });
  let seq = 0;

  const load = async () => {
    const mine = ++seq;
    try {
      const data = await api.problems(filters);
      if (mine !== seq) return; // a newer request superseded this one
      subtitle.textContent = `${data.count} free LeetCode ${data.count === 1 ? 'problem' : 'problems'}${Object.values(filters).some(Boolean) ? ' match your filters' : ''}`;
      const list = h('div', { class: 'rows', role: 'list' });
      if (!data.problems.length) list.append(h('div', { class: 'card-body muted' }, 'No problems match these filters.'));
      data.problems.forEach((p) =>
        list.append(
          problemRow(p, {
            ctx,
            variant: 'list',
            onStatus: async (s) => {
              await api.updateProblem(p.slug, { status: s });
              ctx.refreshSidebar();
              if (filters.status) load(); // the row may no longer match the status filter
            },
          })
        )
      );
      results.replaceChildren(
        h('div', { class: 'rows-head hide-sm' }, h('span', null, 'Status'), h('span', null, 'Problem'), h('span', null, 'Level'), h('span', null, 'Topic'), h('span', null, 'Plan'), h('span')),
        list
      );
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  let timer;
  const search = h('input', {
    class: 'input',
    type: 'search',
    placeholder: 'Search by title or pattern',
    'aria-label': 'Search problems',
    value: filters.q,
    oninput: (e) => {
      filters.q = e.target.value;
      clearTimeout(timer);
      timer = setTimeout(load, 200);
    },
  });
  const select = (key, label, options) =>
    h(
      'select',
      {
        class: 'select',
        'aria-label': label,
        value: filters[key],
        onchange: (e) => {
          filters[key] = e.target.value;
          load();
        },
      },
      h('option', { value: '' }, label),
      options.map(([v, t]) => h('option', { value: v }, t))
    );

  page.append(
    h(
      'div',
      { class: 'toolbar' },
      h('div', { class: 'search' }, icon('search'), search),
      select('topic', 'All topics', ctx.meta.topics.map((t) => [t.topic, `${t.topic} (${t.count})`])),
      select('difficulty', 'All levels', [['easy', 'Easy'], ['medium', 'Medium'], ['hard', 'Hard']]),
      select('status', 'Any status', STATUS_ORDER.map((s) => [s, STATUS[s].long]))
    ),
    results
  );
  await load();
  return page;
}
