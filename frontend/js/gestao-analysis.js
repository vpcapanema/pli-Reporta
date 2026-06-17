/** Painel de análise de um reporte (moderação). */
import { decideModeration, fetchModerationReportDetail } from './api.js';
import {
  $,
  categoryLabel,
  escHtml,
  formatDate,
  handleAuthError,
  requireAuth,
  statusLabel,
} from './gestao-common.js';

let loadedReportId = null;

const ANALYSIS_EMPTY_HTML = `
  <div class="gestao-analysis-empty">
    <p class="muted">Na aba Registros, clique em <strong>Precisa da sua análise</strong> (ou outro status revisável) para abrir o reporte aqui.</p>
  </div>
`;

function esc(s) {
  if (s == null || s === '') return '—';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderSignals(signals) {
  if (!signals || typeof signals !== 'object') return '<p class="muted">Sem sinais registrados.</p>';
  const rows = Object.entries(signals).map(([k, v]) => {
    const val = typeof v === 'object' ? JSON.stringify(v) : v;
    return `<tr><td><code>${esc(k)}</code></td><td>${esc(val)}</td></tr>`;
  }).join('');
  return `<table class="gestao-analysis-kv"><tbody>${rows}</tbody></table>`;
}

function renderAudit(audit) {
  if (!audit?.length) return '<p class="muted">Nenhum registro de auditoria.</p>';
  return `<ul class="gestao-audit-list">${audit.map((a) => `
    <li><strong>${esc(a.action)}</strong> · ${esc(a.actor)} · ${formatDate(a.ts)}</li>
  `).join('')}</ul>`;
}

function renderPhotoSlot(photoUrl) {
  const safeUrl = photoUrl ? escHtml(photoUrl) : '';
  const body = photoUrl
    ? `<img src="${safeUrl}" alt="Foto enviada pelo cidadão" class="gestao-analysis-photo" loading="lazy" decoding="async"/>`
    : `<p class="gestao-analysis-photo-empty muted">Nenhuma foto anexada a este reporte.</p>`;
  const link = photoUrl
    ? `<a class="gestao-analysis-photo-link" href="${safeUrl}" target="_blank" rel="noopener noreferrer">Abrir em tamanho original</a>`
    : '';
  return `
    <aside class="gestao-analysis-photo-col">
      <h3>Foto enviada</h3>
      <div class="gestao-analysis-photo-frame${photoUrl ? ' is-loading' : ' is-empty'}" data-photo-frame>
        <p class="gestao-analysis-photo-status muted" aria-live="polite">${photoUrl ? 'Carregando foto…' : ''}</p>
        ${body}
      </div>
      ${link}
    </aside>
  `;
}

function bindPhotoSlot(root) {
  const frame = root.querySelector('[data-photo-frame]');
  const img = frame?.querySelector('.gestao-analysis-photo');
  const status = frame?.querySelector('.gestao-analysis-photo-status');
  if (!frame || !img || !status) return;

  const markLoaded = () => {
    frame.classList.remove('is-loading');
    frame.classList.add('is-loaded');
    status.textContent = '';
    status.hidden = true;
  };

  const markError = () => {
    frame.classList.remove('is-loading');
    frame.classList.add('is-error');
    status.hidden = false;
    status.textContent = 'Não foi possível carregar a foto.';
    img.remove();
  };

  if (img.complete && img.naturalWidth > 0) {
    markLoaded();
    return;
  }

  img.addEventListener('load', markLoaded, { once: true });
  img.addEventListener('error', markError, { once: true });
}

export function renderAnalysisEmpty(el) {
  if (!el) return;
  loadedReportId = null;
  el.innerHTML = ANALYSIS_EMPTY_HTML;
}

export function closeAnalysis(panel = null) {
  const el = panel || $('#gestao-analysis');
  if (!el) return;
  renderAnalysisEmpty(el);
  document.dispatchEvent(new CustomEvent('gestao:analysis-closed'));
}

export async function openAnalysis(reportId, catalog, { onDecided = null, panel = null } = {}) {
  const session = requireAuth();
  if (!session || !reportId) return;
  const el = panel || $('#gestao-analysis');
  if (!el) return;
  loadedReportId = reportId;
  el.innerHTML = '<p class="muted gestao-analysis-loading">Carregando análise…</p>';
  try {
    const detail = await fetchModerationReportDetail(session.token, reportId);
    if (loadedReportId !== reportId) return;
    renderAnalysisPanel(el, detail, catalog, onDecided);
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (err) {
    if (loadedReportId !== reportId) return;
    if (handleAuthError(err)) return;
    el.innerHTML = `<p class="gestao-error">${esc(err.message)}</p>`;
  }
}

export function renderAnalysisPanel(el, detail, catalog, onDecided) {
  const canDecide = detail.status === 'em_moderacao';
  const typeLabel = detail.interaction_type === 'manifestacao' ? 'Manifestação cidadã' : 'Evento de tráfego';
  el.innerHTML = `
    <header class="gestao-analysis-header">
      <div>
        <h2>Análise do reporte</h2>
        <p class="muted">${typeLabel} · ${categoryLabel(detail.category, catalog)} · <code>${esc(detail.id)}</code></p>
      </div>
      <button type="button" class="secondary gestao-analysis-close" aria-label="Fechar">Fechar</button>
    </header>
    <div class="gestao-analysis-grid">
      ${renderPhotoSlot(detail.photo_url)}
      <section class="gestao-analysis-main">
        <dl class="gestao-analysis-dl">
          <dt>Status</dt><dd>${statusLabel(detail.status, catalog)}</dd>
          <dt>Recebido</dt><dd>${formatDate(detail.received_at)}</dd>
          <dt>Capturado</dt><dd>${formatDate(detail.captured_at)}</dd>
          <dt>Coordenadas</dt><dd>${detail.lat?.toFixed(5)}, ${detail.lon?.toFixed(5)}</dd>
          ${detail.road_label ? `<dt>Rodovia</dt><dd>${esc(detail.road_label)}</dd>` : ''}
          ${detail.road_scope ? `<dt>Escopo</dt><dd>${esc(detail.road_scope)}</dd>` : ''}
          <dt>Veracidade (V)</dt><dd>${detail.veracity ?? '—'}</dd>
          <dt>Relevância (R)</dt><dd>${detail.relevance ?? '—'}</dd>
          <dt>Prioridade (P)</dt><dd>${detail.priority ?? '—'}</dd>
        </dl>
        ${detail.description ? `<p class="gestao-analysis-desc"><strong>Descrição</strong><br/>${esc(detail.description)}</p>` : ''}
      </section>
      <section class="gestao-analysis-side">
        <h3>Sinais de veracidade</h3>
        ${renderSignals(detail.signals)}
        <h3>Auditoria</h3>
        ${renderAudit(detail.audit)}
      </section>
    </div>
    ${canDecide ? `
      <div class="gestao-analysis-actions">
        <button type="button" data-decision="publicar" data-id="${detail.id}">Publicar no mapa</button>
        <button type="button" class="secondary" data-decision="descartar" data-id="${detail.id}">Arquivar</button>
      </div>
    ` : ''}
  `;

  bindPhotoSlot(el);

  el.querySelector('.gestao-analysis-close')?.addEventListener('click', () => {
    closeAnalysis(el);
  });

  el.querySelectorAll('button[data-decision]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const session = requireAuth();
      if (!session) return;
      const dec = btn.dataset.decision;
      const note = dec === 'descartar' ? prompt('Motivo (opcional):', '') : null;
      try {
        await decideModeration(session.token, detail.id, dec, note);
        if (onDecided) await onDecided();
        await openAnalysis(detail.id, catalog, { onDecided, panel: el });
      } catch (err) {
        alert('Não foi possível concluir: ' + err.message);
      }
    });
  });
}

export function bindAnalysisTabs() {
  const tabLista = $('#gestao-tab-lista');
  const tabAnalise = $('#gestao-tab-analise');
  const panelLista = $('#gestao-panel-lista');
  const panelAnalise = $('#gestao-panel-analise');
  const analysisEl = $('#gestao-analysis');

  renderAnalysisEmpty(analysisEl);

  function showTab(name) {
    const isAnalise = name === 'analise';
    tabLista?.classList.toggle('active', !isAnalise);
    tabAnalise?.classList.toggle('active', isAnalise);
    tabLista?.setAttribute('aria-selected', String(!isAnalise));
    tabAnalise?.setAttribute('aria-selected', String(isAnalise));
    if (panelLista) panelLista.hidden = isAnalise;
    if (panelAnalise) panelAnalise.hidden = !isAnalise;
    if (isAnalise && analysisEl && !loadedReportId && !analysisEl.querySelector('.gestao-analysis-header')) {
      renderAnalysisEmpty(analysisEl);
    }
  }

  showTab('lista');

  tabLista?.addEventListener('click', () => showTab('lista'));
  tabAnalise?.addEventListener('click', () => showTab('analise'));

  return { showTab };
}
