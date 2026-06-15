/** Documentação interativa da API pública — preenche URLs a partir do manifesto. */
import {
  PUBLIC_DER_POPUP_FIELD_LABELS,
  PUBLIC_SYSTEM_POPUP_FIELD_LABELS,
} from './layer-popup-fields.js';
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

/** Mapeamento rótulo popup → propriedade GeoJSON (documentação para integradores). */
const POPUP_FIELD_GEOJSON = {
  'Tipo de interação': 'interaction_type (+ rótulo fixo “Evento de tráfego”)',
  Categoria: 'category_label ou category',
  Magnitude: 'magnitude',
  Descrição: 'description',
  Status: 'status_label ou status',
  Bloqueante: 'blocking',
  'Válido desde': 'valid_from',
  'Válido até': 'valid_to',
  'Capturado em': 'captured_at',
  'Recebido em': 'received_at',
  'Acurácia GPS (m)': 'accuracy_m',
  'Classificação viária': 'road_context.scope / road_scope → “Provavelmente municipal” se municipal',
  Rodovia: 'road_context.rodovia + denominacao',
  'Tipo rodoviário': 'road_context.tipo_rodoviario',
  Município: 'road_context.municipio',
  'Tipo de pista': 'road_context.tipo_pista',
  'Administrador da via': 'road_context.administra',
  'Coordenadoria Regional Geral DER': 'road_context.cod_regional',
  'Sede da coordenadoria': 'road_context.sede_regional',
  'Residência de conserva DER': 'road_context.residencia',
  'Sede da residência de conserva': 'road_context.sede_residencia',
};

const POPUP_STATUS_COPY = [
  {
    status: 'publicado',
    headline: 'Situação ativa',
    detail:
      'Evento confirmado e exibido neste mapa. A autoridade responsável foi informada.',
  },
  {
    status: 'resolvido',
    headline: 'Situação encerrada',
    detail:
      'Este registro foi encerrado pela autoridade competente e permanece aqui como histórico.',
  },
];

function renderPopupFieldTable(tbodyId, labels) {
  const tbody = $(tbodyId);
  if (!tbody) return;
  tbody.innerHTML = labels
    .map(
      (label, i) => `
        <tr>
          <td>${i + 1}</td>
          <td>${label}</td>
          <td><code>${POPUP_FIELD_GEOJSON[label] || 'road_context / road_label'}</code></td>
        </tr>`,
    )
    .join('');
}

function renderPopupStatusTable() {
  const tbody = $('#api-popup-status-body');
  if (!tbody) return;
  tbody.innerHTML = POPUP_STATUS_COPY.map(
    (row) => `
        <tr>
          <td><code>${row.status}</code></td>
          <td>${row.headline}</td>
          <td class="muted">${row.detail}</td>
        </tr>`,
  ).join('');
}

function renderPopupSpec() {
  renderPopupStatusTable();
  renderPopupFieldTable('#api-popup-cadastro-body', PUBLIC_SYSTEM_POPUP_FIELD_LABELS);
  renderPopupFieldTable('#api-popup-rodoviario-body', PUBLIC_DER_POPUP_FIELD_LABELS);
}

function renderStatusLegend(items) {
  const legendBody = $('#api-status-legend-body');
  if (!legendBody || !items?.length) return;
  legendBody.innerHTML = items.map((item) => {
    const inApi = item.export_publico === true;
    const rowClass = inApi ? ' class="api-publica-legend-public"' : '';
    const badge = inApi
      ? '<span class="api-publica-legend-yes">Sim</span>'
      : '<span class="api-publica-legend-no">Não</span>';
    const desc = item.descricao || '—';
    return `
        <tr${rowClass}>
          <td>
            <span class="api-publica-swatch" style="background-color:${item.symbol_color}" title="${item.symbol_color}"></span>
            <code>${item.symbol_color}</code>
          </td>
          <td><code>${item.status}</code></td>
          <td>${item.label}</td>
          <td class="muted">${desc}</td>
          <td>${badge}</td>
        </tr>`;
  }).join('');
}

/** Fallback estático (mesmo STATUS_META do backend) se o manifesto falhar. */
const STATUS_LEGEND_FALLBACK = [
  { status: 'submetido', label: 'Recém-chegado', symbol_color: '#475569', descricao: 'Ainda em processamento inicial', export_publico: false },
  { status: 'em_moderacao', label: 'Precisa da sua análise', symbol_color: '#c2410c', descricao: 'O sistema preferiu não decidir sozinho', export_publico: false },
  { status: 'validado', label: 'Aprovado internamente', symbol_color: '#1d4ed8', descricao: 'Validado, aguardando publicação no mapa público', export_publico: false },
  { status: 'publicado', label: 'Publicado', symbol_color: '#15803d', descricao: 'Visível no mapa público', export_publico: true },
  { status: 'descartado', label: 'Arquivado', symbol_color: '#b91c1c', descricao: 'Não será exibido publicamente', export_publico: false },
  { status: 'registro_municipal', label: 'Registro municipal', symbol_color: '#0369a1', descricao: 'Armazenado internamente para relatórios', export_publico: false },
  { status: 'expirado', label: 'Expirado', symbol_color: '#334155', descricao: 'Perdeu validade temporal', export_publico: false },
  { status: 'resolvido', label: 'Resolvido', symbol_color: '#7e22ce', descricao: 'Encerrado pela autoridade', export_publico: true },
];

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

    const symBody = $('#api-symbology-body');
    const categories = data.simbologia?.categories || data.layers || [];
    if (symBody && categories.length) {
      symBody.innerHTML = categories.map((cat) => `
        <tr>
          <td>${cat.label}</td>
          <td><img src="${cat.icon_url || cat.icon_path}" alt="" width="28" height="28" loading="lazy"/></td>
          <td><code>${cat.icon_format || 'svg'}</code></td>
        </tr>`).join('');
    }

    const legendItems =
      data.simbologia?.legenda_status?.todos_status ||
      data.simbologia?.legenda_status?.mapa_publico ||
      [];
    renderStatusLegend(legendItems);

  } catch (e) {
    console.warn('Manifesto da API indisponível', e);
    const warn = $('#api-manifest-warn');
    if (warn) warn.hidden = false;
    const tbody = $('#api-layers-body');
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="3" class="muted">Manifesto indisponível — reinicie o backend.</td></tr>';
    }
    renderStatusLegend(STATUS_LEGEND_FALLBACK);
    const symBody = $('#api-symbology-body');
    if (symBody) {
      symBody.innerHTML = '<tr><td colspan="3" class="muted">Simbologia indisponível offline.</td></tr>';
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  mountSidebarBrands();
  bindSidebarCollapse('panel-api-publica', { defaultExpanded: true });
  mountPublicNavSecondary('#public-sidebar-nav', 'api');
  renderPopupSpec();
  loadManifest();
});
