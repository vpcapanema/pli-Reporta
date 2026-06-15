// Painel de acesso restrito — login por usuário/senha.

import {

  loginModerator,

  fetchAuthContext,

  fetchModerationQueue,

  decideModeration,

  clearSession,

  getSession,

} from './api.js';



function $(s) { return document.querySelector(s); }



function applyAuthContext(ctx) {

  if (!ctx) return;



  const idField = ctx.identifier;

  if (idField) {

    $('#login-user-label').textContent = idField.label;

    if (idField.placeholder) $('#login-user').placeholder = idField.placeholder;

  }



  const passField = ctx.password;

  if (passField) {

    $('#login-pass-label').textContent = passField.label;

    if (passField.placeholder) $('#login-pass').placeholder = passField.placeholder;

  }



  const links = ctx.sigma_links;

  if (!links) return;



  const forgot = $('#link-recuperar-senha');

  const register = $('#link-cadastro');

  if (links.recuperar_senha && forgot) {

    forgot.href = links.recuperar_senha;

    forgot.hidden = false;

  }

  if (links.cadastro && register) {

    register.href = links.cadastro;

    register.hidden = false;

    $('#access-divider').hidden = false;

  }

}



function bindPasswordToggle() {

  const input = $('#login-pass');

  const btn = $('#login-toggle-pw');

  if (!input || !btn) return;

  btn.addEventListener('click', () => {

    const show = input.type === 'password';

    input.type = show ? 'text' : 'password';

    btn.setAttribute('aria-label', show ? 'Ocultar senha' : 'Mostrar senha');

  });

}



async function initLoginPanel() {

  bindPasswordToggle();

  try {

    const ctx = await fetchAuthContext();

    applyAuthContext(ctx);

  } catch (_) {

    // Mantém textos padrão do HTML se a API não responder.

  }

}



function showLogin() {

  $('#login-panel').hidden = false;

  $('#mod-panel').hidden = true;

  $('#mod-user').hidden = true;

}



function showPanel(username) {

  $('#login-panel').hidden = true;

  $('#mod-panel').hidden = false;

  $('#mod-user').hidden = false;

  $('#mod-user').textContent = username;

}



async function loadQueue() {

  const session = getSession();

  if (!session?.token) {

    showLogin();

    return;

  }

  try {

    const data = await fetchModerationQueue(session.token);

    showPanel(data.moderator || session.username);

    render(data);

  } catch (err) {

    if (String(err.message).includes('401')) {

      clearSession();

      showLogin();

      $('#login-error').hidden = false;

      $('#login-error').textContent = 'Sessão expirada. Entre novamente.';

      return;

    }

    $('#mod-list').innerHTML = `<p>Erro: ${err.message}</p>`;

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

    const typeLabel = it.interaction_type === 'manifestacao' ? 'Manifestação' : 'Evento';

    const signalsHtml = Object.entries(it.signals || {})

      .map(([k, v]) => `<li>${k}=${(v.value).toFixed(2)} — ${v.detail}</li>`).join('');

    card.innerHTML = `

      <div><strong>${typeLabel} · ${it.category}</strong> · ${it.magnitude} ·

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

      const session = getSession();

      const id = b.dataset.id;

      const dec = b.dataset.decision;

      const note = dec === 'descartar' ? prompt('Motivo (opcional):', '') : null;

      try {

        await decideModeration(session.token, id, dec, note);

        loadQueue();

      } catch (err) {

        alert('Falhou: ' + err.message);

      }

    });

  });

}



async function onLogin(ev) {

  ev.preventDefault();

  $('#login-error').hidden = true;

  const username = $('#login-user').value.trim();

  const password = $('#login-pass').value;

  try {

    await loginModerator(username, password);

    $('#login-pass').value = '';

    loadQueue();

  } catch (err) {

    $('#login-error').hidden = false;

    if (err.status === 503) {

      $('#login-error').textContent = err.message || 'SIGMA indisponível. Verifique conectividade com a VM.';

    } else {

      $('#login-error').textContent = 'Usuário ou senha inválidos.';

    }

  }

}



document.addEventListener('DOMContentLoaded', () => {

  initLoginPanel();

  $('#login-form').addEventListener('submit', onLogin);

  $('#btn-refresh').addEventListener('click', loadQueue);

  $('#btn-logout').addEventListener('click', () => {

    clearSession();

    showLogin();

  });

  loadQueue();

});


