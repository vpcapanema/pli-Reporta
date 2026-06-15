/** Página "Funcionalidades do sistema" — glossário de ícones, siglas e status. */
import { fetchModerationCatalog } from './api.js';
import {
  $,
  bindLogout,
  handleAuthError,
  renderSidebar,
  requireAuth,
} from './gestao-common.js';

/** Categorias cujo arquivo de ícone é PNG (Flaticon); demais são SVG (FA 6). */
const PNG_IDS = new Set([
  'acidente', 'alagamento', 'bloqueio_total',
  'lentidao_corredor', 'obra_grande', 'queda_arvore', 'sinalizacao_quebrada',
]);

function iconUrl(id) {
  return `/static/img/icons/${id}.${PNG_IDS.has(id) ? 'png' : 'svg'}`;
}

/**
 * Gera o HTML do marcador losangular/circular.
 * Se `id` for passado, renderiza <img> com o ícone; senão exibe a sigla.
 */
function markerPreview({ shape, sigla, color, id }) {
  const shapeClass = shape === 'diamond' ? 'gestao-marker-diamond' : 'gestao-marker-circle';
  const inner = id
    ? `<img src="${iconUrl(id)}" alt="${sigla}" class="gestao-marker-icon"/>`
    : (sigla || '');
  return `<div class="gestao-marker ${shapeClass}" style="border-color:${color || '#64748b'}">
    <span class="gestao-marker-inner">${inner}</span>
  </div>`;
}

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

/** Seção 3 — Status (a lista de ciclo de vida está diretamente no HTML) */
function renderStatuses(catalog) {
  const el = $('#gloss-status');
  if (!el) return;
  const entries = Object.entries(catalog.statuses || {});
  el.innerHTML = entries.map(([, m]) => `
    <div class="gestao-gloss-status-row">
      <span class="gestao-gloss-border" style="border-color:${m.cor}"></span>
      <div>
        <strong>${m.label}</strong>
        <span class="muted">${m.descricao}</span>
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
