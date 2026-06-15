/** Utilitários compartilhados da console de gestão. */
import {
  clearSession,
  getSession,
} from './api.js';

export const NAV = [
  { id: 'dashboard', href: '/gestao', label: 'Painel', icon: '◉' },
  { id: 'eventos', href: '/gestao/eventos', label: 'Eventos', icon: '◆' },
  { id: 'manifestacoes', href: '/gestao/manifestacoes', label: 'Manifestações', icon: '●' },
  { id: 'aprovador', href: '/gestao/aprovador', label: 'Aprovador automático', icon: '⚙' },
  { id: 'funcionalidades', href: '/gestao/funcionalidades', label: 'Funcionalidades do sistema', icon: '?' },
];

export function $(sel, root = document) {
  return root.querySelector(sel);
}

export function requireAuth() {
  const session = getSession();
  if (!session?.token || session.expiresAt < Date.now()) {
    clearSession();
    location.href = '/acesso';
    return null;
  }
  return session;
}

export function bindLogout() {
  const btn = $('#btn-gestao-logout');
  if (!btn) return;
  btn.addEventListener('click', () => {
    clearSession();
    location.href = '/acesso';
  });
}

export function renderSidebar(activeId) {
  const nav = $('#gestao-nav');
  if (!nav) return;
  nav.innerHTML = NAV.map((item) => `
    <a href="${item.href}" class="gestao-nav-item${item.id === activeId ? ' active' : ''}">
      <span class="gestao-nav-icon" aria-hidden="true">${item.icon}</span>
      <span>${item.label}</span>
    </a>
  `).join('');
  const session = getSession();
  const userEl = $('#gestao-user');
  if (userEl && session) userEl.textContent = session.username;
}

export function statusLabel(status, catalog) {
  return catalog?.statuses?.[status]?.label || status;
}

export function categorySigla(category, catalog) {
  const all = [
    ...(catalog?.event_categories || []),
    ...(catalog?.manifestation_categories || []),
  ];
  const hit = all.find((c) => c.id === category);
  return hit?.sigla || category?.slice(0, 2).toUpperCase() || '?';
}

export function formatDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

export function handleAuthError(err) {
  if (err?.status === 401 || String(err?.message).includes('401')) {
    clearSession();
    location.href = '/acesso';
    return true;
  }
  return false;
}
