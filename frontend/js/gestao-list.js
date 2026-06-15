/** Listagens de eventos e manifestações. */
import { fetchManagementReports, fetchModerationCatalog } from './api.js';
import {
  $,
  bindLogout,
  formatDate,
  handleAuthError,
  renderSidebar,
  requireAuth,
  statusLabel,
} from './gestao-common.js';

const PAGE = document.body.dataset.page || 'eventos';
const INTERACTION = PAGE === 'manifestacoes' ? 'manifestacao' : 'evento_trafego';

let catalog = null;
let offset = 0;
const LIMIT = 40;

function renderTable(data) {
  const tbody = $('#gestao-table-body');
  const meta = $('#gestao-table-meta');
  if (!tbody) return;
  if (!data.items?.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="muted">Nenhum registro encontrado.</td></tr>';
  } else {
    tbody.innerHTML = data.items.map((it) => `
      <tr>
        <td><code>${it.id.slice(0, 8)}…</code></td>
        <td>${it.category}</td>
        <td>${statusLabel(it.status, catalog)}</td>
        <td>${formatDate(it.received_at)}</td>
        <td>${it.lat.toFixed(4)}, ${it.lon.toFixed(4)}</td>
        <td>${it.description ? it.description.slice(0, 80) : '—'}</td>
      </tr>
    `).join('');
  }
  if (meta) {
    meta.textContent = `Mostrando ${data.items.length} de ${data.total} · offset ${data.offset}`;
  }
  $('#btn-prev').disabled = offset <= 0;
  $('#btn-next').disabled = offset + LIMIT >= data.total;
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

document.addEventListener('DOMContentLoaded', async () => {
  const session = requireAuth();
  if (!session) return;
  renderSidebar(PAGE);
  bindLogout();
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
  $('#btn-reload')?.addEventListener('click', loadList);
  loadList();
});
