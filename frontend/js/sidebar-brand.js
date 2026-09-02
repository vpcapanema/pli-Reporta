/** Marca PLI Reporta nas sidebars — icone verde + nome branco, slogan abaixo.
 *  Mesma marca do cabeçalho da página inicial, para não haver duas identidades. */

export const PLI_MARK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" focusable="false" aria-hidden="true"><path d="M3 11v2a1 1 0 0 0 1 1h2.5L14 19V5L6.5 10H4a1 1 0 0 0-1 1Z"/><path d="M6.5 14v4.5a1.5 1.5 0 0 0 3 0V16"/><path d="M18 9.5a3.5 3.5 0 0 1 0 5"/><path d="M20.5 7a7 7 0 0 1 0 10"/></svg>';

/**
 * A marca e montada em runtime, depois da entrega da pagina, entao escapa da
 * reescrita de links que o backend faz no HTML servido. Sem o prefixo, o link
 * iria para a raiz do dominio em vez da raiz da app.
 */
function homeHref() {
  const prefixo = window.__BASE_PATH__ || '/pli-reporta';
  return prefixo ? `${prefixo}/` : '/';
}

function brandInnerHtml(sub) {
  return [
    `<a href="${homeHref()}" class="sidebar-brand-link" aria-label="PLI Reporta — página inicial">`,
    '<div class="sidebar-brand-head">',
    `<span class="sidebar-brand-mark" aria-hidden="true">${PLI_MARK_SVG}</span>`,
    '<span class="sidebar-brand-name">PLI – REPORTA</span>',
    '</div>',
    '</a>',
    `<p class="sidebar-brand-sub">${sub || 'Reporte cidadão de tráfego · PLI-SP'}</p>`,
  ].join('');
}

function wrapBrandHeadLink(el) {
  const head = el.querySelector('.sidebar-brand-head');
  if (!head || head.closest('.sidebar-brand-link')) return;
  const link = document.createElement('a');
  link.href = homeHref();
  link.className = 'sidebar-brand-link';
  link.setAttribute('aria-label', 'PLI Reporta — página inicial');
  head.parentNode.insertBefore(link, head);
  link.appendChild(head);
}

function readBrandSubtitle(el) {
  return el.querySelector('.sidebar-brand-sub')?.textContent?.trim()
    || el.querySelector('.sidebar-brand-text .muted')?.textContent?.trim()
    || el.querySelector('.muted')?.textContent?.trim()
    || '';
}

/** @param {ParentNode} [root] */
export function mountSidebarBrands(root = document) {
  root.querySelectorAll('.public-brand, .gestao-brand').forEach((el) => {
    if (el.dataset.brandMounted) return;
    el.dataset.brandMounted = '1';
    el.classList.add('sidebar-brand');

    if (el.querySelector('.sidebar-brand-head')) {
      wrapBrandHeadLink(el);
      return;
    }

    const sub = readBrandSubtitle(el);
    el.innerHTML = brandInnerHtml(sub);
  });
}
