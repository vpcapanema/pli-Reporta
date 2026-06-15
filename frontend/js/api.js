// Cliente HTTP fino. Centraliza endpoints e formato dos payloads.
const BASE = '';
const SESSION_STORAGE = 'pli-reporta-session';

export function getSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_STORAGE) || 'null');
  } catch {
    return null;
  }
}

export function clearSession() {
  localStorage.removeItem(SESSION_STORAGE);
}

export async function fetchAuthContext() {
  const res = await fetch('/api/v1/auth/context');
  if (!res.ok) throw new Error('auth context failed: ' + res.status);
  return res.json();
}

export async function loginModerator(username, password) {
  const res = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body.detail || '';
    } catch (_) {}
    const err = new Error(detail || `login failed: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  const data = await res.json();
  localStorage.setItem(SESSION_STORAGE, JSON.stringify({
    token: data.token,
    username: data.username,
    expiresAt: Date.now() + data.expires_in * 1000,
  }));
  return data;
}

function authHeaders(token) {
  return { Authorization: `Bearer ${token}` };
}
export async function getCaptureNonce(clientId) {
  const u = new URL('/api/v1/capture-nonce', location.origin);
  if (clientId) u.searchParams.set('client_id', clientId);
  const res = await fetch(u);
  if (!res.ok) throw new Error('nonce request failed');
  return res.json();
}

export async function postReport({
  photoBlob, lat, lon, accuracy, category, magnitude, description,
  capturedAt, captureNonce, clientId, geometry,
  interactionType, offlineCapture, queuedAt,
}) {
  const fd = new FormData();
  fd.append('photo', photoBlob, 'capture.jpg');
  fd.append('lat', String(lat));
  fd.append('lon', String(lon));
  fd.append('category', category);
  fd.append('captured_at', capturedAt);
  fd.append('interaction_type', interactionType || 'evento_trafego');
  if (accuracy != null) fd.append('accuracy_m', String(accuracy));
  if (magnitude) fd.append('magnitude', magnitude);
  if (description) fd.append('description', description);
  if (captureNonce) fd.append('capture_nonce', captureNonce);
  if (clientId) fd.append('client_id', clientId);
  if (geometry) fd.append('geometry', JSON.stringify(geometry));
  if (offlineCapture) fd.append('offline_capture', 'true');
  if (queuedAt) fd.append('queued_at', queuedAt);

  const res = await fetch(`${BASE}/api/v1/reports`, { method: 'POST', body: fd });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`POST /reports failed: ${res.status} ${text}`);
  }
  return res.json();
}

export async function fetchIncidents(opts = {}) {
  return fetchGeoJson('/api/v1/incidents.geojson', opts);
}

export async function fetchManifestations(opts = {}) {
  return fetchGeoJson('/api/v1/manifestations.geojson', opts);
}

export async function resolveIncident(clusterId) {
  const res = await fetch(`/api/v1/incidents/${clusterId}/resolver`, { method: 'POST' });
  if (!res.ok) throw new Error('resolveIncident failed: ' + res.status);
  return res.json();
}

async function fetchGeoJson(path, { bbox, since, category, minPriority } = {}) {
  const u = new URL(path, location.origin);
  if (bbox) u.searchParams.set('bbox', bbox);
  if (since) u.searchParams.set('since', since);
  if (category) u.searchParams.set('category', category);
  if (minPriority != null) u.searchParams.set('min_priority', String(minPriority));
  const res = await fetch(u);
  if (!res.ok) throw new Error(`fetch ${path} failed`);
  return res.json();
}

export async function fetchModerationQueue(token) {
  const res = await fetch('/api/v1/moderation/queue', {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error('fetchModerationQueue failed: ' + res.status);
  return res.json();
}

export async function decideModeration(token, id, decision, note) {
  const res = await fetch(`/api/v1/moderation/${id}/decide`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, note: note || null }),
  });
  if (!res.ok) throw new Error('decideModeration failed');
  return res.json();
}

async function moderationFetch(path, token, opts = {}) {
  const res = await fetch(`/api/v1/moderation${path}`, {
    ...opts,
    headers: { ...authHeaders(token), ...(opts.headers || {}) },
  });
  if (res.status === 401) {
    const err = new Error('401');
    err.status = 401;
    throw err;
  }
  if (!res.ok) throw new Error(`moderation ${path} failed: ${res.status}`);
  return res.json();
}

export function fetchModerationStats(token) {
  return moderationFetch('/stats', token);
}

export function fetchModerationCatalog(token) {
  return moderationFetch('/catalog', token);
}

export function fetchModerationPolicy(token) {
  return moderationFetch('/policy', token);
}

export function updateModerationPolicy(token, payload) {
  return moderationFetch('/policy', token, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function simulateModerationPolicy(token, days = 7) {
  return moderationFetch(`/policy/simulate?days=${days}`, token, { method: 'POST' });
}

export function fetchManagementReports(token, params = {}) {
  const u = new URL('/api/v1/moderation/reports', location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== '') u.searchParams.set(k, String(v));
  });
  return fetch(u, { headers: authHeaders(token) }).then((res) => {
    if (res.status === 401) throw Object.assign(new Error('401'), { status: 401 });
    if (!res.ok) throw new Error('fetchManagementReports failed');
    return res.json();
  });
}

export function fetchManagementGeoJson(token, params = {}) {
  const u = new URL('/api/v1/moderation/reports.geojson', location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== '') u.searchParams.set(k, String(v));
  });
  return fetch(u, { headers: authHeaders(token) }).then((res) => {
    if (res.status === 401) throw Object.assign(new Error('401'), { status: 401 });
    if (!res.ok) throw new Error('fetchManagementGeoJson failed');
    return res.json();
  });
}