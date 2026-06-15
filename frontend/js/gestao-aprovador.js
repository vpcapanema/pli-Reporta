/** Aprovador automático — todos os parâmetros do serviço. */
import {
  fetchModerationPolicy,
  simulateModerationPolicy,
  updateModerationPolicy,
} from './api.js';
import {
  $,
  bindLogout,
  handleAuthError,
  renderSidebar,
  requireAuth,
} from './gestao-common.js';

/* ── Critérios de pontuação por sinal (espelham veracity.py) ─────────── */
const SIGNAL_CRITERIA = {
  geo_browser: [
    { score: '100 pts', tier: 'high', condition: 'Localização muito precisa — o app conseguiu um GPS com menos de 50 metros de margem.' },
    { score:  '50 pts', tier: 'mid',  condition: 'Localização razoável — GPS entre 50 e 200 metros de margem. Aceitável, mas não ideal.' },
    { score:  '40 pts', tier: 'mid',  condition: 'O navegador não informou a margem de erro do GPS. Pontuação neutra.' },
    { score:  '10 pts', tier: 'low',  condition: 'Localização muito imprecisa — GPS com mais de 200 metros de margem.' },
    { score:   '0 pts', tier: 'zero', condition: 'Coordenadas impossíveis — o sistema não conseguiu nem identificar onde o reporte foi feito.' },
  ],
  exif_match: [
    { score: '100 pts', tier: 'high', condition: 'A foto e o reporte contam a mesma história: o lugar bate (menos de 100 m de diferença) e o horário também (menos de 5 minutos).' },
    { score:  '50 pts', tier: 'mid',  condition: 'Lugar ou horário batem, mas não os dois ao mesmo tempo. Sinal parcial.' },
    { score:  '50 pts', tier: 'mid',  condition: 'A foto não tem localização nos metadados — comum em câmeras sem GPS. O sistema não penaliza.' },
    { score:  '10 pts', tier: 'low',  condition: 'Nem o lugar nem o horário dos metadados batem com o reporte. Alta chance de foto reciclada.' },
  ],
  capture_inapp: [
    { score: '100 pts', tier: 'high', condition: 'Foto tirada na hora, dentro do próprio app. O sistema confirma que foi captura ao vivo.' },
    { score:  '40 pts', tier: 'low',  condition: 'Foto enviada da galeria — pode ter sido tirada bem antes do evento acontecer.' },
  ],
  road_snap: [
    { score: '100 pts', tier: 'high', condition: 'O ponto do reporte está praticamente em cima de uma via cadastrada (menos de 30 m).' },
    { score:  '70 pts', tier: 'mid',  condition: 'A base de malha viária não está ativa no servidor — pontuação neutra aplicada.' },
    { score:  '60 pts', tier: 'mid',  condition: 'Perto de uma via, mas não exatamente em cima (entre 30 e 100 m). Provavelmente ok.' },
    { score:  '30 pts', tier: 'low',  condition: 'Distante da via mais próxima (entre 100 e 200 m). Localização duvidosa.' },
    { score:   '0 pts', tier: 'zero', condition: 'Mais de 200 m de qualquer via — provável engano de localização ou reporte fora de contexto.' },
  ],
  image_integrity: [
    { score:  '90 pts', tier: 'high', condition: 'A foto foi processada por algum software, mas não é nenhum editor de imagem suspeito.' },
    { score:  '85 pts', tier: 'high', condition: 'Foto bruta, sem marcas de nenhum software. Tudo certo.' },
    { score:   '0 pts', tier: 'zero', condition: 'Editor de imagem detectado nos metadados: Photoshop, GIMP, Lightroom, Snapseed, FaceTune ou PicsArt.' },
  ],
  user_reputation: [
    { score: '0–100 pts', tier: 'high', condition: 'Pontuação baseada no histórico do cidadão: quantas vezes ele reportou algo que realmente era verdadeiro. Usuário novo ou anônimo começa em 0.' },
  ],
  temporal_plausibility: [
    { score: '100 pts', tier: 'high', condition: 'Foto tirada há menos de 30 minutos — reporte fresquinho, muito confiável.' },
    { score: '100 pts', tier: 'high', condition: 'Modo offline: foto tirada há menos de 24 horas antes do envio.' },
    { score:  '70 pts', tier: 'mid',  condition: 'Modo offline: foto tirada há menos de 48 horas. Ainda dentro do prazo aceitável.' },
    { score:  '60 pts', tier: 'mid',  condition: 'Foto tirada há menos de 2 horas. Razoavelmente recente.' },
    { score:  '40 pts', tier: 'mid',  condition: 'Foto tirada há menos de 24 horas. Pode ainda ser válido dependendo da categoria.' },
    { score:  '30 pts', tier: 'low',  condition: 'Modo offline: foto com mais de 48 horas. Muito antiga para ser confiável.' },
    { score:  '20 pts', tier: 'low',  condition: 'Foto tirada há mais de 24 horas. O evento pode já ter se resolvido.' },
    { score:  '20 pts', tier: 'low',  condition: 'A data da foto está no futuro — provavelmente o relógio do celular está errado.' },
    { score:  '30 pts', tier: 'low',  condition: 'Não foi possível identificar quando a foto foi tirada.' },
  ],
};

/* ── Utilidades ──────────────────────────────────────────────────────── */
const BLOCKING_IDS = new Set(['bloqueio_total', 'alagamento', 'incendio']);

/** Valores padrão (preset equilibrado) — espelham moderation_policy.py / relevance.py */
const DEFAULT_GLOBAL = {
  event_publish_min: 70,
  event_discard_below: 30,
  manif_publish_min: 75,
  manif_discard_below: 40,
  always_review_blocking: true,
  always_review_offline: true,
  always_review_first_in_area: false,
  always_review_other: true,
};

const DEFAULT_SIGNALS = [
  { id: 'geo_browser', label: 'Precisão GPS', descricao: 'Precisão do GPS declarado pelo navegador/app', peso: 20 },
  { id: 'exif_match', label: 'Coerência EXIF', descricao: 'Coerência entre GPS e timestamp da foto (EXIF) com o reporte', peso: 15 },
  { id: 'capture_inapp', label: 'Captura in-app', descricao: 'Foto capturada dentro do app vs. enviada da galeria', peso: 20 },
  { id: 'road_snap', label: 'Snap à via', descricao: 'Proximidade do ponto reportado a uma via conhecida', peso: 10 },
  { id: 'image_integrity', label: 'Integridade da imagem', descricao: 'Ausência de sinais de edição por software', peso: 15 },
  { id: 'user_reputation', label: 'Reputação do usuário', descricao: 'Histórico de acertos/erros anteriores do usuário', peso: 10 },
  { id: 'temporal_plausibility', label: 'Atualidade da captura', descricao: 'Frescor da captura — foto muito antiga reduz confiabilidade', peso: 10 },
];

const DEFAULT_EVENT_CATS = [
  { id: 'bloqueio_total', label: 'Bloqueio total', severidade_base: 100, ttl_horas: 6, sempre_revisar: true, limiar_publicar: null, limiar_descartar: null },
  { id: 'incendio', label: 'Incêndio', severidade_base: 95, ttl_horas: 4, sempre_revisar: true, limiar_publicar: null, limiar_descartar: null },
  { id: 'acidente', label: 'Acidente', severidade_base: 85, ttl_horas: 2, sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'alagamento', label: 'Alagamento', severidade_base: 85, ttl_horas: 12, sempre_revisar: true, limiar_publicar: null, limiar_descartar: null },
  { id: 'queda_arvore', label: 'Queda de árvore', severidade_base: 75, ttl_horas: 24, sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'animal_na_pista', label: 'Animal na pista', severidade_base: 70, ttl_horas: 3, sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'obra_grande', label: 'Obra na pista', severidade_base: 70, ttl_horas: 720, sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'objeto_na_pista', label: 'Objeto na pista', severidade_base: 65, ttl_horas: 6, sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'lentidao_corredor', label: 'Lentidão no corredor', severidade_base: 65, ttl_horas: 1, sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'veiculo_quebrado', label: 'Veículo quebrado', severidade_base: 55, ttl_horas: 3, sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'sinalizacao_quebrada', label: 'Sinalização quebrada', severidade_base: 50, ttl_horas: 336, sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'buraco', label: 'Buraco', severidade_base: 40, ttl_horas: 2160, sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'outro', label: 'Outro', severidade_base: 30, ttl_horas: 168, sempre_revisar: true, limiar_publicar: null, limiar_descartar: null },
];

const DEFAULT_MANIF_CATS = [
  { id: 'elogio', label: 'Elogio', sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'sugestao', label: 'Sugestão', sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
  { id: 'reclamacao', label: 'Reclamação', sempre_revisar: false, limiar_publicar: null, limiar_descartar: null },
];

const DEFAULT_HIGHWAY = [
  { id: 'motorway', label: 'Rodovia principal (faixa dupla)', fator: 100 },
  { id: 'motorway_link', label: 'Acesso de rodovia principal', fator: 100 },
  { id: 'trunk', label: 'Rodovia de acesso / contorno', fator: 100 },
  { id: 'trunk_link', label: 'Acesso de rodovia de contorno', fator: 100 },
  { id: 'primary', label: 'Avenida / via primária', fator: 85 },
  { id: 'primary_link', label: 'Acesso de via primária', fator: 85 },
  { id: 'secondary', label: 'Via secundária', fator: 70 },
  { id: 'secondary_link', label: 'Acesso de via secundária', fator: 70 },
  { id: 'tertiary', label: 'Via terciária', fator: 55 },
  { id: 'tertiary_link', label: 'Acesso de via terciária', fator: 55 },
  { id: 'residential', label: 'Via residencial', fator: 35 },
  { id: 'unclassified', label: 'Via sem classificação', fator: 35 },
  { id: 'service', label: 'Via de serviço', fator: 15 },
  { id: 'track', label: 'Estrada de terra / trilha', fator: 15 },
];

let thresholdRangesBound = false;

/** Extrai limiar numérico (0–100) de formatos legado e novo. */
function pickThreshold(value, fallback) {
  if (value == null || value === '') return fallback;
  if (typeof value === 'number' && Number.isFinite(value)) {
    if (value > 0 && value <= 1) return Math.round(value * 100);
    return Math.round(value);
  }
  if (typeof value === 'object') {
    if (typeof value.valor === 'number') return Math.round(value.valor);
  }
  return fallback;
}

function buildDefaultPolicy() {
  return {
    preset: 'equilibrado',
    global: { ...DEFAULT_GLOBAL },
    sinais_veracidade: DEFAULT_SIGNALS.map((s) => ({ ...s })),
    fatores_via: DEFAULT_HIGHWAY.map((h) => ({ ...h })),
    categorias_evento: DEFAULT_EVENT_CATS.map((c) => ({ ...c })),
    categorias_manif: DEFAULT_MANIF_CATS.map((c) => ({ ...c })),
  };
}

/** Garante formato completo mesmo com resposta legada ou parcial da API. */
function normalizePolicy(raw) {
  const base = buildDefaultPolicy();
  if (!raw || typeof raw !== 'object') return base;

  const legacyGlobal = {};
  if (!raw.global && (raw.eventos || raw.manifestacoes)) {
    const ev = raw.eventos || {};
    const mn = raw.manifestacoes || {};
    Object.assign(legacyGlobal, {
      event_publish_min: pickThreshold(ev.publicar_sozinho, undefined),
      event_discard_below: pickThreshold(ev.arquivar_sozinho, undefined),
      manif_publish_min: pickThreshold(mn.publicar_sozinho, undefined),
      manif_discard_below: pickThreshold(mn.arquivar_sozinho, undefined),
      always_review_blocking: ev.revisar_bloqueios,
      always_review_offline: ev.revisar_offline,
      always_review_first_in_area: ev.revisar_primeiro_na_area,
      always_review_other: ev.revisar_outro,
    });
    const sr = ev.sempre_revisar;
    if (sr && typeof sr === 'object' && !Array.isArray(sr)) {
      if ('bloqueio_alagamento' in sr) legacyGlobal.always_review_blocking = !!sr.bloqueio_alagamento;
      if ('envio_offline' in sr) legacyGlobal.always_review_offline = !!sr.envio_offline;
      if ('primeiro_na_regiao' in sr) legacyGlobal.always_review_first_in_area = !!sr.primeiro_na_regiao;
      if ('categoria_outro' in sr) legacyGlobal.always_review_other = !!sr.categoria_outro;
    }
  }

  const fromApi = raw.global || {};
  const cleanedApi = Object.fromEntries(
    Object.entries(fromApi).filter(([, v]) => v != null && v !== ''),
  );
  const cleanedLegacy = Object.fromEntries(
    Object.entries(legacyGlobal).filter(([, v]) => v != null && v !== ''),
  );
  const globalCfg = { ...base.global, ...cleanedLegacy, ...cleanedApi };
  for (const key of Object.keys(globalCfg)) {
    if (key.includes('_min') || key.includes('_below')) {
      globalCfg[key] = pickThreshold(globalCfg[key], base.global[key]);
    }
  }

  return {
    ...base,
    ...raw,
    global: globalCfg,
    sinais_veracidade: raw.sinais_veracidade?.length ? raw.sinais_veracidade : base.sinais_veracidade,
    fatores_via: raw.fatores_via?.length ? raw.fatores_via : base.fatores_via,
    categorias_evento: raw.categorias_evento?.length ? raw.categorias_evento : base.categorias_evento,
    categorias_manif: raw.categorias_manif?.length ? raw.categorias_manif : base.categorias_manif,
  };
}

const RELEVANCE_FIXED = [
  {
    title: 'R_confirmação',
    formula: 'R_conf = 0,5 + 0,5 × (1 − e^(−0,6 × n))',
    detail: 'n = confirmações no cluster (outros cidadãos no mesmo ponto). Mais confirmações → relevância sobe.',
  },
  {
    title: 'R_persistência',
    formula: 'R_pers = e^(−idade_horas / TTL_categoria)',
    detail: 'TTL configurável por categoria na tabela 4a. Reportes antigos perdem relevância até expirar.',
  },
  {
    title: 'Magnitude do evento',
    formula: 'R_sev × fator: leve 70% · normal 100% · grave 120%',
    detail: 'Escolhida pelo cidadão no envio. Multiplica a severidade base da categoria.',
  },
  {
    title: 'Prioridade no mapa',
    formula: 'P = V × R',
    detail: 'Usada para ordenar eventos e decidir destaque. Não substitui os limiares de V para publicação.',
  },
];

function bindTabs() {
  const tabs = document.querySelectorAll('.policy-type-tab');
  const panels = {
    eventos: $('#panel-eventos'),
    manifestacoes: $('#panel-manifestacoes'),
  };
  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const id = tab.dataset.tab;
      tabs.forEach((t) => {
        const on = t === tab;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      Object.entries(panels).forEach(([key, panel]) => {
        if (!panel) return;
        panel.hidden = key !== id;
      });
    });
  });
}

/** Sincroniza slider ↔ input numérico. */
function bindRangePair(rangeId, numId, onChange) {
  const range = $(rangeId);
  const num = $(numId);
  if (!range || !num) return;
  const sync = (fromRange) => {
    if (fromRange) num.value = range.value;
    else range.value = num.value;
    onChange?.();
  };
  range.addEventListener('input', () => sync(true));
  num.addEventListener('input', () => sync(false));
  sync(true);
}

function bindThresholdRanges(onGlobalChange) {
  bindRangePair('#g-event-pub-range', '#g-event-pub', onGlobalChange);
  bindRangePair('#g-event-disc-range', '#g-event-disc', onGlobalChange);
  bindRangePair('#g-manif-pub-range', '#g-manif-pub', onGlobalChange);
  bindRangePair('#g-manif-disc-range', '#g-manif-disc', onGlobalChange);
}

function renderRelevanceFixed() {
  const box = $('#relevance-fixed-params');
  if (!box) return;
  box.innerHTML = RELEVANCE_FIXED.map((p) => `
    <article class="gestao-slider-block">
      <strong>${p.title}</strong>
      <code>${p.formula}</code>
      <p class="muted">${p.detail}</p>
    </article>
  `).join('');
}

function ttlHuman(h) {
  if (!h || h < 1) return '';
  if (h < 24)       return `${h} h`;
  const d = h / 24;
  if (d < 2)        return '1 dia';
  if (d < 30)       return `${Math.round(d)} dias`;
  if (d < 60)       return '1 mês';
  const m = Math.round(d / 30);
  if (m < 24)       return `${m} meses`;
  return `${Math.round(d / 365)} ano(s)`;
}

/* ── Seção 1: Limiares de decisão ────────────────────────────────────── */
function updateGlobalLabels(g) {
  const ep = $('#lbl-event-pub');
  if (ep) ep.textContent = `Padrão: ${g.event_publish_min} pts`;
  const ed = $('#lbl-event-disc');
  if (ed) ed.textContent = `Padrão: ${g.event_discard_below} pts`;
  const mp = $('#lbl-manif-pub');
  if (mp) mp.textContent = `Padrão: ${g.manif_publish_min} pts`;
  const md = $('#lbl-manif-disc');
  if (md) md.textContent = `Padrão: ${g.manif_discard_below} pts`;
}

function renderGlobal(g) {
  const cfg = { ...DEFAULT_GLOBAL, ...(g || {}) };
  const setPair = (rangeId, numId, val, fallback) => {
    const n = pickThreshold(val, fallback);
    const num = $(numId);
    const range = $(rangeId);
    if (num) num.value = n;
    if (range) range.value = n;
  };

  setPair('#g-event-pub-range', '#g-event-pub', cfg.event_publish_min, DEFAULT_GLOBAL.event_publish_min);
  setPair('#g-event-disc-range', '#g-event-disc', cfg.event_discard_below, DEFAULT_GLOBAL.event_discard_below);
  setPair('#g-manif-pub-range', '#g-manif-pub', cfg.manif_publish_min, DEFAULT_GLOBAL.manif_publish_min);
  setPair('#g-manif-disc-range', '#g-manif-disc', cfg.manif_discard_below, DEFAULT_GLOBAL.manif_discard_below);

  const blocking = $('#g-blocking');
  const offline = $('#g-offline');
  const firstArea = $('#g-first-area');
  const other = $('#g-other');
  if (blocking) blocking.checked = !!cfg.always_review_blocking;
  if (offline) offline.checked = !!cfg.always_review_offline;
  if (firstArea) firstArea.checked = !!cfg.always_review_first_in_area;
  if (other) other.checked = !!cfg.always_review_other;

  updateGlobalLabels(cfg);
}

/* ── Seção 2: Sinais de veracidade ───────────────────────────────────── */
function _criteriaRows(signalId) {
  const items = SIGNAL_CRITERIA[signalId] || [];
  if (!items.length) return '';
  const rows = items.map((c) =>
    `<li class="sc-item">
      <span class="sc-score sc-${c.tier}">${c.score}</span>
      <span class="sc-cond">${c.condition}</span>
    </li>`,
  ).join('');
  return `
    <details class="signal-criteria">
      <summary class="sc-toggle">Como o sistema calcula essa nota</summary>
      <ul class="sc-list">${rows}</ul>
    </details>`;
}

function renderSignals(sinais) {
  const tbody = $('#tbody-signals');
  if (!tbody) return;
  if (!sinais?.length) sinais = DEFAULT_SIGNALS;

  const total = sinais.reduce((s, x) => s + (x.peso || 0), 0);
  const lbl = $('#lbl-weight-total');
  if (lbl) lbl.textContent = `(total: ${total.toFixed(1)}%)`;

  tbody.innerHTML = sinais.map((s) => `
    <tr data-signal-id="${s.id}">
      <td class="col-signal">
        <span class="policy-cat-label">${s.label}</span>
        <code class="policy-cat-id">${s.id}</code>
      </td>
      <td class="col-signal-desc">
        <span class="muted">${s.descricao}</span>
        ${_criteriaRows(s.id)}
      </td>
      <td class="col-weight">
        <div class="thresh-cell">
          <input type="range" class="policy-weight-range" data-field="peso-range"
                 min="0" max="100" step="0.5" value="${s.peso}"
                 aria-label="Peso ${s.label}"/>
          <input type="number" class="policy-num-input"
                 data-field="peso" min="0" max="100" step="0.1"
                 value="${s.peso}"/>
          <span class="policy-num-unit">%</span>
          <div class="weight-bar-wrap" title="${s.peso}%">
            <div class="weight-bar" style="width:${Math.min(s.peso, 100)}%"></div>
          </div>
        </div>
      </td>
    </tr>`).join('');

  // Atualiza total e sincroniza sliders ao digitar
  tbody.querySelectorAll('[data-field="peso"]').forEach((el) => {
    const row = el.closest('tr');
    const range = row?.querySelector('[data-field="peso-range"]');
    const update = () => {
      const all = Array.from(tbody.querySelectorAll('[data-field="peso"]'));
      const sum = all.reduce((acc, i) => acc + (parseFloat(i.value) || 0), 0);
      if (lbl) lbl.textContent = `(total: ${sum.toFixed(1)}%)`;
      const bar = row?.querySelector('.weight-bar');
      if (bar) bar.style.width = `${Math.min(parseFloat(el.value) || 0, 100)}%`;
    };
    el.addEventListener('input', () => {
      if (range) range.value = el.value;
      update();
    });
    if (range) {
      range.addEventListener('input', () => {
        el.value = range.value;
        update();
      });
    }
  });
}

/* ── Seção 3: Eventos por categoria ──────────────────────────────────── */
function renderEventosTable(categorias, globalPub, globalDisc) {
  const tbody = $('#tbody-eventos');
  if (!tbody) return;
  if (!categorias?.length) categorias = DEFAULT_EVENT_CATS;
  const pubDefault = pickThreshold(globalPub, DEFAULT_GLOBAL.event_publish_min);
  const discDefault = pickThreshold(globalDisc, DEFAULT_GLOBAL.event_discard_below);

  tbody.innerHTML = categorias.map((cat) => {
    const pubIsGlobal  = cat.limiar_publicar  == null;
    const discIsGlobal = cat.limiar_descartar == null;
    const pubVal  = pubIsGlobal  ? pubDefault  : pickThreshold(cat.limiar_publicar, pubDefault);
    const discVal = discIsGlobal ? discDefault : pickThreshold(cat.limiar_descartar, discDefault);

    return `
      <tr data-cat-id="${cat.id}">
        <td class="col-cat">
          <span class="policy-cat-label">${cat.label}</span>
          ${BLOCKING_IDS.has(cat.id) ? '<span class="cat-badge badge-blocking">bloqueante</span>' : ''}
          <code class="policy-cat-id">${cat.id}</code>
        </td>
        <td class="col-sev">
          <div class="thresh-cell">
            <input type="number" class="policy-num-input"
                   data-field="severidade_base" min="0" max="100" step="1"
                   value="${cat.severidade_base}"/>
            <span class="policy-num-unit">%</span>
          </div>
        </td>
        <td class="col-ttl">
          <div class="ttl-cell">
            <input type="number" class="policy-num-input"
                   data-field="ttl_horas" data-is-global="false"
                   min="1" max="262800" step="1"
                   value="${cat.ttl_horas}"/>
            <span class="policy-num-unit">h</span>
            <span class="ttl-human">${ttlHuman(cat.ttl_horas)}</span>
          </div>
        </td>
        <td class="col-thresh">
          <div class="thresh-cell">
            <input type="number" class="policy-num-input${pubIsGlobal ? ' is-global' : ''}"
                   data-field="limiar_publicar" data-is-global="${pubIsGlobal}"
                   min="1" max="99" step="1" value="${pubVal}"/>
            <span class="policy-num-unit">pts</span>
            ${pubIsGlobal ? '<span class="global-badge" title="Usando padrão global (Seção 1)">G</span>' : ''}
          </div>
        </td>
        <td class="col-thresh">
          <div class="thresh-cell">
            <input type="number" class="policy-num-input${discIsGlobal ? ' is-global' : ''}"
                   data-field="limiar_descartar" data-is-global="${discIsGlobal}"
                   min="1" max="99" step="1" value="${discVal}"/>
            <span class="policy-num-unit">pts</span>
            ${discIsGlobal ? '<span class="global-badge" title="Usando padrão global (Seção 1)">G</span>' : ''}
          </div>
        </td>
        <td class="col-rev">
          <label class="policy-toggle">
            <input type="checkbox" data-field="sempre_revisar"
                   ${cat.sempre_revisar ? 'checked' : ''}/>
            <span class="toggle-track"></span>
          </label>
        </td>
      </tr>`;
  }).join('');

  _bindTableBadges(tbody);
  _bindTtlLabels(tbody);
}

/* ── Seção 4: Fatores por tipo de via ────────────────────────────────── */
function renderHighwayTable(fatores) {
  const tbody = $('#tbody-highway');
  if (!tbody) return;
  if (!fatores?.length) fatores = DEFAULT_HIGHWAY;

  tbody.innerHTML = fatores.map((hw) => `
    <tr data-hw-id="${hw.id}">
      <td class="col-highway-id"><code>${hw.id}</code></td>
      <td class="col-highway-label"><span class="muted">${hw.label}</span></td>
      <td class="col-weight">
        <div class="thresh-cell">
          <input type="range" class="policy-weight-range" data-field="fator-range"
                 min="0" max="100" step="1" value="${hw.fator}"
                 aria-label="Fator ${hw.label}"/>
          <input type="number" class="policy-num-input"
                 data-field="fator" min="0" max="100" step="1"
                 value="${hw.fator}"/>
          <span class="policy-num-unit">%</span>
          <div class="weight-bar-wrap" title="${hw.fator}%">
            <div class="weight-bar" style="width:${hw.fator}%"></div>
          </div>
        </div>
      </td>
    </tr>`).join('');

  tbody.querySelectorAll('[data-field="fator"]').forEach((el) => {
    const row = el.closest('tr');
    const range = row?.querySelector('[data-field="fator-range"]');
    const updateBar = () => {
      const bar = row?.querySelector('.weight-bar');
      if (bar) bar.style.width = `${Math.min(parseFloat(el.value) || 0, 100)}%`;
    };
    el.addEventListener('input', () => {
      if (range) range.value = el.value;
      updateBar();
    });
    if (range) {
      range.addEventListener('input', () => {
        el.value = range.value;
        updateBar();
      });
    }
  });
}

/* ── Seção 5: Manifestações ──────────────────────────────────────────── */
function renderManifTable(categorias, globalPub, globalDisc) {
  const tbody = $('#tbody-manif');
  if (!tbody) return;
  if (!categorias?.length) categorias = DEFAULT_MANIF_CATS;
  const pubDefault = pickThreshold(globalPub, DEFAULT_GLOBAL.manif_publish_min);
  const discDefault = pickThreshold(globalDisc, DEFAULT_GLOBAL.manif_discard_below);

  tbody.innerHTML = categorias.map((cat) => {
    const pubIsGlobal  = cat.limiar_publicar  == null;
    const discIsGlobal = cat.limiar_descartar == null;
    const pubVal  = pubIsGlobal  ? pubDefault  : pickThreshold(cat.limiar_publicar, pubDefault);
    const discVal = discIsGlobal ? discDefault : pickThreshold(cat.limiar_descartar, discDefault);

    return `
      <tr data-cat-id="${cat.id}">
        <td class="col-cat">
          <span class="policy-cat-label">${cat.label}</span>
          <code class="policy-cat-id">${cat.id}</code>
        </td>
        <td class="col-thresh">
          <div class="thresh-cell">
            <input type="number" class="policy-num-input${pubIsGlobal ? ' is-global' : ''}"
                   data-field="limiar_publicar" data-is-global="${pubIsGlobal}"
                   min="1" max="99" step="1" value="${pubVal}"/>
            <span class="policy-num-unit">pts</span>
            ${pubIsGlobal ? '<span class="global-badge" title="Usando padrão global (Seção 1)">G</span>' : ''}
          </div>
        </td>
        <td class="col-thresh">
          <div class="thresh-cell">
            <input type="number" class="policy-num-input${discIsGlobal ? ' is-global' : ''}"
                   data-field="limiar_descartar" data-is-global="${discIsGlobal}"
                   min="1" max="99" step="1" value="${discVal}"/>
            <span class="policy-num-unit">pts</span>
            ${discIsGlobal ? '<span class="global-badge" title="Usando padrão global (Seção 1)">G</span>' : ''}
          </div>
        </td>
        <td class="col-rev">
          <label class="policy-toggle">
            <input type="checkbox" data-field="sempre_revisar"
                   ${cat.sempre_revisar ? 'checked' : ''}/>
            <span class="toggle-track"></span>
          </label>
        </td>
      </tr>`;
  }).join('');

  _bindTableBadges(tbody);
}

/* ── Helpers de binding ──────────────────────────────────────────────── */
function _bindTableBadges(tbody) {
  tbody.querySelectorAll('input[data-is-global]').forEach((el) => {
    el.addEventListener('input', () => {
      el.dataset.isGlobal = 'false';
      el.classList.remove('is-global');
      el.closest('.thresh-cell')?.querySelector('.global-badge')?.remove();
    });
  });
}

function _bindTtlLabels(tbody) {
  tbody.querySelectorAll('[data-field="ttl_horas"]').forEach((el) => {
    el.addEventListener('input', () => {
      const lbl = el.closest('.ttl-cell')?.querySelector('.ttl-human');
      if (lbl) lbl.textContent = ttlHuman(Number(el.value) || 0);
    });
  });
}

/* ── Render completo ─────────────────────────────────────────────────── */
function renderPolicy(data) {
  const policy = normalizePolicy(data);
  renderGlobal(policy.global);
  renderSignals(policy.sinais_veracidade);
  renderHighwayTable(policy.fatores_via);
  renderEventosTable(
    policy.categorias_evento,
    policy.global.event_publish_min,
    policy.global.event_discard_below,
  );
  renderManifTable(
    policy.categorias_manif,
    policy.global.manif_publish_min,
    policy.global.manif_discard_below,
  );
  renderRelevanceFixed();

  const onGlobalChange = () => {
    updateGlobalLabels({
      event_publish_min: Number($('#g-event-pub')?.value || DEFAULT_GLOBAL.event_publish_min),
      event_discard_below: Number($('#g-event-disc')?.value || DEFAULT_GLOBAL.event_discard_below),
      manif_publish_min: Number($('#g-manif-pub')?.value || DEFAULT_GLOBAL.manif_publish_min),
      manif_discard_below: Number($('#g-manif-disc')?.value || DEFAULT_GLOBAL.manif_discard_below),
    });
  };

  if (!thresholdRangesBound) {
    bindThresholdRanges(onGlobalChange);
    thresholdRangesBound = true;
  } else {
    onGlobalChange();
  }
}

/* ── Coleta payload ──────────────────────────────────────────────────── */
function collectPayload() {
  const global_config = {
    event_publish_min:           Number($('#g-event-pub').value),
    event_discard_below:         Number($('#g-event-disc').value),
    manif_publish_min:           Number($('#g-manif-pub').value),
    manif_discard_below:         Number($('#g-manif-disc').value),
    always_review_blocking:      $('#g-blocking').checked,
    always_review_offline:       $('#g-offline').checked,
    always_review_first_in_area: $('#g-first-area').checked,
    always_review_other:         $('#g-other').checked,
  };

  // Sinais de veracidade
  const sinais_veracidade = Array.from(
    document.querySelectorAll('#tbody-signals tr[data-signal-id]'),
  ).map((tr) => ({
    id:   tr.dataset.signalId,
    peso: parseFloat(tr.querySelector('[data-field="peso"]').value) || 0,
  }));

  // Fatores de via
  const fatores_via = Array.from(
    document.querySelectorAll('#tbody-highway tr[data-hw-id]'),
  ).map((tr) => ({
    id:    tr.dataset.hwId,
    fator: parseFloat(tr.querySelector('[data-field="fator"]').value) || 0,
  }));

  return {
    global: global_config,
    sinais_veracidade,
    fatores_via,
    categorias_evento: collectTableRows('#tbody-eventos'),
    categorias_manif:  collectTableRows('#tbody-manif'),
  };
}

function collectTableRows(sel) {
  const rows = document.querySelectorAll(`${sel} tr[data-cat-id]`);
  return Array.from(rows).map((tr) => {
    const entry = { id: tr.dataset.catId };
    tr.querySelectorAll('[data-field]').forEach((el) => {
      const field = el.dataset.field;
      if (el.type === 'checkbox') {
        entry[field] = el.checked;
      } else if (el.dataset.isGlobal === 'true') {
        entry[field] = null;
      } else {
        const val = el.value.trim();
        entry[field] = val === '' ? null : Number(val);
      }
    });
    return entry;
  });
}

/* ── Salvar ──────────────────────────────────────────────────────────── */
async function savePolicy() {
  const session = requireAuth();
  if (!session) return;
  const msg = $('#policy-save-msg');
  msg.hidden = true;
  try {
    const updated = await updateModerationPolicy(session.token, collectPayload());
    renderPolicy(updated);
    msg.hidden = false;
    msg.textContent = 'Configuracao salva com sucesso.';
    msg.className = 'gestao-feedback ok';
    setTimeout(() => { msg.hidden = true; }, 4000);
  } catch (err) {
    if (handleAuthError(err)) return;
    msg.hidden = false;
    msg.textContent = 'Erro ao salvar: ' + err.message;
    msg.className = 'gestao-feedback err';
  }
}

/* ── Simulação ───────────────────────────────────────────────────────── */
async function runSimulate() {
  const session = requireAuth();
  if (!session) return;
  const box = $('#policy-sim-result');
  box.hidden = false;
  box.innerHTML = '<p class="muted">Calculando...</p>';
  try {
    const sim = await simulateModerationPolicy(session.token, 7);
    const total = sim.total || 0;
    const pct = (n) => total ? Math.round((n / total) * 100) : 0;
    const examples = (sim.exemplos_fila || [])
      .map((e) => `<li>${e.motivo} -- <code>${e.id.slice(0, 8)}</code></li>`)
      .join('');
    box.innerHTML = `
      <div class="policy-sim-stats">
        <div class="sim-stat sim-publish">
          <strong>${sim.publicados_auto}</strong>
          <span>publicados automaticamente</span>
          <small class="muted">${pct(sim.publicados_auto)}%</small>
        </div>
        <div class="sim-stat sim-queue">
          <strong>${sim.sua_fila}</strong>
          <span>chegariam na sua fila</span>
          <small class="muted">${pct(sim.sua_fila)}%</small>
        </div>
        <div class="sim-stat sim-discard">
          <strong>${sim.arquivados_auto}</strong>
          <span>arquivados automaticamente</span>
          <small class="muted">${pct(sim.arquivados_auto)}%</small>
        </div>
      </div>
      <p class="muted" style="margin-top:var(--space-md)">
        Ultimos <strong>${sim.periodo_dias}</strong> dias --
        <strong>${total}</strong> reportes analisados
      </p>
      ${examples ? `<p class="muted" style="margin-top:var(--space-md)">Exemplos na fila:</p><ul class="gestao-considera">${examples}</ul>` : ''}
    `;
  } catch (err) {
    if (handleAuthError(err)) return;
    box.innerHTML = `<p class="gestao-error">${err.message}</p>`;
  }
}

/* ── Init ────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  const session = requireAuth();
  if (!session) return;
  renderSidebar('aprovador');
  bindLogout();
  bindTabs();

  // Preenche imediatamente com defaults — não depende só do fetch
  renderPolicy(buildDefaultPolicy());

  try {
    const data = await fetchModerationPolicy(session.token);
    renderPolicy(data);
  } catch (err) {
    if (handleAuthError(err)) return;
    const msg = $('#policy-save-msg');
    if (msg) {
      msg.hidden = false;
      msg.className = 'gestao-feedback err';
      msg.textContent = `Não foi possível carregar a política do servidor (${err.message}). Exibindo valores padrão — salvar sobrescreverá no banco.`;
    }
  }

  $('#btn-save-policy')?.addEventListener('click', savePolicy);
  $('#btn-simulate')?.addEventListener('click', runSimulate);
});
