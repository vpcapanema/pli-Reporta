/** Marca PLI Reporta nas sidebars — pin interno + título em duas linhas. */

export const PLI_MARK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 32" focusable="false" aria-hidden="true"><path fill="currentColor" d="M12 0C6.48 0 2 4.48 2 10c0 7 10 18 10 18s10-11 10-18C22 4.48 17.52 0 12 0zm0 14a4 4 0 1 1 0-8 4 4 0 0 1 0 8z"/></svg>';

function brandInnerHtml(sub) {
  return [
    '<a href="/" class="sidebar-brand-link" aria-label="PLI Reporta — página inicial">',
    '<div class="sidebar-brand-head">',
    `<span class="sidebar-brand-mark" aria-hidden="true">${PLI_MARK_SVG}</span>`,
    '<div class="sidebar-brand-titles">',
    '<span class="sidebar-brand-pli">PLI</span>',
    '<span class="sidebar-brand-reporta">Reporta</span>',
    '</div>',
    '</div>',
    '</a>',
    sub ? `<span class="sidebar-brand-sub muted">${sub}</span>` : '',
  ].join('');
}

function wrapBrandHeadLink(el) {
  const head = el.querySelector('.sidebar-brand-head');
  if (!head || head.closest('.sidebar-brand-link')) return;
  const link = document.createElement('a');
  link.href = '/';
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
