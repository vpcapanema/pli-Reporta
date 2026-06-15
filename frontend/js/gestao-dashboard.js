/** Painel principal — mapa Leaflet, camadas, legenda e progresso na sidebar. */
import {
  fetchManagementGeoJson,
  fetchModerationCatalog,
  fetchModerationStats,
} from './api.js';
import {
  $,
  bindLogout,
  handleAuthError,
  renderSidebar,
  requireAuth,
} from './gestao-common.js';
import { bindPopupCloseControl, buildGestaoPopupHtml } from './gestao-map-popup.js';
import {
  createMarkerElement,
  legendStatusSwatch,
  preloadEventIcons,
  resolveStatusColor,
  buildLegendSymbolsBlock,
} from './gestao-markers.js';

let map;
/** @type {Record<string, L.LayerGroup>} */
const typeLayers = {};
/** @type {Record<string, L.LayerGroup>} */
const categoryLayers = {};
let catalog = null;
/** @type {Record<string, boolean>} */
const layerVisibility = {};
/** @type {Record<string, number>} */
const layerProgressPct = {};
/** @type {string[]} */
let allLayerKeys = [];

function initMap() {
  map = L.map('gestao-map', { zoomControl: false }).setView([-23.55, -46.63], 8);
  L.control.zoom({ position: 'topright' }).addTo(map);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19,
  }).addTo(map);
  mountMapOverlays();
  ensurePopupOnTop();
}

function ensurePopupOnTop() {
  if (!map) return;
  const popupPane = map.getPane('popupPane');
  if (popupPane) popupPane.style.zIndex = '2000';
  const markerPane = map.getPane('markerPane');
  if (markerPane) markerPane.style.zIndex = '650';
  map.getContainer().querySelectorAll('.leaflet-control').forEach((el) => {
    el.style.zIndex = '600';
  });
}

/** Painéis flutuantes dentro do container Leaflet para popups ficarem acima deles. */
function mountMapOverlays() {
  const container = map?.getContainer();
  if (!container) return;
  for (const id of ['gestao-layers', 'gestao-legend']) {
    const el = document.getElementById(id);
    if (el && el.parentElement !== container) container.appendChild(el);
  }
}

function initDraggablePanel(panel, handle) {
  if (!panel || !handle) return;
  handle.addEventListener('mousedown', (e) => {
    if (e.button !== 0 || e.target.closest('input, label, button, select, .gestao-layers-toggle')) return;
    e.preventDefault();
    const mapPanel = panel.offsetParent;
    if (!mapPanel) return;
    const panelRect = panel.getBoundingClientRect();
    const parentRect = mapPanel.getBoundingClientRect();
    const startX = e.clientX;
    const startY = e.clientY;
    const initialLeft = panelRect.left - parentRect.left;
    const initialTop = panelRect.top - parentRect.top;
    panel.style.left = `${initialLeft}px`;
    panel.style.top = `${initialTop}px`;
    panel.style.right = 'auto';
    panel.classList.add('is-dragging');

    const onMove = (ev) => {
      const left = Math.max(0, Math.min(
        parentRect.width - panel.offsetWidth,
        initialLeft + ev.clientX - startX,
      ));
      const top = Math.max(0, Math.min(
        parentRect.height - panel.offsetHeight,
        initialTop + ev.clientY - startY,
      ));
      panel.style.left = `${left}px`;
      panel.style.top = `${top}px`;
    };
    const onUp = () => {
      panel.classList.remove('is-dragging');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
}

function initLayersCollapse() {
  const panel = $('#gestao-layers');
  const btn = $('#gestao-layers-toggle');
  if (!panel || !btn) return;
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const collapsed = panel.classList.toggle('gestao-layers--collapsed');
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    btn.textContent = collapsed ? '+' : '−';
    btn.title = collapsed ? 'Expandir camadas' : 'Recolher camadas';
  });
}

function layerKeyForFeature(p) {
  const catPrefix = p.interaction_type === 'manifestacao' ? 'manifestacao' : 'evento';
  return `${catPrefix}:${p.category || 'outro'}`;
}

function layerLabelForKey(key) {
  const [prefix, catId] = key.split(':');
  const categories = prefix === 'manifestacao'
    ? catalog?.manifestation_categories
    : catalog?.event_categories;
  return categories?.find((c) => c.id === catId)?.label || catId || key;
}

function orderedActiveKeys(grouped) {
  const withData = Object.keys(grouped).filter((k) => grouped[k].length > 0);
  if (!withData.length) return [];

  const catalogOrder = [
    ...(catalog?.event_categories || []).map((c) => `evento:${c.id}`),
    ...(catalog?.manifestation_categories || []).map((c) => `manifestacao:${c.id}`),
  ];
  const ordered = catalogOrder.filter((k) => withData.includes(k));
  const extra = withData.filter((k) => !catalogOrder.includes(k));
  return [...ordered, ...extra];
}

function setLayerProgress(key, rawPct, hint = '') {
  const pct = Math.min(100, Math.max(0, Math.round(rawPct)));
  layerProgressPct[key] = pct;
  const row = document.querySelector(`[data-load-key="${key}"]`);
  const bar = row?.querySelector('[data-load-bar]');
  const label = row?.querySelector('[data-load-pct]');
  const track = row?.querySelector('[role="progressbar"]');
  const hintEl = row?.querySelector('[data-load-hint]');
  if (bar) bar.style.width = `${pct}%`;
  if (label) label.textContent = `${pct}%`;
  if (track) track.setAttribute('aria-valuenow', String(pct));
  if (hintEl && hint) hintEl.textContent = hint;
  if (row) {
    row.classList.toggle('gestao-load-row--done', pct >= 100);
    row.classList.toggle('gestao-load-row--error', pct < 0);
  }
  updateOverallProgress();
  finishLayerLoadPanelIfDone(layerLoadGeneration);
}

function setLayerError(key, message) {
  layerProgressPct[key] = -1;
  const row = document.querySelector(`[data-load-key="${key}"]`);
  if (!row) return;
  row.classList.add('gestao-load-row--error');
  const label = row.querySelector('[data-load-pct]');
  const hintEl = row.querySelector('[data-load-hint]');
  if (label) label.textContent = '—';
  if (hintEl) hintEl.textContent = message;
  finishLayerLoadPanelIfDone(layerLoadGeneration);
}

function updateOverallProgress() {
  const el = $('#gestao-load-overall');
  const hint = $('#gestao-load-overall-hint');
  if (!el || !allLayerKeys.length) return;
  const valid = allLayerKeys.filter((k) => layerProgressPct[k] >= 0);
  if (!valid.length) {
    el.textContent = '—';
    return;
  }
  const sum = valid.reduce((acc, k) => acc + layerProgressPct[k], 0);
  const avg = Math.round(sum / valid.length);
  el.textContent = `${avg}%`;
  if (hint) {
    const placed = Number(hint.dataset.placed || 0);
    const total = Number(hint.dataset.total || 0);
    hint.textContent = total ? `${placed} de ${total} no mapa` : '';
  }
}

/** Evita que um refresh antigo oculte o painel durante um carregamento mais novo. */
let layerLoadGeneration = 0;

function allLayersFinishedLoading() {
  return allLayerKeys.length > 0
    && allLayerKeys.every((k) => layerProgressPct[k] >= 100 || layerProgressPct[k] < 0);
}

function setLayerLoadPanelVisible(visible) {
  const panel = $('#gestao-layer-load');
  if (!panel) return;
  panel.hidden = !visible;
  panel.style.display = visible ? '' : 'none';
}

function finishLayerLoadPanelIfDone(generation) {
  if (generation !== layerLoadGeneration || !allLayersFinishedLoading()) return;
  setLayerLoadPanelVisible(false);
}

function resetAllProgress(message = 'Aguardando…') {
  for (const k of allLayerKeys) {
    layerProgressPct[k] = 0;
    setLayerProgress(k, 0, message);
  }
  const hint = $('#gestao-load-overall-hint');
  if (hint) {
    hint.textContent = '';
    hint.dataset.placed = '0';
    hint.dataset.total = '0';
  }
  $('#gestao-load-overall').textContent = '0%';
}

function renderLayerLoadPanel(activeKeys) {
  const body = $('#gestao-layer-load-body');
  if (!body || !catalog) return;

  allLayerKeys = [...activeKeys];
  for (const k of allLayerKeys) layerProgressPct[k] = 0;

  const renderGroup = (title, keys) => {
    if (!keys.length) return '';
    const rows = keys.map((key) => `
        <div class="gestao-load-row" data-load-key="${key}">
          <div class="gestao-load-row-head">
            <span>${layerLabelForKey(key)}</span>
            <span class="gestao-load-pct" data-load-pct="${key}">0%</span>
          </div>
          <div class="gestao-load-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
            <div class="gestao-load-bar" data-load-bar="${key}" style="width:0%"></div>
          </div>
          <span class="gestao-load-hint muted" data-load-hint="${key}">—</span>
        </div>`).join('');
    return `
      <div class="gestao-load-group">
        <h4>${title}</h4>
        ${rows}
      </div>`;
  };

  const eventKeys = activeKeys.filter((k) => k.startsWith('evento:'));
  const manifestKeys = activeKeys.filter((k) => k.startsWith('manifestacao:'));

  body.innerHTML =
    renderGroup('Eventos de tráfego', eventKeys)
    + renderGroup('Manifestação cidadã', manifestKeys);
}

function ensureLayerGroups() {
  if (!catalog) return;
  if (!typeLayers.evento_trafego) {
    typeLayers.evento_trafego = L.layerGroup().addTo(map);
  }
  if (!typeLayers.manifestacao) {
    typeLayers.manifestacao = L.layerGroup().addTo(map);
  }

  for (const c of catalog.event_categories || []) {
    const key = `evento:${c.id}`;
    if (!categoryLayers[key]) {
      categoryLayers[key] = L.layerGroup().addTo(typeLayers.evento_trafego);
    }
    layerVisibility[key] = layerVisibility[key] !== false;
  }
  for (const c of catalog.manifestation_categories || []) {
    const key = `manifestacao:${c.id}`;
    if (!categoryLayers[key]) {
      categoryLayers[key] = L.layerGroup().addTo(typeLayers.manifestacao);
    }
    layerVisibility[key] = layerVisibility[key] !== false;
  }
  layerVisibility.evento_trafego = true;
  layerVisibility.manifestacao = true;
}

function renderLayerControl() {
  const el = $('#gestao-layers-body');
  if (!el || !catalog) return;

  const catGroup = (typeId, categories, typeLabel) => {
    const cats = (categories || []).map((c) => {
      const key = `${typeId === 'evento_trafego' ? 'evento' : 'manifestacao'}:${c.id}`;
      return `
        <label class="gestao-layer-item gestao-layer-cat">
          <input type="checkbox" data-layer="${key}" checked/>
          <span>${c.label}</span>
        </label>`;
    }).join('');
    return `
      <fieldset class="gestao-layer-group">
        <label class="gestao-layer-item gestao-layer-type">
          <input type="checkbox" data-layer="${typeId}" checked/>
          <strong>${typeLabel}</strong>
        </label>
        <div class="gestao-layer-children">${cats}</div>
      </fieldset>`;
  };

  el.innerHTML = `
    ${catGroup('evento_trafego', catalog.event_categories, 'Eventos de tráfego')}
    ${catGroup('manifestacao', catalog.manifestation_categories, 'Manifestação cidadã')}
  `;

  el.querySelectorAll('input[data-layer]').forEach((input) => {
    input.addEventListener('change', () => {
      const key = input.dataset.layer;
      layerVisibility[key] = input.checked;
      applyLayerVisibility(key);
      if (key === 'evento_trafego' || key === 'manifestacao') {
        el.querySelectorAll(`input[data-layer^="${key === 'evento_trafego' ? 'evento' : 'manifestacao'}:"]`)
          .forEach((child) => {
            child.checked = input.checked;
            layerVisibility[child.dataset.layer] = input.checked;
            applyLayerVisibility(child.dataset.layer);
          });
      }
    });
  });
}

function applyLayerVisibility(key) {
  const visible = layerVisibility[key] !== false;
  if (key === 'evento_trafego' || key === 'manifestacao') {
    const group = typeLayers[key];
    if (!group) return;
    if (visible) group.addTo(map);
    else map.removeLayer(group);
    return;
  }
  const group = categoryLayers[key];
  if (!group) return;
  const parent = typeLayers[key.startsWith('evento:') ? 'evento_trafego' : 'manifestacao'];
  if (!parent) return;
  if (visible) {
    if (!parent.hasLayer(group)) group.addTo(parent);
  } else {
    parent.removeLayer(group);
  }
}

function renderLegend() {
  const el = $('#gestao-legend');
  if (!el || !catalog) return;
  const statuses = Object.entries(catalog.statuses || {}).map(([id, m]) => {
    const color = resolveStatusColor({ status: id }, catalog);
    return `
    <div class="gestao-legend-row">
      ${legendStatusSwatch(color)}
      <div class="gestao-legend-copy">
        <strong>${m.label}</strong>
      </div>
    </div>`;
  }).join('');
  el.innerHTML = `
    <h3>Legenda</h3>
    ${buildLegendSymbolsBlock()}
    <div class="gestao-legend-list">${statuses}</div>
  `;
}

/** Só remove marcadores — NÃO limpar typeLayers (isso desanexa subgrupos do mapa). */
function clearMarkers() {
  for (const g of Object.values(categoryLayers)) {
    g?.clearLayers();
  }
}

function ensureCategoryLayerOnMap(catKey) {
  const typeKey = catKey.startsWith('manifestacao:') ? 'manifestacao' : 'evento_trafego';
  const parent = typeLayers[typeKey];
  if (!parent) return null;
  if (!categoryLayers[catKey]) {
    categoryLayers[catKey] = L.layerGroup();
    layerVisibility[catKey] = true;
  }
  if (!parent.hasLayer(categoryLayers[catKey])) {
    categoryLayers[catKey].addTo(parent);
  }
  return categoryLayers[catKey];
}

function addMarkerForFeature(p, lat, lon) {
  const catKey = layerKeyForFeature(p);
  const target = ensureCategoryLayerOnMap(catKey);
  if (!target) return false;

  const markerEl = createMarkerElement(p, catalog);
  const icon = L.divIcon({
    className: 'gestao-divicon leaflet-div-icon',
    html: markerEl,
    iconSize: [48, 48],
    iconAnchor: [24, 24],
  });
  const m = L.marker([lat, lon], { icon, interactive: true });
  m.bindPopup(buildGestaoPopupHtml(p, catalog), {
    className: 'gestao-map-popup map-feature-popup',
    maxWidth: 9600,
    autoPan: true,
    autoPanPadding: [56, 56],
    closeButton: false,
  });
  m.on('popupopen', () => {
    const el = m.getPopup()?.getElement();
    if (el) el.style.zIndex = '2001';
    bindPopupCloseControl(el, () => m.closePopup());
  });
  target.addLayer(m);
  return true;
}

function groupFeatures(fc) {
  const grouped = {};
  for (const f of fc.features || []) {
    const p = f.properties || {};
    const [lon, lat] = f.geometry?.coordinates || [];
    if (lat == null || lon == null) continue;
    const key = layerKeyForFeature(p);
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push({ p, lat, lon });
  }
  return grouped;
}

async function loadMap() {
  const session = requireAuth();
  if (!session) return;

  const generation = ++layerLoadGeneration;
  allLayerKeys = [];
  setLayerLoadPanelVisible(false);

  try {
    const fc = await fetchManagementGeoJson(session.token);
    const grouped = groupFeatures(fc);
    const activeKeys = orderedActiveKeys(grouped);
    const totalFeatures = (fc.features || []).length;

    ensureLayerGroups();
    clearMarkers();
    await preloadEventIcons(catalog);

    const hint = $('#gestao-load-overall-hint');
    if (hint) {
      hint.dataset.total = String(totalFeatures);
      hint.dataset.placed = '0';
    }

    if (!activeKeys.length) {
      if (hint) hint.textContent = 'Nenhum registro retornado pela API';
      $('#gestao-load-overall').textContent = '—';
      return;
    }

    setLayerLoadPanelVisible(true);
    renderLayerLoadPanel(activeKeys);
    resetAllProgress('Plotando…');

    let placedTotal = 0;
    const bounds = [];

    for (const key of activeKeys) {
      const items = grouped[key];

      for (let i = 0; i < items.length; i += 1) {
        const { p, lat, lon } = items[i];
        const ok = addMarkerForFeature(p, lat, lon);
        if (!ok) {
          setLayerError(key, 'Falha ao plotar');
          break;
        }
        bounds.push([lat, lon]);
        placedTotal += 1;
        if (hint) hint.dataset.placed = String(placedTotal);

        const pct = Math.round(((i + 1) / items.length) * 100);
        setLayerProgress(key, pct, `${i + 1}/${items.length} no mapa`);

        if (items.length > 5 && i % 3 === 0) {
          await new Promise((r) => requestAnimationFrame(r));
        }
      }
    }

    updateOverallProgress();

    if (bounds.length) {
      map.fitBounds(bounds, { padding: [48, 48], maxZoom: 12 });
    }
  } catch (err) {
    if (handleAuthError(err)) return;
    console.error(err);
    for (const k of allLayerKeys) setLayerError(k, 'Erro ao carregar');
  } finally {
    finishLayerLoadPanelIfDone(generation);
  }
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

async function refreshAll() {
  await Promise.all([loadStats(), loadMap()]);
}

document.addEventListener('DOMContentLoaded', async () => {
  const session = requireAuth();
  if (!session) return;
  renderSidebar('dashboard');
  bindLogout();
  initMap();
  initDraggablePanel($('#gestao-layers'), $('#gestao-layers-handle'));
  initLayersCollapse();
  try {
    catalog = await fetchModerationCatalog(session.token);
    ensureLayerGroups();
    renderLayerControl();
    renderLegend();
  } catch (err) {
    handleAuthError(err);
  }
  await refreshAll();
  $('#btn-gestao-refresh')?.addEventListener('click', refreshAll);
  setTimeout(() => map?.invalidateSize(), 100);
});
