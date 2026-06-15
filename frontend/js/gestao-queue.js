/** Fila "Precisa da sua análise" — compartilhada entre eventos e manifestações. */
import { decideModeration, fetchModerationQueue } from './api.js';
import { $, categoryLabel, formatDate, handleAuthError, requireAuth, statusLabel } from './gestao-common.js';

export async function loadQueue(catalog, { interactionType = null, onRefresh = null } = {}) {
  const session = requireAuth();
  if (!session) return;
  const list = $('#gestao-queue');
  const countEl = $('#gestao-fila-count');
  if (!list) return;
  try {
    const data = await fetchModerationQueue(session.token);
    let items = data.items || [];
    if (interactionType) {
      items = items.filter((it) => it.interaction_type === interactionType);
    }
    if (countEl) countEl.textContent = items.length;
    renderQueue(list, items, catalog, onRefresh);
  } catch (err) {
    if (handleAuthError(err)) return;
    list.innerHTML = `<p class="gestao-error">${err.message}</p>`;
  }
}

function renderQueue(list, items, catalog, onRefresh) {
  if (!items.length) {
    list.innerHTML = '<p class="muted gestao-empty">Nenhum reporte aguardando sua análise.</p>';
    return;
  }
  list.innerHTML = items.map((it) => {
    const typeLabel = it.interaction_type === 'manifestacao' ? 'Manifestação' : 'Evento';
    const photo = it.photo_url ? `<img src="${it.photo_url}" alt="" class="gestao-queue-photo"/>` : '';
    return `
      <article class="gestao-queue-card" data-id="${it.id}">
        <header>
          <strong>${typeLabel} · ${categoryLabel(it.category, catalog)}</strong>
          <span class="gestao-badge">${statusLabel(it.status, catalog)}</span>
        </header>
        <p class="muted">${formatDate(it.received_at)}</p>
        ${it.description ? `<p>${it.description}</p>` : ''}
        ${photo}
        <div class="gestao-queue-actions">
          <button type="button" data-action="analise" data-id="${it.id}">Analisar</button>
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
        if (onRefresh) await onRefresh();
      } catch (err) {
        alert('Não foi possível concluir: ' + err.message);
      }
    });
  });

  list.querySelectorAll('button[data-action="analise"]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.id;
      document.dispatchEvent(new CustomEvent('gestao:open-analysis', { detail: { id } }));
    });
  });
}
