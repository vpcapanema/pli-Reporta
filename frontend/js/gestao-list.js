/** Listagens de eventos e manifestações + fila e análise. */
import { fetchManagementReports, fetchModerationCatalog } from './api.js';
import { bindAnalysisTabs, openAnalysis } from './gestao-analysis.js';
import { loadQueue } from './gestao-queue.js';
import {
  $,
  bindLogout,
  categoryLabel,
  formatDate,
  handleAuthError,
  renderSidebar,
  requireAuth,
  REVIEW_STATUSES,
  statusLabel,
} from './gestao-common.js';

const PAGE = document.body.dataset.page || 'eventos';
const INTERACTION = PAGE === 'manifestacoes' ? 'manifestacao' : 'evento_trafego';

let catalog = null;
let offset = 0;
const LIMIT = 40;
let tabsApi = null;

function statusCell(it) {
  const label = statusLabel(it.status, catalog);
  if (REVIEW_STATUSES.has(it.status)) {
    return `<button type="button" class="gestao-status-link" data-id="${it.id}" title="Abrir análise">${label}</button>`;
  }
  return `<span class="gestao-status-text">${label}</span>`;
}

function renderTable(data) {
  const tbody = $('#gestao-table-body');
  const meta = $('#gestao-table-meta');
  if (!tbody) return;
  if (!data.items?.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="muted">Nenhum registro encontrado.</td></tr>';
  } else {
    tbody.innerHTML = data.items.map((it) => `
      <tr data-id="${it.id}">
        <td><code>${it.id.slice(0, 8)}…</code></td>
        <td>${categoryLabel(it.category, catalog)}</td>
        <td>${statusCell(it)}</td>
        <td>${formatDate(it.received_at)}</td>
        <td>${it.lat.toFixed(4)}, ${it.lon.toFixed(4)}</td>
        <td>${it.description ? it.description.slice(0, 80) : '—'}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('.gestao-status-link').forEach((btn) => {
      btn.addEventListener('click', () => selectReport(btn.dataset.id));
    });
  }
  if (meta) {
    meta.textContent = `Mostrando ${data.items.length} de ${data.total} · offset ${data.offset}`;
  }
  $('#btn-prev').disabled = offset <= 0;
  $('#btn-next').disabled = offset + LIMIT >= data.total;
}

async function selectReport(id) {
  if (!id) return;
  tabsApi?.showTab('analise');
  await openAnalysis(id, catalog, {
    onDecided: refreshAll,
    panel: $('#gestao-analysis'),
  });
}

async function loadList() {
  const session = requireAuth();
  if (!session) return;
  const status = $('#filter-status')?.value || '';
  try {
    const data = await fetchManagementReports(session.token, {
      interaction_type: INTERACTION,
      status: status || undefined,
      limit: LIMIT,
      offset,
    });
    renderTable(data);
  } catch (err) {
    if (handleAuthError(err)) return;
    $('#gestao-table-body').innerHTML = `<tr><td colspan="6">${err.message}</td></tr>`;
  }
}

async function refreshAll() {
  await Promise.all([
    loadList(),
    loadQueue(catalog, { interactionType: INTERACTION, onRefresh: refreshAll }),
  ]);
}

document.addEventListener('DOMContentLoaded', async () => {
  const session = requireAuth();
  if (!session) return;
  renderSidebar(PAGE);
  bindLogout();
  tabsApi = bindAnalysisTabs();

  document.addEventListener('gestao:open-analysis', (ev) => {
    selectReport(ev.detail?.id);
  });

  try {
    catalog = await fetchModerationCatalog(session.token);
    const sel = $('#filter-status');
    if (sel && catalog?.statuses) {
      Object.entries(catalog.statuses).forEach(([id, m]) => {
        const opt = document.createElement('option');
        opt.value = id;
        opt.textContent = m.label;
        sel.appendChild(opt);
      });
    }
  } catch (err) {
    handleAuthError(err);
  }

  $('#filter-status')?.addEventListener('change', () => { offset = 0; loadList(); });
  $('#btn-prev')?.addEventListener('click', () => { offset = Math.max(0, offset - LIMIT); loadList(); });
  $('#btn-next')?.addEventListener('click', () => { offset += LIMIT; loadList(); });
  $('#btn-reload')?.addEventListener('click', refreshAll);
  await refreshAll();
});
