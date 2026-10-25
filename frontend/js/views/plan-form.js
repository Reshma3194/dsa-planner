import { api } from '../api.js';
import { bar, h, icon, openModal, plural, sparkBars, toast } from '../ui.js';

const LEVELS = [
  ['beginner', 'Beginner', 'Slower estimates, no Hard problems'],
  ['intermediate', 'Intermediate', 'Balanced estimates'],
  ['advanced', 'Advanced', 'Faster estimates, Easy problems deprioritised'],
];

function localISO(d = new Date()) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Modal to create a plan. Shows a live preview (no files written until you generate). */
export function openPlanForm(ctx) {
  const form = { days: 30, hours: 2, level: 'intermediate', weak: new Set(), start: localISO(), name: '', verify: true };
  let preview;
  let generate;
  let timer;
  let seq = 0;

  const payload = () => ({
    days: form.days,
    hours_per_day: form.hours,
    level: form.level,
    weak_topics: [...form.weak],
    start_date: form.start || null,
    name: form.name.trim() || null,
    verify: form.verify,
  });
  const valid = () => Number.isInteger(form.days) && form.days >= 1 && form.days <= 365 && form.hours >= 0.5 && form.hours <= 16;

  const renderPreview = (data, error) => {
    if (error) return preview.replaceChildren(h('p', null, error));
    const s = data.summary;
    preview.replaceChildren(
      h('div', { class: 'cols' }, h('div', null, h('div', { class: 'big' }, String(s.new_problems)), h('div', { class: 'hint' }, 'new problems')), h('div', null, h('div', { class: 'big' }, `${s.planned_hours}h`), h('div', { class: 'hint' }, 'total practice time'))),
      h('div', null, h('div', { style: { display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '13px' } }, h('span', null, 'Core coverage'), h('b', null, `${s.core_pct}%`)), bar(s.core_pct)),
      sparkBars(data.days),
      h('p', null, s.notes[0] || '')
    );
  };

  const refresh = () => {
    clearTimeout(timer);
    generate.disabled = !valid();
    if (!valid()) return renderPreview(null, 'Enter between 1 and 365 days and 0.5 to 16 hours per day.');
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const data = await api.previewPlan(payload());
        if (mine === seq) renderPreview(data);
      } catch (e) {
        if (mine === seq) renderPreview(null, e.message);
      }
    }, 250);
  };

  const presets = (values, current, set, suffix = '') =>
    h(
      'div',
      { class: 'chips' },
      values.map((v) => {
        const btn = h('button', { class: 'chip', type: 'button', 'aria-pressed': String(current() === v), onclick: () => set(v) }, `${v}${suffix}`);
        btn.dataset.v = v;
        return btn;
      })
    );

  openModal(
    'Create a plan',
    ({ close }) => {
      const daysInput = h('input', { class: 'input', id: 'f-days', type: 'number', min: 1, max: 365, step: 1, value: form.days });
      const hoursInput = h('input', { class: 'input', id: 'f-hours', type: 'number', min: 0.5, max: 16, step: 0.5, value: form.hours });
      const daysChips = presets([7, 14, 30, 60, 90], () => form.days, (v) => setDays(v), 'd');
      const hoursChips = presets([1, 2, 3, 4], () => form.hours, (v) => setHours(v), 'h');
      const syncChips = (wrap, value) => wrap.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', String(Number(c.dataset.v) === value)));
      const setDays = (v) => { form.days = v; daysInput.value = v; syncChips(daysChips, v); refresh(); };
      const setHours = (v) => { form.hours = v; hoursInput.value = v; syncChips(hoursChips, v); refresh(); };
      daysInput.addEventListener('input', () => { form.days = Number(daysInput.value); syncChips(daysChips, form.days); refresh(); });
      hoursInput.addEventListener('input', () => { form.hours = Number(hoursInput.value); syncChips(hoursChips, form.hours); refresh(); });

      const levelSeg = h(
        'div',
        { class: 'seg', role: 'group', 'aria-label': 'Level' },
        LEVELS.map(([v, label, tip]) =>
          h('button', { type: 'button', title: tip, 'aria-pressed': String(form.level === v), 'data-v': v, onclick: () => { form.level = v; levelSeg.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === v))); refresh(); } }, label)
        )
      );
      const weak = h(
        'div',
        { class: 'chips' },
        ctx.meta.topics.map((t) =>
          h('button', { class: 'chip', type: 'button', 'aria-pressed': 'false', onclick: (e) => { const on = !form.weak.has(t.topic); on ? form.weak.add(t.topic) : form.weak.delete(t.topic); e.currentTarget.setAttribute('aria-pressed', String(on)); refresh(); } }, t.topic)
        )
      );

      preview = h('div', { class: 'preview', 'aria-live': 'polite' }, h('span', { class: 'spinner' }));
      generate = h('button', { class: 'btn btn-primary', type: 'button' }, 'Generate plan');
      generate.addEventListener('click', async () => {
        if (!valid()) return;
        generate.disabled = true;
        generate.replaceChildren(h('span', { class: 'spinner', style: { borderTopColor: 'var(--on-ink)' } }), form.verify ? 'Checking LeetCode…' : 'Generating…');
        try {
          const plan = await api.createPlan(payload());
          close();
          const v = plan.verification;
          toast(`Plan ready: ${plural(plan.summary.new_problems, 'problem')} over ${plural(plan.params.days, 'day')}.`);
          if (form.verify && v.status === 'offline') toast('Could not reach leetcode.com, so the bundled free-problem list was used.', 'info', 7000);
          ctx.navigate('plan', true);
        } catch (e) {
          toast(e.message, 'error');
          generate.disabled = false;
          generate.textContent = 'Generate plan';
        }
      });

      const body = h(
        'div',
        { class: 'form-grid' },
        h(
          'div',
          { class: 'form-col' },
          h('div', { class: 'field' }, h('label', { class: 'label', for: 'f-days' }, 'Days until your interview'), daysInput, daysChips),
          h('div', { class: 'field' }, h('label', { class: 'label', for: 'f-hours' }, 'Hours you can practise per day'), hoursInput, hoursChips),
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'Level'), levelSeg),
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'Weak topics (optional)'), weak, h('p', { class: 'hint' }, 'These get extra problems earlier in the plan.')),
          h(
            'div',
            { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' } },
            h('div', { class: 'field' }, h('label', { class: 'label', for: 'f-start' }, 'Start date'), h('input', { class: 'input', id: 'f-start', type: 'date', value: form.start, onchange: (e) => { form.start = e.target.value; refresh(); } })),
            h('div', { class: 'field' }, h('label', { class: 'label', for: 'f-name' }, 'Name (optional)'), h('input', { class: 'input', id: 'f-name', type: 'text', maxlength: 80, placeholder: 'e.g. Google onsite', oninput: (e) => { form.name = e.target.value; } }))
          ),
          h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: true, onchange: (e) => { form.verify = e.target.checked; } }), h('span', null, h('span', { class: 'label' }, 'Check problems are free on LeetCode'), h('span', { class: 'hint', style: { display: 'block' } }, 'Asks leetcode.com for the free/premium flag of every problem before planning. Falls back to the bundled list if offline.')))
        ),
        h('div', { class: 'form-col' }, h('span', { class: 'label' }, 'Preview'), preview)
      );
      refresh();
      return {
        body,
        footer: [h('button', { class: 'btn', type: 'button', onclick: close }, 'Cancel'), generate],
      };
    },
    { size: '' }
  );
}
