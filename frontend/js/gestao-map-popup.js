/** HTML dos popups Leaflet no mapa de gestão. */
import { categoryLabel, escHtml, formatDate, statusLabel } from './gestao-common.js';
import { resolveStatusColor } from './gestao-markers.js';
import {
  buildMunicipalFallbackRows,
  buildRoadContextRows,
  normalizeRoadContext,
  rodoviaLine,
} from './road-context-labels.js';

function formatScore(value) {
  if (value == null || value === '') return null;
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 3 });
}

function kvRowsHtml(rows, prefix = 'gestao-map-popup') {
  if (!rows.length) return '';
  const items = rows.map(({ label, value }) => `
    <div class="${prefix}-kv-row">
      <dt>${escHtml(label)}</dt>
      <dd>${escHtml(value)}</dd>
    </div>`).join('');
  return `<dl class="${prefix}-kv">${items}</dl>`;
}

function roadContextBlock(p) {
  const isEvent = p.interaction_type !== 'manifestacao';
  if (!isEvent) return '';

  const ctx = normalizeRoadContext(p.road_context);
  let rows = buildRoadContextRows(ctx);
  if (!rows.length) {
    rows = buildMunicipalFallbackRows(p);
  }
  if (!rows.length && p.road_label) {
    rows = [{ label: 'Referência local', value: String(p.road_label) }];
  }
  if (!rows.length) return '';
  return `<section class="gestao-map-popup-section"><h4>Local viário</h4>${kvRowsHtml(rows)}</section>`;
}

function scoreRow(label, value) {
  const formatted = formatScore(value);
  if (formatted == null) return '';
  return `<div class="gestao-map-popup-metric"><span>${label}</span><strong>${escHtml(formatted)}</strong></div>`;
}

/** Conteúdo do popup ao clicar em um ponto do mapa. */
export function buildGestaoPopupHtml(p, catalog, { showResolve = false } = {}) {
  const isManif = p.interaction_type === 'manifestacao';
  const typeLabel = isManif ? 'Manifestação cidadã' : 'Evento de tráfego';
  const catLabel = categoryLabel(p.category, catalog);
  const status = statusLabel(p.status, catalog);
  const statusColor = resolveStatusColor(p, catalog);
  const desc = p.description ? escHtml(String(p.description).slice(0, 280)) : '';
  const photo = p.photo_url
    ? `<img src="${escHtml(p.photo_url)}" alt="" class="gestao-map-popup-photo" loading="lazy"/>`
    : '';
  const resolveBtn = showResolve && !isManif && p.cluster_id
    ? `<button type="button" class="gestao-map-popup-resolve popup-resolver" data-cluster="${escHtml(p.cluster_id)}">Já foi resolvido?</button>`
    : '';

  return `
    <div class="gestao-map-popup-inner">
      <header class="gestao-map-popup-head">
        <div>
          <strong>${escHtml(typeLabel)}</strong>
          <span class="gestao-map-popup-cat">${escHtml(catLabel)}</span>
        </div>
        <span class="gestao-map-popup-status" style="color:${statusColor}">${escHtml(status)}</span>
      </header>
      ${roadContextBlock(p)}
      ${desc ? `<p class="gestao-map-popup-desc"><strong>Descrição</strong><br/>${desc}</p>` : ''}
      <div class="gestao-map-popup-metrics">
        ${scoreRow('Veracidade (V)', p.veracity)}
        ${scoreRow('Relevância (R)', p.relevance)}
        ${scoreRow('Prioridade (P)', p.priority)}
      </div>
      ${photo}
      ${resolveBtn}
      <footer class="gestao-map-popup-foot muted">
        <span>${formatDate(p.received_at || p.captured_at)}</span>
        <code title="${escHtml(p.id)}">${escHtml(p.id)}</code>
      </footer>
    </div>`;
}

/** Linhas viárias compactas para mapa público. */
export function buildPublicRoadContextHtml(p) {
  const ctx = normalizeRoadContext(p?.road_context);
  let rows = buildRoadContextRows(ctx);
  if (!rows.length) rows = buildMunicipalFallbackRows(p);
  if (!rows.length) return '';
  return kvRowsHtml(rows, 'map-popup');
}

export { rodoviaLine };
