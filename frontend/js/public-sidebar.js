/** Navegação lateral compartilhada das páginas públicas. */

export const PUBLIC_NAV_ICONS = {
  mapa: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>',
  api: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
  reportar: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
  relatorios: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
};

const NAV_ITEMS = [
  { id: 'mapa', href: '/mapa', label: 'Mapa público', icon: 'mapa' },
  { id: 'api', href: '/api-publica', label: 'API pública', icon: 'api' },
  { id: 'reportar', href: '/', label: 'Reportar', icon: 'reportar' },
];

function navBlock(item, active) {
  const icon = PUBLIC_NAV_ICONS[item.icon];
  if (item.id === active) {
    return `
      <section class="public-sidebar-block" aria-label="${item.label}">
        <span class="public-nav-item active" aria-current="page">
          <span class="public-nav-icon" aria-hidden="true">${icon}</span>
          <span>${item.label}</span>
        </span>
      </section>`;
  }
  return `
    <section class="public-sidebar-block" aria-label="${item.label}">
      <a class="public-nav-item" href="${item.href}">
        <span class="public-nav-icon" aria-hidden="true">${icon}</span>
        <span>${item.label}</span>
      </a>
    </section>`;
}

/** @param {string|Element} container */
export function mountPublicNav(container, active) {
  const el = typeof container === 'string' ? document.querySelector(container) : container;
  if (!el) return;
  el.innerHTML = NAV_ITEMS.map((item) => navBlock(item, active)).join('');
}

/** Itens de navegação exceto o da página atual (menu primário fica no HTML). */
export function mountPublicNavSecondary(container, activeId) {
  const el = typeof container === 'string' ? document.querySelector(container) : container;
  if (!el) return;
  el.innerHTML = NAV_ITEMS.filter((item) => item.id !== activeId)
    .map((item) => navBlock(item, null))
    .join('');
}

/**
 * @param {string} panelId
 * @param {{ defaultExpanded?: boolean }} [opts]
 */
export function bindSidebarCollapse(panelId, opts = {}) {
  const { defaultExpanded = true } = opts;
  const panel = document.getElementById(panelId);
  if (!panel || panel.dataset.collapseBound) return;
  const btn = panel.querySelector('.public-nav-item-toggle');
  const body = panel.querySelector('.public-sidebar-block-body');
  if (!btn || !body) return;

  panel.dataset.collapseBound = '1';

  if (defaultExpanded) {
    panel.classList.remove('collapsed');
    body.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
  } else {
    panel.classList.add('collapsed');
    body.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
  }

  btn.addEventListener('click', () => {
    const collapsed = panel.classList.toggle('collapsed');
    body.hidden = collapsed;
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  });
}

let relatoriosToggleBound = false;

export function bindRelatoriosCollapse() {
  if (relatoriosToggleBound) return;
  relatoriosToggleBound = true;
  bindSidebarCollapse('panel-relatorios', { defaultExpanded: false });
}
