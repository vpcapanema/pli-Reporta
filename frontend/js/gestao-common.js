/** Utilitários compartilhados da console de gestão. */
import {
  clearSession,
  getSession,
} from './api.js';

const SVG = {
  dashboard: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>`,
  eventos: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  manifestacoes: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
  aprovador: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>`,
  funcionalidades: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`,
};

export const NAV = [
  { id: 'dashboard',       href: '/gestao',                  label: 'Painel',                    icon: SVG.dashboard },
  { id: 'eventos',         href: '/gestao/eventos',          label: 'Eventos de Tráfego',        icon: SVG.eventos },
  { id: 'manifestacoes',   href: '/gestao/manifestacoes',    label: 'Manifestação Cidadã',       icon: SVG.manifestacoes },
  { id: 'aprovador',       href: '/gestao/aprovador',        label: 'Aprovador automático',      icon: SVG.aprovador },
  { id: 'funcionalidades', href: '/gestao/funcionalidades',  label: 'Funcionalidades do sistema', icon: SVG.funcionalidades },
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

export function categoryLabel(category, catalog) {
  const all = [
    ...(catalog?.event_categories || []),
    ...(catalog?.manifestation_categories || []),
  ];
  const hit = all.find((c) => c.id === category);
  return hit?.label || category || '—';
}

export function categorySigla(category, catalog) {
  const all = [
    ...(catalog?.event_categories || []),
    ...(catalog?.manifestation_categories || []),
  ];
  const hit = all.find((c) => c.id === category);
  return hit?.sigla || category?.slice(0, 2).toUpperCase() || '?';
}

/** Status que permitem abrir painel de análise ao clicar na tabela. */
export const REVIEW_STATUSES = new Set(['em_moderacao', 'submetido']);

export function formatDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

export function escHtml(s) {
  if (s == null || s === '') return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function handleAuthError(err) {
  if (err?.status === 401 || String(err?.message).includes('401')) {
    clearSession();
    location.href = '/acesso';
    return true;
  }
  return false;
}
