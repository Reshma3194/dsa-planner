import { api } from '../api.js';
import { STATUS, bar, card, emptyState, fmtDate, fmtLong, fmtMin, h, icon, pageHeader, plural, problemRow, stat, statusButton, toast, diffClass } from '../ui.js';

function subtitle(d) {
  const p = d.plan;
  if (!p) return fmtLong(d.today);
  if (p.state === 'active') return `${fmtLong(d.today)} · Day ${p.day_number} of ${p.total_days}`;
  if (p.state === 'upcoming') return `${fmtLong(d.today)} · Plan starts ${fmtDate(p.start_date)}`;
  return `${fmtLong(d.today)} · Plan ended ${fmtDate(p.end_date)}`;
}

function todayCard(d, ctx) {
  const day = d.today_day;
  const onStatus = (item) => async (s) => {
    await api.updateProblem(item.slug, { status: s });
    ctx.rerender();
  };
  const isReview = day.kind === 'review';
  const list = h('div', { class: 'rows', role: 'list' });
  if (!day.items.length) {
    list.append(h('div', { class: 'card-body muted' }, 'Rest day. Nothing new is scheduled, so use the time to re-solve something from your revision queue.'));
  }
  day.items.forEach((it) => list.append(problemRow(it, { ctx, onStatus: onStatus(it), review: it.kind === 'review' })));
  return card(
    {
      title: h('span', null, `Day ${day.day}`, h('span', { class: 'muted', style: { fontWeight: 500 } }, ` · ${day.theme}`), isReview ? h('span', { class: 'tag tag-accent', style: { marginLeft: '8px' } }, 'Review') : null),
      meta: [h('span', null, `${day.done}/${day.count} done`), h('span', null, `${fmtMin(day.planned_minutes)} planned`)],
    },
    list,
    h(
      'div',
      { class: 'legend' },
      ...['solved', 'hinted', 'redo', 'todo'].map((s) => h('span', null, h('b', { style: { color: 'var(--text-2)' } }, STATUS[s].long), ` · ${STATUS[s].desc}`))
    )
  );
}

function upNextCard(d) {
  if (!d.upcoming.length) return null;
  return card(
    { title: 'Up next' },
    ...d.upcoming.map((u) =>
      h(
        'div',
        { class: 'list-row' },
        h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, `Day ${u.day} `, h('span', { class: 'muted', style: { fontWeight: 400 } }, fmtDate(u.date))), h('div', { class: 'prow-sub' }, u.theme)),
        h('span', { class: 'muted' }, u.count ? `${plural(u.count, 'problem')} · ${fmtMin(u.planned_minutes)}` : 'Buffer')
      )
    )
  );
}

function revisionCard(d, ctx) {
  const rows = d.revisions.length
    ? d.revisions.map((r) => {
        const item = { ...r };
        return h(
          'div',
          { class: 'list-row' },
          h(
            'div',
            { class: 'grow' },
            h('button', { class: 'prow-title', type: 'button', onclick: () => ctx.openProblem(r.slug) }, r.title),
            h('div', { class: 'prow-sub' }, h('span', { class: diffClass(r.difficulty) }, r.difficulty), ` · ${r.status === 'redo' ? 'Redo' : 'Re-check'} · ${r.days_overdue > 0 ? `${r.days_overdue}d overdue` : 'due today'}`)
          ),
          statusButton(item, async (s) => {
            await api.updateProblem(r.slug, { status: s });
            ctx.rerender();
          }),
          h('a', { class: 'icon-btn', href: r.url, target: '_blank', rel: 'noopener noreferrer', 'aria-label': `Open ${r.title} on LeetCode` }, icon('external'))
        );
      })
    : [h('div', { class: 'card-body muted' }, 'Nothing due. Problems you mark Redo come back here the next day, and Hints problems after 3 days.')];
  return card({ title: 'Revision queue', meta: d.revisions.length ? plural(d.revisions.length, 'problem') + ' due' : null }, ...rows);
}

function topicsCard(d) {
  if (!d.topics.length) return null;
  return card(
    { title: 'Topic progress', meta: d.has_plan ? 'Planned problems' : 'All problems' },
    ...d.topics.map((t) =>
      h(
        'div',
        { class: 'topic-row' },
        h('div', { class: 'top' }, h('span', null, t.topic), h('span', null, `${t.done}/${t.total}`)),
        bar(t.total ? (100 * t.done) / t.total : 0, true)
      )
    )
  );
}

export async function dashboardView(ctx) {
  const d = await api.dashboard();
  ctx.updateSidebar(d);
  const page = h('div', { class: 'page' });

  const actions = [];
  if (d.has_plan) actions.push(h('button', { class: 'btn', type: 'button', onclick: () => ctx.navigate('plan') }, icon('calendar'), 'View plan'));
  actions.push(h('button', { class: 'btn btn-primary', type: 'button', onclick: () => ctx.openPlanForm() }, icon('plus'), d.has_plan ? 'New plan' : 'Create plan'));
  page.append(pageHeader({ title: 'Today', sub: subtitle(d), actions }));

  if (!d.has_plan) {
    page.append(
      emptyState({
        title: 'Build your DSA plan',
        text: 'Tell it how many days you have and how much time you can give each day. It picks free LeetCode problems, schedules them topic by topic, and re-plans when you fall behind.',
        action: h('button', { class: 'btn btn-primary', type: 'button', onclick: () => ctx.openPlanForm() }, icon('plus'), 'Create plan'),
      })
    );
    return page;
  }

  const s = d.stats;
  const p = d.plan.progress;
  page.append(
    h(
      'div',
      { class: 'strip' },
      stat('Plan progress', String(p.done), `/ ${p.total}`, `${p.pct}% of planned problems`, p.pct),
      stat('Solo rate', s.solo_rate === null ? '–' : `${s.solo_rate}%`, null, `${s.solved} solo · ${s.hinted} hints · ${s.redo} redo`),
      stat('Streak', String(s.streak), s.streak === 1 ? 'day' : 'days', `Best ${s.best_streak}`),
      stat('Revisions due', String(d.revisions.length), null, d.revisions.length ? 'Re-solve these alone' : 'All caught up')
    )
  );

  if (d.plan.state === 'active' && d.carried_over.count > 0) {
    page.append(
      h(
        'div',
        { class: 'callout' },
        h('p', null, h('b', null, plural(d.carried_over.count, 'problem')), ' carried over from earlier days. Replanning fits them into the days you have left.'),
        h(
          'button',
          {
            class: 'btn btn-sm',
            type: 'button',
            onclick: async (e) => {
              e.currentTarget.disabled = true;
              try {
                const r = await api.replan(d.plan.id);
                const dropped = r.replan.dropped.length;
                toast(`Rescheduled ${r.replan.rescheduled} problems${dropped ? `, dropped ${dropped} lowest-priority` : ''}.`);
                ctx.rerender();
              } catch (err) {
                toast(err.message, 'error');
                e.currentTarget.disabled = false;
              }
            },
          },
          icon('refresh'),
          'Replan now'
        )
      )
    );
  }

  const left = h('div', { class: 'stack' });
  const right = h('div', { class: 'stack' });
  if (d.today_day) {
    left.append(todayCard(d, ctx));
  } else if (d.plan.state === 'upcoming') {
    left.append(card({ title: 'Not started yet' }, h('div', { class: 'card-body muted' }, `Your plan starts on ${fmtLong(d.plan.start_date)}. Here is what the first days look like.`)));
  } else if (d.plan.state === 'finished') {
    left.append(
      emptyState({
        title: 'Plan complete',
        text: `You finished ${p.done} of ${p.total} planned problems. Keep your revision queue empty, or build a new plan for the next stretch.`,
        action: h('button', { class: 'btn btn-primary', type: 'button', onclick: () => ctx.openPlanForm() }, icon('plus'), 'New plan'),
      })
    );
  }
  const next = upNextCard(d);
  if (next) left.append(next);
  right.append(revisionCard(d, ctx));
  const topics = topicsCard(d);
  if (topics) right.append(topics);
  page.append(h('div', { class: 'grid-2' }, left, right));
  return page;
}
