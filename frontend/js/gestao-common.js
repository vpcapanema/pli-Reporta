/** Utilitários compartilhados da console de gestão. */
import {
  clearSession,
  getSession,
} from './api.js';
import { mountSidebarBrands } from './sidebar-brand.js';

const SVG = {
  dashboard: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>`,
  eventos: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  manifestacoes: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
  aprovador: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>`,
  funcionalidades: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`,
};

// As abas que cada pagina tinha no conteudo viram sub-itens do menu lateral:
// "tab" e o id do botao de aba (mantido no HTML, oculto) que o sub-item aciona.
const ABAS_REGISTROS_ANALISE = [
  { id: 'lista',   label: 'Registros', tab: 'gestao-tab-lista' },
  { id: 'analise', label: 'Análise',   tab: 'gestao-tab-analise' },
];

export const NAV = [
  { id: 'dashboard',       href: '/gestao',                  label: 'Painel',                    icon: SVG.dashboard },
  { id: 'eventos',         href: '/gestao/eventos',          label: 'Eventos de Tráfego',        icon: SVG.eventos,        children: ABAS_REGISTROS_ANALISE },
  { id: 'manifestacoes',   href: '/gestao/manifestacoes',    label: 'Manifestação Cidadã',       icon: SVG.manifestacoes,  children: ABAS_REGISTROS_ANALISE },
  { id: 'aprovador',       href: '/gestao/aprovador',        label: 'Aprovador automático',      icon: SVG.aprovador,
    children: [
      { id: 'eventos',       label: 'Eventos de tráfego',     tab: 'tab-eventos' },
      { id: 'manifestacoes', label: 'Manifestações cidadãs',  tab: 'tab-manifestacoes' },
    ] },
  { id: 'funcionalidades', href: '/gestao/funcionalidades',  label: 'Funcionalidades do sistema', icon: SVG.funcionalidades },
];

export function $(sel, root = document) {
  return root.querySelector(sel);
}

export function requireAuth() {
  const session = getSession();
  if (!session?.token || session.expiresAt < Date.now()) {
    clearSession();
    location.href = appPath('/acesso');
    return null;
  }
  return session;
}

function appPath(path) {
  const prefix = window.__BASE_PATH__ || '/pli-reporta';
  if (!prefix || path.startsWith(`${prefix}/`) || path === prefix) return path;
  return path === '/' ? `${prefix}/` : `${prefix}${path}`;
}

/**
 * O rodape da sidebar e fixo: so o credito padrao do ecossistema, que ja vem
 * no HTML. "Voltar ao mapa" e "Sair" ficam na barra de sessao, logo abaixo do
 * cabecalho da pagina — nao se injeta mais nada aqui.
 */
function renderSidebarFooter() {}

export function bindLogout() {
  const btn = $('#btn-gestao-logout');
  if (!btn) return;
  btn.addEventListener('click', () => {
    clearSession();
    location.href = appPath('/acesso');
  });
}

export function renderSidebar(activeId) {
  mountSidebarBrands();
  renderSidebarFooter();
  const nav = $('#gestao-nav');
  if (!nav) return;
  // Os href do NAV sao relativos a raiz da app; sem appPath eles apontariam
  // para a raiz do dominio, fora do prefixo em que a app e servida.
  nav.innerHTML = NAV.map((item) => {
    const active = item.id === activeId;
    const expandido = active && Array.isArray(item.children);
    const filhos = expandido ? `
      <div class="gestao-nav-sub" role="group" aria-label="${item.label}">
        ${item.children.map((c) => `
          <a href="${appPath(item.href)}?aba=${c.id}" class="gestao-nav-subitem"
             data-aba="${c.id}" data-tab="${c.tab}">${c.label}</a>`).join('')}
      </div>` : '';
    return `
    <a href="${appPath(item.href)}" class="gestao-nav-item${active ? ' active' : ''}${item.children ? ' has-children' : ''}"
       aria-expanded="${expandido ? 'true' : 'false'}">
      <span class="gestao-nav-icon" aria-hidden="true">${item.icon}</span>
      <span>${item.label}</span>
    </a>${filhos}`;
  }).join('');
  bindSubnav(nav);
  const session = getSession();
  const userEl = $('#gestao-user');
  if (userEl && session) userEl.textContent = session.fullName || session.username;
  renderSessionBar(session);
}

/**
 * Sub-itens do menu: cada um aciona o botao de aba correspondente, que segue no
 * HTML (oculto por CSS) com seus handlers. A aba escolhida vai para ?aba= na
 * URL, entao o link de outra pagina ja abre no sub-item certo.
 */
function bindSubnav(nav) {
  const subitens = [...nav.querySelectorAll('.gestao-nav-subitem')];
  if (!subitens.length) return;

  const ativar = (el, { atualizarUrl = true } = {}) => {
    subitens.forEach((s) => s.classList.toggle('active', s === el));
    document.getElementById(el.dataset.tab)?.click();
    if (atualizarUrl) {
      const url = new URL(location.href);
      url.searchParams.set('aba', el.dataset.aba);
      history.replaceState(null, '', url);
    }
  };

  subitens.forEach((el) => el.addEventListener('click', (ev) => {
    ev.preventDefault();
    ativar(el);
  }));

  // Estado inicial: ?aba= da URL ou o primeiro sub-item. Adiado para depois da
  // inicializacao da pagina, que e quem liga os handlers dos botoes de aba.
  const pedida = new URLSearchParams(location.search).get('aba');
  const inicial = subitens.find((s) => s.dataset.aba === pedida) || subitens[0];
  setTimeout(() => ativar(inicial, { atualizarUrl: Boolean(pedida) }), 0);
}

/** Monta a barra de status/sessão no topo do conteúdo (nome, @username, tipo, sair). */
export function renderSessionBar(session) {
  const sess = session || getSession();
  const main = document.querySelector('.gestao-main');
  if (!main || !sess) return;
  let bar = $('#gestao-session-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'gestao-session-bar';
    bar.className = 'adm-session-bar';
    bar.setAttribute('aria-label', 'Sessão ativa');
  }
  // Estrutura fixa das paginas restritas: a barra de sessao vem imediatamente
  // apos o cabecalho da pagina. Reposiciona sempre, porque paginas como a de
  // eventos inserem elementos (abas) logo apos o cabecalho depois desta chamada.
  const header = main.querySelector('.gestao-header');
  if (header) {
    if (header.nextElementSibling !== bar) header.insertAdjacentElement('afterend', bar);
  } else if (!bar.parentElement) {
    main.insertBefore(bar, main.firstChild);
  }
  const name = sess.fullName || sess.username || '';
  const username = sess.username || '';
  const tipo = sess.tipoUsuario || 'GESTOR';
  bar.innerHTML = `
    <div class="adm-session-user">
      <span class="adm-session-status" aria-hidden="true"></span>
      <strong>${escHtml(name)}</strong>
      <span class="adm-session-username">@${escHtml(username)}</span>
      <span class="adm-session-role">${escHtml(tipo)}</span>
    </div>
    <button type="button" class="adm-session-logout" id="adm-session-logout">Sair</button>
  `;
  const logoutBtn = bar.querySelector('#adm-session-logout');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      clearSession();
      location.href = appPath('/acesso');
    });
  }
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
    location.href = appPath('/acesso');
    return true;
  }
  return false;
}
