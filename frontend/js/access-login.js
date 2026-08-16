/** Login do PLI Reporta — redireciona para /pli-reporta/gestao. */
import { fetchAuthContext, getSession, loginModerator } from './api.js';

function $(s) { return document.querySelector(s); }

function appPath(path) {
  return `${window.__BASE_PATH__ || '/pli-reporta'}${path}`;
}

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

async function onLogin(ev) {
  ev.preventDefault();
  $('#login-error').hidden = true;
  const username = $('#login-user').value.trim();
  const password = $('#login-pass').value;
  try {
    await loginModerator(username, password);
    $('#login-pass').value = '';
    location.href = appPath('/gestao');
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
  const session = getSession();
  if (session?.token && session.expiresAt > Date.now()) {
    location.href = appPath('/gestao');
    return;
  }
  bindPasswordToggle();
  fetchAuthContext().then(applyAuthContext).catch(() => {});
  $('#login-form').addEventListener('submit', onLogin);
});
