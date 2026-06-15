/** Documentação interativa da API pública — preenche URLs a partir do manifesto. */
import { bindSidebarCollapse, mountPublicNavSecondary } from './public-sidebar.js';
import { mountSidebarBrands } from './sidebar-brand.js';

function $(sel) {
  return document.querySelector(sel);
}

function setCode(el, text) {
  if (!el) return;
  const code = el.querySelector('code') || el;
  code.textContent = text;
}

async function loadManifest() {
  const origin = location.origin;
  const base = `${origin}/api/public`;
  const baseEl = $('#api-base-url');
  if (baseEl) baseEl.textContent = base;

  setCode($('#code-all-events'), `GET ${base}/eventos-trafego.geojson`);
  setCode($('#code-manifest'), `GET ${base}/`);
  setCode(
    $('#code-bbox-example'),
    `GET ${base}/eventos-trafego/buraco.geojson?bbox=-47.0,-23.0,-46.5,-22.5&min_priority=0.3`,
  );
  setCode(
    $('#code-curl'),
    `curl -s "${base}/eventos-trafego.geojson" -H "Accept: application/json"`,
  );
  setCode(
    $('#code-fetch'),
    `const res = await fetch('${base}/eventos-trafego.geojson');\nconst geojson = await res.json();\nconsole.log(geojson.features.length, 'eventos');`,
  );

  const tryAll = $('#link-try-all');
  if (tryAll) tryAll.href = `${base}/eventos-trafego.geojson`;

  try {
    const res = await fetch(`${base}/`);
    if (!res.ok) throw new Error(`manifest ${res.status}`);
    const data = await res.json();

    const statuses = (data.statuses_incluidos || [])
      .map((s) => s.label)
      .join(', ');
    const stEl = $('#api-statuses');
    if (stEl && statuses) stEl.textContent = statuses;

    const tbody = $('#api-layers-body');
    if (tbody && Array.isArray(data.layers)) {
      tbody.innerHTML = data.layers.map((layer) => `
        <tr>
          <td>${layer.label}</td>
          <td><code>${layer.category_id}</code></td>
          <td><a href="${layer.geojson_url}" target="_blank" rel="noopener">${layer.geojson_url.replace(origin, '')}</a></td>
        </tr>`).join('');
    }

  } catch (e) {
    console.warn('Manifesto da API indisponível', e);
    const warn = $('#api-manifest-warn');
    if (warn) warn.hidden = false;
    const tbody = $('#api-layers-body');
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="3" class="muted">Manifesto indisponível — reinicie o backend.</td></tr>';
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  mountSidebarBrands();
  bindSidebarCollapse('panel-api-publica', { defaultExpanded: true });
  mountPublicNavSecondary('#public-sidebar-nav', 'api');
  loadManifest();
});
