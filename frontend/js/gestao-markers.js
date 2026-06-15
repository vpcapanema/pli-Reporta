/** Marcadores do mapa — ícones e formas conforme Funcionalidades do sistema. */

/** Categorias cujo arquivo de ícone é PNG (Flaticon); demais são SVG (FA 6). */
export const PNG_ICON_IDS = new Set([
  'acidente', 'alagamento', 'bloqueio_total',
  'lentidao_corredor', 'obra_grande', 'queda_arvore', 'sinalizacao_quebrada',
]);

/** Borda fixa do losango/círculo; cor do status vai no símbolo interno. */
export const MARKER_BORDER_COLOR = '#003b5a';

const CATEGORY_LABELS = {
  buraco: 'Buraco',
  alagamento: 'Alagamento',
  acidente: 'Acidente',
  incendio: 'Incêndio',
  animal_na_pista: 'Animal na pista',
  objeto_na_pista: 'Objeto na pista',
  queda_arvore: 'Queda de árvore',
  veiculo_quebrado: 'Veículo quebrado',
  bloqueio_total: 'Bloqueio total',
  obra_grande: 'Obra',
  lentidao_corredor: 'Lentidão',
  sinalizacao_quebrada: 'Sinalização',
  outro: 'Outro',
  elogio: 'Elogio',
  sugestao: 'Sugestão',
  reclamacao: 'Reclamação',
};

/** Cores do símbolo interno — tons escuros, saturados, 0% de transparência. */
export const STATUS_COLORS = {
  submetido: '#475569',
  em_moderacao: '#c2410c',
  validado: '#1d4ed8',
  publicado: '#15803d',
  descartado: '#b91c1c',
  registro_municipal: '#0369a1',
  expirado: '#334155',
  resolvido: '#7e22ce',
};

export function categoryIconUrl(id) {
  if (!id) return '/static/img/icons/outro.svg';
  const ext = PNG_ICON_IDS.has(id) ? 'png' : 'svg';
  return `/static/img/icons/${id}.${ext}`;
}

export function categoryLabel(category, catalog) {
  const all = [
    ...(catalog?.event_categories || []),
    ...(catalog?.manifestation_categories || []),
  ];
  const hit = all.find((c) => c.id === category);
  return hit?.label || CATEGORY_LABELS[category] || category || '—';
}

export function categorySigla(category, catalog) {
  const all = [
    ...(catalog?.event_categories || []),
    ...(catalog?.manifestation_categories || []),
  ];
  const hit = all.find((c) => c.id === category);
  return hit?.sigla || category?.slice(0, 2).toUpperCase() || '?';
}

export function resolveStatusColor(props, catalog) {
  const p = props || {};
  return STATUS_COLORS[p.status] || catalog?.statuses?.[p.status]?.cor || STATUS_COLORS.publicado;
}

/** Aplica máscara diretamente (CSS variables em mask-image falham no Leaflet). */
export function applyColoredIconMask(el, url, statusColor) {
  el.className = 'gestao-marker-icon-colored';
  el.style.backgroundColor = statusColor;
  el.style.opacity = '1';
  const mask = `url("${url}")`;
  el.style.webkitMaskImage = mask;
  el.style.maskImage = mask;
  el.style.webkitMaskSize = 'contain';
  el.style.maskSize = 'contain';
  el.style.webkitMaskRepeat = 'no-repeat';
  el.style.maskRepeat = 'no-repeat';
  el.style.webkitMaskPosition = 'center';
  el.style.maskPosition = 'center';
}

/**
 * Elemento DOM do marcador (losango + ícone para eventos; círculo + sigla para manifestações).
 * @param {{ wrapForMaplibre?: boolean }} [opts] — MapLibre sobrescreve transform no nó raiz; use wrapper.
 */
export function createMarkerElement(props, catalog, opts = {}) {
  const p = props || {};
  const isEvent = p.interaction_type !== 'manifestacao';
  const statusColor = resolveStatusColor(p, catalog);

  const root = document.createElement('div');
  root.className = `gestao-marker ${isEvent ? 'gestao-marker-diamond' : 'gestao-marker-circle'}`;
  root.style.borderColor = MARKER_BORDER_COLOR;

  const inner = document.createElement('span');
  inner.className = 'gestao-marker-inner';

  if (isEvent) {
    const url = categoryIconUrl(p.category || 'outro');
    const icon = document.createElement('span');
    applyColoredIconMask(icon, url, statusColor);
    icon.addEventListener('error', () => {}, { once: true });
    inner.appendChild(icon);
  } else {
    const sigla = document.createElement('span');
    sigla.className = 'gestao-marker-fallback';
    sigla.style.color = statusColor;
    sigla.style.opacity = '1';
    sigla.textContent = categorySigla(p.category, catalog);
    inner.appendChild(sigla);
  }

  root.appendChild(inner);

  if (opts.wrapForMaplibre) {
    const host = document.createElement('div');
    host.className = 'gestao-marker-host';
    host.appendChild(root);
    return host;
  }
  return root;
}

/** Quadrado colorido para legenda de status. */
export function legendStatusSwatch(color) {
  return `<span class="gestao-legend-swatch" style="background-color:${color}" aria-hidden="true"></span>`;
}

/** Símbolos de tipo + subtítulo da relação cor/status (legenda dos mapas). */
export function buildLegendSymbolsBlock() {
  return `
    <div class="gestao-legend-symbols">
      <p class="gestao-legend-symbol-row">
        <span class="gestao-legend-shape gestao-legend-diamond" aria-hidden="true"></span>
        <strong>Eventos de Tráfego</strong>
      </p>
      <p class="gestao-legend-symbol-row">
        <span class="gestao-legend-shape gestao-legend-circle" aria-hidden="true"></span>
        <strong>Manifestação cidadã</strong>
      </p>
    </div>
    <p class="gestao-legend-subtitle">Relação cor/símbolo:</p>`;
}

/** Pré-carrega um ícone; devolve Promise resolvida ao terminar. */
export function loadIconAsset(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(true);
    img.onerror = () => resolve(false);
    img.src = url;
  });
}

/** Pré-carrega todos os ícones de eventos. */
export async function preloadEventIcons(catalog) {
  const ids = (catalog?.event_categories || []).map((c) => c.id);
  if (!ids.length) {
    ids.push(...Object.keys(CATEGORY_LABELS).filter((k) => !['elogio', 'sugestao', 'reclamacao'].includes(k)));
  }
  const urls = [...new Set(ids.map(categoryIconUrl))];
  await Promise.all(urls.map(loadIconAsset));
}

/** Preview estático (página Funcionalidades). */
export function markerPreview({ shape, sigla, color, id }) {
  const shapeClass = shape === 'diamond' ? 'gestao-marker-diamond' : 'gestao-marker-circle';
  const host = document.createElement('div');
  host.className = `gestao-marker ${shapeClass}`;
  host.style.borderColor = MARKER_BORDER_COLOR;
  const inner = document.createElement('span');
  inner.className = 'gestao-marker-inner';
  if (id) {
    const icon = document.createElement('span');
    applyColoredIconMask(icon, categoryIconUrl(id), color || MARKER_BORDER_COLOR);
    inner.appendChild(icon);
  } else {
    const s = document.createElement('span');
    s.className = 'gestao-marker-fallback';
    s.style.color = color || MARKER_BORDER_COLOR;
    s.textContent = sigla || '';
    inner.appendChild(s);
  }
  host.appendChild(inner);
  return host.outerHTML;
}
