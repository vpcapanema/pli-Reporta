// Cliente HTTP fino. Centraliza endpoints e formato dos payloads.
const BASE = ''; // mesma origem do frontend

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
}) {
  const fd = new FormData();
  fd.append('photo', photoBlob, 'capture.jpg');
  fd.append('lat', String(lat));
  fd.append('lon', String(lon));
  fd.append('category', category);
  fd.append('captured_at', capturedAt);
  if (accuracy != null) fd.append('accuracy_m', String(accuracy));
  if (magnitude) fd.append('magnitude', magnitude);
  if (description) fd.append('description', description);
  if (captureNonce) fd.append('capture_nonce', captureNonce);
  if (clientId) fd.append('client_id', clientId);
  if (geometry) fd.append('geometry', JSON.stringify(geometry));

  const res = await fetch(`${BASE}/api/v1/reports`, { method: 'POST', body: fd });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`POST /reports failed: ${res.status} ${text}`);
  }
  return res.json();
}

export async function fetchIncidents({ bbox, since, category, minPriority } = {}) {
  const u = new URL('/api/v1/incidents.geojson', location.origin);
  if (bbox) u.searchParams.set('bbox', bbox);
  if (since) u.searchParams.set('since', since);
  if (category) u.searchParams.set('category', category);
  if (minPriority != null) u.searchParams.set('min_priority', String(minPriority));
  const res = await fetch(u);
  if (!res.ok) throw new Error('fetchIncidents failed');
  return res.json();
}

export async function fetchModerationQueue(apiKey) {
  const res = await fetch('/api/v1/moderation/queue', {
    headers: { 'X-API-Key': apiKey },
  });
  if (!res.ok) throw new Error('fetchModerationQueue failed: ' + res.status);
  return res.json();
}

export async function decideModeration(apiKey, id, decision, note) {
  const res = await fetch(`/api/v1/moderation/${id}/decide`, {
    method: 'POST',
    headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, note: note || null }),
  });
  if (!res.ok) throw new Error('decideModeration failed');
  return res.json();
}
