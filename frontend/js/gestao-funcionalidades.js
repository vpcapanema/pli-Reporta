/** Página "Funcionalidades do sistema" — glossário de ícones, siglas e status. */
import { fetchModerationCatalog } from './api.js';
import {
  $,
  bindLogout,
  handleAuthError,
  renderSidebar,
  requireAuth,
} from './gestao-common.js';
import { markerPreview } from './gestao-markers.js';

/** Seção 1 — Forma do marcador */
function renderShapes(catalog) {
  const el = $('#gloss-shapes');
  if (!el) return;
  el.innerHTML = (catalog.interaction_types || []).map((t) => `
    <div class="gestao-gloss-card">
      ${markerPreview({ shape: t.shape, sigla: '' })}
      <div>
        <strong>${t.label}</strong>
        <span class="muted">${t.descricao}</span>
      </div>
    </div>
  `).join('');
}

/** Seção 2 — Ícone no marcador (eventos + manifestações) */
function renderCategories(catalog) {
  const ev = $('#gloss-cat-eventos');
  const mn = $('#gloss-cat-manif');

  const card = (c, shape, withIcon) => `
    <div class="gestao-gloss-card">
      ${markerPreview({ shape, sigla: c.sigla, id: withIcon ? c.id : null })}
      <div>
        <strong>${c.label}</strong>
        <span class="muted">${c.sigla}</span>
      </div>
    </div>
  `;

  if (ev) ev.innerHTML = (catalog.event_categories || []).map((c) => card(c, 'diamond', true)).join('');
  if (mn) mn.innerHTML = (catalog.manifestation_categories || []).map((c) => card(c, 'circle', false)).join('');
}

/** Seção 3 — Status (matriz de visibilidade + descrição) */
function renderStatuses(catalog) {
  const el = $('#gloss-status');
  if (!el) return;
  const entries = Object.entries(catalog.statuses || {});
  const badge = (on, label) => `<span class="gestao-vis-badge ${on ? 'on' : 'off'}" title="${label}">${on ? '✓' : '—'} ${label}</span>`;
  el.innerHTML = entries.map(([id, m]) => `
    <div class="gestao-gloss-status-row">
      <span class="gestao-gloss-border" style="border-color:${m.cor}"></span>
      <div class="gestao-gloss-status-body">
        <strong>${m.label}</strong>
        <code class="gestao-gloss-status-id">${id}</code>
        <span class="muted">${m.descricao}</span>
        <div class="gestao-vis-badges">
          ${badge(m.visivel_mapa_publico, 'Mapa público')}
          ${badge(m.visivel_mapa_gestao, m.camada_gestao === 'municipal' ? 'Gestão (municipal)' : 'Mapa gestão')}
          ${badge(m.export_publico, 'Export público')}
          ${badge(m.export_gestao, 'Export gestão')}
        </div>
      </div>
      <code>${m.cor}</code>
    </div>
  `).join('');
}

document.addEventListener('DOMContentLoaded', async () => {
  const session = requireAuth();
  if (!session) return;
  renderSidebar('funcionalidades');
  bindLogout();
  try {
    const catalog = await fetchModerationCatalog(session.token);
    renderShapes(catalog);
    renderCategories(catalog);
    renderStatuses(catalog);
  } catch (err) {
    handleAuthError(err);
  }
});
