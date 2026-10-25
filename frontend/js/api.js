// Thin fetch wrapper around the FastAPI backend.

function formatDetail(detail) {
  if (!detail) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== 'body').join('.') : '';
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join('; ');
  }
  return String(detail);
}

async function request(method, path, body) {
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error('Cannot reach the DSA Planner server. Is it still running?');
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      message = formatDetail((await res.json()).detail) || message;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  return res.json();
}

const qs = (params) => {
  const sp = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) sp.set(k, v);
  });
  const s = sp.toString();
  return s ? `?${s}` : '';
};

export const api = {
  meta: () => request('GET', '/api/meta'),
  dashboard: () => request('GET', '/api/dashboard'),
  problems: (filters) => request('GET', `/api/problems${qs(filters)}`),
  problem: (slug) => request('GET', `/api/problems/${encodeURIComponent(slug)}`),
  updateProblem: (slug, body) => request('PUT', `/api/problems/${encodeURIComponent(slug)}`, body),
  previewPlan: (body) => request('POST', '/api/plans/preview', body),
  createPlan: (body) => request('POST', '/api/plans', body),
  plans: () => request('GET', '/api/plans'),
  activePlan: () => request('GET', '/api/plans/active'),
  activate: (id) => request('POST', `/api/plans/${id}/activate`),
  replan: (id) => request('POST', `/api/plans/${id}/replan`),
  deletePlan: (id) => request('DELETE', `/api/plans/${id}`),
  verify: () => request('POST', '/api/catalog/verify'),
  exportUrl: (id, format) => `/api/plans/${id}/export?format=${format}`,
};
