// Painel de moderação (faixa cinza). Pede API key e exibe a fila.
import { fetchModerationQueue, decideModeration } from './api.js';

const KEY_STORAGE = 'pli-reporta-mod-key';

function $(s) { return document.querySelector(s); }

async function loadQueue() {
  const apiKey = localStorage.getItem(KEY_STORAGE) || '';
  if (!apiKey) {
    promptKey();
    return;
  }
  try {
    const data = await fetchModerationQueue(apiKey);
    render(data);
  } catch (err) {
    $('#mod-list').innerHTML = `<p>Erro: ${err.message}</p>`;
    promptKey();
  }
}

function promptKey() {
  const cur = localStorage.getItem(KEY_STORAGE) || '';
  const key = prompt('Informe MODERATOR_API_KEY:', cur);
  if (key) {
    localStorage.setItem(KEY_STORAGE, key.trim());
    loadQueue();
  }
}

function render(data) {
  const list = $('#mod-list');
  $('#mod-count').textContent = data.queue_size;
  if (!data.items.length) {
    list.innerHTML = '<p class="muted">Fila vazia.</p>';
    return;
  }
  list.innerHTML = '';
  for (const it of data.items) {
    const card = document.createElement('div');
    card.className = 'card queue-item';
    const photoUrl = `/media/${(it.photo_path || '').replace(/\\/g, '/')}`;
    const signalsHtml = Object.entries(it.signals || {})
      .map(([k, v]) => `<li>${k}=${(v.value).toFixed(2)} — ${v.detail}</li>`).join('');
    card.innerHTML = `
      <div><strong>${it.category}</strong> · ${it.magnitude} ·
        V=${it.veracity} · R=${it.relevance} · P=${it.priority}</div>
      <div class="meta">id=${it.id} · captured_at=${it.captured_at}</div>
      <div class="meta">lat=${it.lat.toFixed(5)} · lon=${it.lon.toFixed(5)}</div>
      ${it.description ? `<div>“${it.description}”</div>` : ''}
      <img src="${photoUrl}" alt="reporte"/>
      <ul class="signals">${signalsHtml}</ul>
      <div class="actions">
        <button data-id="${it.id}" data-decision="publicar">Publicar</button>
        <button class="secondary" data-id="${it.id}" data-decision="descartar">Descartar</button>
      </div>
    `;
    list.appendChild(card);
  }
  list.querySelectorAll('button[data-decision]').forEach((b) => {
    b.addEventListener('click', async () => {
      const apiKey = localStorage.getItem(KEY_STORAGE);
      const id = b.dataset.id;
      const dec = b.dataset.decision;
      const note = dec === 'descartar' ? prompt('Motivo (opcional):', '') : null;
      try {
        await decideModeration(apiKey, id, dec, note);
        loadQueue();
      } catch (err) {
        alert('Falhou: ' + err.message);
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  $('#btn-key').addEventListener('click', promptKey);
  $('#btn-refresh').addEventListener('click', loadQueue);
  loadQueue();
});
