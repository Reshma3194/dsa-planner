import { api } from '../api.js';
import { STATUS, STATUS_ORDER, diffClass, fmtDate, h, icon, openDrawer, toast } from '../ui.js';

/** Side drawer with status, notes and attempt history for one problem. */
export async function openProblemDrawer(slug, ctx) {
  let problem;
  try {
    problem = (await api.problem(slug)).problem;
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  let changed = false;

  openDrawer(
    problem.title,
    () => {
      const statusBtns = STATUS_ORDER.map((s) =>
        h(
          'button',
          {
            class: 'status-opt',
            type: 'button',
            'data-s': s,
            'aria-pressed': String(problem.status === s),
            onclick: async () => {
              const prev = problem.status;
              problem.status = s;
              paint();
              try {
                await api.updateProblem(slug, { status: s });
                changed = true;
                problem.history = [{ status: s, at: new Date().toISOString() }, ...(problem.history || [])].slice(0, 10);
                renderHistory();
              } catch (e) {
                problem.status = prev;
                paint();
                toast(e.message, 'error');
              }
            },
          },
          h('span', { class: 't' }, STATUS[s].long),
          h('span', { class: 'd' }, STATUS[s].desc)
        )
      );
      const paint = () => statusBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.s === problem.status)));

      const saved = h('span', { class: 'hint' }, '');
      let timer;
      const save = async (value) => {
        saved.textContent = 'Saving…';
        try {
          await api.updateProblem(slug, { note: value });
          changed = true;
          saved.textContent = 'Saved';
        } catch (e) {
          saved.textContent = '';
          toast(e.message, 'error');
        }
      };
      const note = h('textarea', {
        class: 'input',
        id: 'note',
        maxlength: 4000,
        placeholder: 'Key idea, edge cases you missed, complexity, the pattern you will recognise next time…',
        value: problem.note || '',
        oninput: (e) => {
          saved.textContent = '';
          clearTimeout(timer);
          timer = setTimeout(() => save(e.target.value), 700);
        },
        onblur: (e) => {
          clearTimeout(timer);
          if (e.target.value !== (problem.note || '')) {
            problem.note = e.target.value;
            save(e.target.value);
          }
        },
      });

      const historyEl = h('div', { class: 'history' });
      const renderHistory = () => {
        historyEl.replaceChildren(
          ...((problem.history || []).length
            ? problem.history.map((e) => h('div', null, h('span', null, STATUS[e.status] ? STATUS[e.status].long : e.status), h('span', { class: 'muted' }, fmtDate(e.at.slice(0, 10)))))
            : [h('span', { class: 'muted' }, 'No attempts logged yet.')])
        );
      };
      renderHistory();

      const body = [
        h(
          'div',
          { style: { display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' } },
          h('span', { class: diffClass(problem.difficulty) }, problem.difficulty),
          h('span', { class: 'tag' }, problem.topic),
          h('span', { class: 'tag' }, problem.pattern)
        ),
        h('a', { class: 'btn btn-primary', href: problem.url, target: '_blank', rel: 'noopener noreferrer' }, 'Solve on LeetCode', icon('external')),
        h('div', { class: 'field' }, h('span', { class: 'label' }, 'How did it go?'), h('div', { class: 'status-seg' }, statusBtns), h('p', { class: 'hint' }, 'Be honest. Redo problems come back in your revision queue tomorrow; problems you needed hints for come back in 3 days.')),
        h('div', { class: 'field' }, h('label', { class: 'label', for: 'note' }, 'Notes'), note, saved),
        h('div', { class: 'field' }, h('span', { class: 'label' }, 'Recent attempts'), historyEl),
      ];
      return { body };
    },
    { onClose: () => changed && ctx.rerender() }
  );
}
