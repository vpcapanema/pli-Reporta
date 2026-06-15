/** Painel principal — mapa Leaflet, fila e estatísticas. */
import {
  decideModeration,
  fetchManagementGeoJson,
  fetchModerationCatalog,
  fetchModerationQueue,
  fetchModerationStats,
} from './api.js';
import {
  $,
  bindLogout,
  categorySigla,
  formatDate,
  handleAuthError,
  renderSidebar,
  requireAuth,
  statusLabel,
} from './gestao-common.js';

let map;
let markersLayer;
let catalog = null;

const STATUS_COLORS = {
  submetido: '#94a3b8',
  em_moderacao: '#f59e0b',
  validado: '#3b82f6',
  publicado: '#22c55e',
  descartado: '#ef4444',
  expirado: '#64748b',
  resolvido: '#a855f7',
};

function markerHtml(p) {
  const sigla = categorySigla(p.category, catalog);
  const color = STATUS_COLORS[p.status] || '#64748b';
  const isEvent = p.interaction_type === 'evento_trafego';
  const shapeClass = isEvent ? 'gestao-marker-diamond' : 'gestao-marker-circle';
  return `<div class="gestao-marker ${shapeClass}" style="border-color:${color}">
    <span>${sigla}</span>
  </div>`;
}

function initMap() {
  map = L.map('gestao-map', { zoomControl: true }).setView([-23.55, -46.63], 11);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19,
  }).addTo(map);
  markersLayer = L.layerGroup().addTo(map);
}

function renderLegend() {
  const el = $('#gestao-legend');
  if (!el || !catalog) return;
  const statuses = Object.entries(catalog.statuses || {}).map(([id, m]) => `
    <div class="gestao-legend-row">
      <span class="gestao-legend-swatch" style="background:${m.cor}"></span>
      <span>${m.label}</span>
    </div>
  `).join('');
  el.innerHTML = `
    <h3>Legenda</h3>
    <p class="muted">◆ evento · ● manifestação · sigla = categoria · borda = status</p>
    ${statuses}
  `;
}

async function loadMap() {
  const session = requireAuth();
  if (!session) return;
  try {
    const fc = await fetchManagementGeoJson(session.token);
    markersLayer.clearLayers();
    const bounds = [];
    for (const f of fc.features || []) {
      const p = f.properties || {};
      const [lon, lat] = f.geometry?.coordinates || [];
      if (lat == null || lon == null) continue;
      bounds.push([lat, lon]);
      const icon = L.divIcon({
        className: 'gestao-divicon',
        html: markerHtml(p),
        iconSize: [36, 36],
        iconAnchor: [18, 18],
      });
      const m = L.marker([lat, lon], { icon });
      m.bindPopup(`
        <strong>${p.interaction_type === 'manifestacao' ? 'Manifestação' : 'Evento'}</strong>
        · ${p.category}<br/>
        ${statusLabel(p.status, catalog)}<br/>
        <small>${formatDate(p.received_at || p.captured_at)}</small>
      `);
      markersLayer.addLayer(m);
    }
    if (bounds.length) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
  } catch (err) {
    if (handleAuthError(err)) return;
    console.error(err);
  }
}

function renderQueue(data) {
  const list = $('#gestao-queue');
  const count = $('#gestao-fila-count');
  if (count) count.textContent = data.queue_size;
  if (!list) return;
  if (!data.items?.length) {
    list.innerHTML = '<p class="muted gestao-empty">Nenhum reporte aguardando sua análise.</p>';
    return;
  }
  list.innerHTML = data.items.map((it) => {
    const typeLabel = it.interaction_type === 'manifestacao' ? 'Manifestação' : 'Evento';
    const photo = it.photo_url ? `<img src="${it.photo_url}" alt="" class="gestao-queue-photo"/>` : '';
    return `
      <article class="gestao-queue-card" data-id="${it.id}">
        <header>
          <strong>${typeLabel} · ${it.category}</strong>
          <span class="gestao-badge">${statusLabel(it.status, catalog)}</span>
        </header>
        <p class="muted">${formatDate(it.received_at)}</p>
        ${it.description ? `<p>${it.description}</p>` : ''}
        ${photo}
        <div class="gestao-queue-actions">
          <button type="button" data-decision="publicar" data-id="${it.id}">Publicar</button>
          <button type="button" class="secondary" data-decision="descartar" data-id="${it.id}">Arquivar</button>
        </div>
      </article>
    `;
  }).join('');

  list.querySelectorAll('button[data-decision]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const session = requireAuth();
      if (!session) return;
      const id = btn.dataset.id;
      const dec = btn.dataset.decision;
      const note = dec === 'descartar' ? prompt('Motivo (opcional):', '') : null;
      try {
        await decideModeration(session.token, id, dec, note);
        await refreshAll();
      } catch (err) {
        alert('Não foi possível concluir: ' + err.message);
      }
    });
  });
}

async function loadStats() {
  const session = requireAuth();
  if (!session) return;
  try {
    const stats = await fetchModerationStats(session.token);
    $('#stat-fila').textContent = stats.fila;
    $('#stat-publicados').textContent = stats.publicados;
    $('#stat-arquivados').textContent = stats.arquivados;
    $('#stat-total').textContent = stats.total;
  } catch (err) {
    handleAuthError(err);
  }
}

async function loadQueue() {
  const session = requireAuth();
  if (!session) return;
  try {
    const data = await fetchModerationQueue(session.token);
    renderQueue(data);
  } catch (err) {
    if (handleAuthError(err)) return;
    $('#gestao-queue').innerHTML = `<p class="gestao-error">${err.message}</p>`;
  }
}

async function refreshAll() {
  await Promise.all([loadStats(), loadQueue(), loadMap()]);
}

document.addEventListener('DOMContentLoaded', async () => {
  const session = requireAuth();
  if (!session) return;
  renderSidebar('dashboard');
  bindLogout();
  initMap();
  try {
    catalog = await fetchModerationCatalog(session.token);
    renderLegend();
  } catch (err) {
    handleAuthError(err);
  }
  await refreshAll();
  $('#btn-gestao-refresh')?.addEventListener('click', refreshAll);
  setTimeout(() => map?.invalidateSize(), 100);
});
