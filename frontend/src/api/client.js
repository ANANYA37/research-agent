import { API_BASE } from './config.js';

const TOKEN_KEY = 'researchAgentAccessToken';

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 401) window.dispatchEvent(new Event('auth:expired'));
  return response;
}

export async function apiJson(path, options = {}) {
  const response = await apiFetch(path, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload?.detail;
    const message = typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map((issue) => issue.msg).filter(Boolean).join('; ') : '';
    throw new Error(message || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

const watchPath = (id) => `/api/watchlists/${encodeURIComponent(id)}`;

export const api = {
  watchlists: () => apiJson('/api/watchlists'),
  watchlist: (id) => apiJson(watchPath(id)),
  createWatchlist: (payload) => apiJson('/api/watchlists', { method: 'POST', body: JSON.stringify(payload) }),
  updateWatchlist: (id, payload) => apiJson(watchPath(id), { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteWatchlist: (id) => apiJson(watchPath(id), { method: 'DELETE' }),
  checkWatchlist: (id) => apiJson(`${watchPath(id)}/check`, { method: 'POST' }),
  watchlistRun: (id, runId) => apiJson(`${watchPath(id)}/runs/${encodeURIComponent(runId)}`),
  me: () => apiJson('/api/auth/me'),
  login: (payload) => apiJson('/api/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  register: (payload) => apiJson('/api/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  history: () => apiJson('/api/history'),
  report: (id) => apiJson(`/api/history/${id}`),
  collections: () => apiJson('/api/collections'),
  createCollection: (payload) => apiJson('/api/collections', { method: 'POST', body: JSON.stringify(payload) }),
  tags: () => apiJson('/api/tags'),
  createTag: (payload) => apiJson('/api/tags', { method: 'POST', body: JSON.stringify(payload) }),
  updateReportMetadata: (id, payload) => apiJson(`/api/history/${id}/metadata`, { method: 'PUT', body: JSON.stringify(payload) }),
};
