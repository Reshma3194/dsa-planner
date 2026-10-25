import { api } from '../api.js';
import { bar, card, confirmDialog, diffClass, emptyState, fmtDate, fmtMin, h, icon, openMenu, pageHeader, plural, problemRow, stat, toast } from '../ui.js';

// Which days are expanded survives re-renders (e.g. after marking a problem).
const openState = { planId: null, days: new Set() };

const VERIFY_LABEL = { verified: 'Verified', cached: 'Cached check', offline: 'Bundled list', skipped: 'Not checked' };

function dayRow(day, plan, ctx) {
  const root = h('div', { class: `day ${day.state}` });
  let body = null;

  const build = () => {
    const onStatus = (it) => async (s) => {
      await api.updateProblem(it.slug, { status: s });
      ctx.rerender();
    };
    const list = h('div', { class: 'rows', role: 'list' });
    if (!day.items.length) list.append(h('div', { class: 'card-body muted' }, 'Buffer day. Nothing new is scheduled.'));
    day.items.forEach((it) => list.append(problemRow(it, { ctx, onStatus: onStatus(it), review: it.kind === 'review' })));
    return h('div', { class: 'day-body' }, list);
  };

  const head = h(
    'button',
    { class: 'day-head', type: 'button', 'aria-expanded': 'false' },
    icon('right').cloneNode(true),
    h('div', null, h('div', { class: 'day-num' }, `Day ${day.day}`), h('div', { class: 'day-date' }, fmtDate(day.date))),
    h(
      'div',
      { style: { minWidth: 0 } },
      h('div', { class: 'day-theme' }, day.kind === 'review' ? day.theme : day.theme),
      day.kind === 'review' ? h('span', { class: 'tag tag-accent' }, 'Review') : null,
      day.state === 'today' ? h('span', { class: 'tag tag-accent', style: { marginLeft: '6px' } }, 'Today') : null,
      day.carried ? h('span', { class: 'tag', style: { marginLeft: '6px', background: 'var(--hinted-bg)', color: 'var(--hinted-fg)' } }, `${day.carried} carried`) : null
    ),
    h('div', { class: 'day-count' }, day.count ? `${day.done}/${day.count} done` : 'Buffer'),
    h('div', { class: 'day-count day-min' }, fmtMin(day.planned_minutes))
  );
  head.firstChild.setAttribute('class', 'chev');

  const setOpen = (open) => {
    root.classList.toggle('open', open);
    head.setAttribute('aria-expanded', String(open));
    if (open) {
      if (!body) body = build();
      root.append(body);
      openState.days.add(day.day);
    } else {
      if (body) body.remove();
      openState.days.delete(day.day);
    }
  };
  head.addEventListener('click', () => setOpen(!root.classList.contains('open')));
  root.append(head);
  if (openState.days.has(day.day)) setOpen(true);
  return root;
}

function verificationStat(plan, ctx) {
  const v = plan.verification || {};
  const when = v.checked_at ? fmtDate(v.checked_at.slice(0, 10), { day: 'numeric', month: 'short' }) : null;
  const sub = when ? `${when}${v.paid_removed ? ` · ${v.paid_removed} premium removed` : ' · all free'}` : 'Only free problems are bundled';
  const el = stat('Free-tier check', VERIFY_LABEL[v.status] || 'Unknown', null, sub);
  const btn = h(
    'button',
    {
      class: 'btn btn-sm',
      type: 'button',
      style: { marginTop: '10px' },
      onclick: async (e) => {
        const b = e.currentTarget;
        b.disabled = true;
        b.replaceChildren(h('span', { class: 'spinner' }), 'Checking…');
        try {
          const r = await api.verify();
          const ver = r.verification;
          toast(
            ver.status === 'verified'
              ? `Verified against leetcode.com. ${r.removed.length ? `${r.removed.length} removed from the catalog.` : 'All problems are free.'}`
              : ver.note
          );
          ctx.rerender();
        } catch (err) {
          toast(err.message, 'error');
          b.disabled = false;
          b.replaceChildren(icon('refresh'), 'Re-check');
        }
      },
    },
    icon('refresh'),
    'Re-check'
  );
  el.append(btn);
  return el;
}

export async function planView(ctx) {
  const [{ plan }, { plans }] = await Promise.all([api.activePlan(), api.plans()]);
  const dash = await api.dashboard();
  ctx.updateSidebar(dash);
  const page = h('div', { class: 'page' });

  if (!plan) {
    page.append(
      pageHeader({ title: 'Plan', sub: 'No active plan yet', actions: [h('button', { class: 'btn btn-primary', type: 'button', onclick: () => ctx.openPlanForm() }, icon('plus'), 'Create plan')] }),
      emptyState({
        title: plans.length ? 'No plan is active' : 'No plan yet',
        text: plans.length ? 'Pick one of your saved plans below, or create a new one.' : 'Create a plan from the days and hours you have. It is saved as a file you can export.',
      })
    );
    if (plans.length) {
      page.append(
        card(
          { title: 'Saved plans' },
          ...plans.map((p) =>
            h(
              'div',
              { class: 'list-row' },
              h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, p.name), h('div', { class: 'prow-sub' }, `${p.days} days · ${p.hours_per_day} h/day · ${p.new_problems} problems`)),
              h('button', { class: 'btn btn-sm', type: 'button', onclick: async () => { await api.activate(p.id); ctx.rerender(); } }, 'Activate')
            )
          )
        )
      );
    }
    return page;
  }

  if (openState.planId !== plan.id) {
    openState.planId = plan.id;
    openState.days = new Set(plan.days.filter((d) => d.state === 'today').map((d) => d.day));
    if (!openState.days.size && plan.days.length) openState.days.add(plan.days[0].day);
  }

  const { params, summary } = plan;
  const actions = [];
  if (plans.length > 1) {
    actions.push(
      h(
        'select',
        {
          class: 'select',
          style: { width: 'auto', maxWidth: '220px' },
          'aria-label': 'Switch plan',
          value: plan.id,
          onchange: async (e) => {
            await api.activate(e.target.value);
            ctx.rerender();
          },
        },
        plans.map((p) => h('option', { value: p.id }, p.name))
      )
    );
  }
  if (plan.state !== 'finished') {
    actions.push(
      h(
        'button',
        {
          class: 'btn',
          type: 'button',
          title: 'Move everything not attempted into the days that are left',
          onclick: async (e) => {
            const b = e.currentTarget;
            b.disabled = true;
            try {
              const r = await api.replan(plan.id);
              const n = r.replan.dropped.length;
              toast(`Replanned. ${r.replan.rescheduled} problems rescheduled${n ? `, ${n} dropped (lowest priority)` : ''}.`);
              ctx.rerender();
            } catch (err) {
              toast(err.message, 'error');
              b.disabled = false;
            }
          },
        },
        icon('refresh'),
        'Replan from today'
      )
    );
  }
  actions.push(
    h(
      'button',
      {
        class: 'btn',
        type: 'button',
        'aria-haspopup': 'menu',
        onclick: (e) =>
          openMenu(
            e.currentTarget,
            [
              { value: 'md', title: 'Markdown checklist', desc: 'Readable file with links' },
              { value: 'json', title: 'JSON', desc: 'Full plan data' },
            ],
            (fmt) => {
              const a = h('a', { href: api.exportUrl(plan.id, fmt), download: '' });
              document.body.append(a);
              a.click();
              a.remove();
            }
          ),
      },
      icon('download'),
      'Export'
    ),
    h(
      'button',
      {
        class: 'icon-btn',
        type: 'button',
        'aria-label': 'Delete plan',
        title: 'Delete plan',
        onclick: async () => {
          const ok = await confirmDialog({ title: 'Delete this plan?', message: 'The plan file is removed. Your solved/redo progress on problems is kept.', confirmLabel: 'Delete plan', danger: true });
          if (!ok) return;
          try {
            await api.deletePlan(plan.id);
            toast('Plan deleted.');
            ctx.rerender();
          } catch (err) {
            toast(err.message, 'error');
          }
        },
      },
      icon('trash')
    ),
    h('button', { class: 'btn btn-primary', type: 'button', onclick: () => ctx.openPlanForm() }, icon('plus'), 'New plan')
  );

  page.append(
    pageHeader({
      title: plan.name,
      sub: `${plural(params.days, 'day')} · ${params.hours_per_day} h/day · ${params.level} · ${fmtDate(params.start_date)} to ${fmtDate(plan.end_date)}`,
      actions,
    }),
    h(
      'div',
      { class: 'strip' },
      stat('Problems', String(summary.new_problems), `+ ${summary.review_slots} re-solves`, `${plan.progress.done} done (${plan.progress.pct}%)`, plan.progress.pct),
      stat('Planned time', `${summary.planned_hours}`, 'hours', `${params.hours_per_day} h/day budget, 15% kept for revision`),
      stat('Core coverage', `${summary.core_pct}%`, null, `${summary.core_covered} of ${summary.core_total} core problems`, summary.core_pct),
      verificationStat(plan, ctx)
    )
  );

  if (summary.notes && summary.notes.length) {
    page.append(h('div', { class: 'notes' }, summary.notes.map((n) => h('p', null, n))));
  }
  if (plan.replans && plan.replans.length) {
    const last = plan.replans[plan.replans.length - 1];
    page.append(h('p', { class: 'hint', style: { margin: '-6px 0 16px' } }, `Replanned ${plural(plan.replans.length, 'time')}; last on ${fmtDate(last.on)}.`));
  }

  const days = h('div', null);
  plan.days.forEach((d) => days.append(dayRow(d, plan, ctx)));
  page.append(card({ title: 'Schedule', meta: `${plan.progress.done}/${plan.progress.total} problems done` }, days));

  const missing = summary.missing_core || [];
  const removed = summary.removed_by_verification || [];
  const dropped = (summary.dropped || []).filter((x) => x.reason.startsWith('Dropped on replan'));
  const sections = [];
  if (missing.length) {
    sections.push(
      h(
        'details',
        { class: 'card', style: { marginTop: '16px' } },
        h('summary', null, h('span', null, `Core problems not in this plan (${missing.length})`), h('span', { class: 'muted' }, 'More time or days would add these')),
        ...missing.map((m) =>
          h('div', { class: 'list-row' }, h('div', { class: 'grow' }, h('a', { href: `https://leetcode.com/problems/${m.slug}/`, target: '_blank', rel: 'noopener noreferrer', style: { fontWeight: 550 } }, m.title), h('div', { class: 'prow-sub' }, m.topic)), h('span', { class: diffClass(m.difficulty) }, m.difficulty))
        )
      )
    );
  }
  if (dropped.length) {
    sections.push(
      h(
        'details',
        { class: 'card', style: { marginTop: '16px' } },
        h('summary', null, h('span', null, `Dropped on replan (${dropped.length})`), h('span', { class: 'muted' }, 'Lowest priority first')),
        ...dropped.map((m) => h('div', { class: 'list-row' }, h('div', { class: 'grow' }, h('span', { style: { fontWeight: 550 } }, m.title), h('div', { class: 'prow-sub' }, m.topic)), h('span', { class: 'muted' }, 'Still available in Problems')))
      )
    );
  }
  if (removed.length) {
    sections.push(
      h(
        'details',
        { class: 'card', style: { marginTop: '16px' } },
        h('summary', null, h('span', null, `Removed by the free-tier check (${removed.length})`), h('span', { class: 'muted' }, 'Premium or missing on LeetCode')),
        ...removed.map((m) => h('div', { class: 'list-row' }, h('span', null, m.title), h('span', { class: 'muted' }, m.reason)))
      )
    );
  }
  page.append(...sections);

  page.afterMount = () => {
    const today = page.querySelector('.day.today');
    if (today) today.scrollIntoView({ block: 'center' });
  };
  return page;
}
