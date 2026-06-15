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
function renderGlobal(g) {
  $('#g-event-pub').value    = g.event_publish_min;
  $('#g-event-disc').value   = g.event_discard_below;
  $('#g-manif-pub').value    = g.manif_publish_min;
  $('#g-manif-disc').value   = g.manif_discard_below;
  $('#g-blocking').checked   = g.always_review_blocking;
  $('#g-offline').checked    = g.always_review_offline;
  $('#g-first-area').checked = g.always_review_first_in_area;
  $('#g-other').checked      = g.always_review_other;

  // Atualiza rótulos de padrão nas tabelas das seções 3 e 5
  const ep = $('#lbl-event-pub');  if (ep) ep.textContent = `Padrão: ${g.event_publish_min} pts`;
  const ed = $('#lbl-event-disc'); if (ed) ed.textContent = `Padrão: ${g.event_discard_below} pts`;
  const mp = $('#lbl-manif-pub');  if (mp) mp.textContent = `Padrão: ${g.manif_publish_min} pts`;
  const md = $('#lbl-manif-disc'); if (md) md.textContent = `Padrão: ${g.manif_discard_below} pts`;
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

  const total = sinais.reduce((s, x) => s + x.peso, 0);
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

  // Atualiza total ao digitar
  tbody.querySelectorAll('[data-field="peso"]').forEach((el) => {
    el.addEventListener('input', () => {
      const all = Array.from(tbody.querySelectorAll('[data-field="peso"]'));
      const sum = all.reduce((acc, i) => acc + (parseFloat(i.value) || 0), 0);
      if (lbl) lbl.textContent = `(total: ${sum.toFixed(1)}%)`;
      const bar = el.closest('tr')?.querySelector('.weight-bar');
      if (bar) bar.style.width = `${Math.min(parseFloat(el.value) || 0, 100)}%`;
    });
  });
}

/* ── Seção 3: Eventos por categoria ──────────────────────────────────── */
function renderEventosTable(categorias, globalPub, globalDisc) {
  const tbody = $('#tbody-eventos');
  if (!tbody) return;

  tbody.innerHTML = categorias.map((cat) => {
    const pubIsGlobal  = cat.limiar_publicar  == null;
    const discIsGlobal = cat.limiar_descartar == null;
    const pubVal  = pubIsGlobal  ? globalPub  : cat.limiar_publicar;
    const discVal = discIsGlobal ? globalDisc : cat.limiar_descartar;

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

  tbody.innerHTML = fatores.map((hw) => `
    <tr data-hw-id="${hw.id}">
      <td class="col-highway-id"><code>${hw.id}</code></td>
      <td class="col-highway-label"><span class="muted">${hw.label}</span></td>
      <td class="col-weight">
        <div class="thresh-cell">
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
    el.addEventListener('input', () => {
      const bar = el.closest('tr')?.querySelector('.weight-bar');
      if (bar) bar.style.width = `${Math.min(parseFloat(el.value) || 0, 100)}%`;
    });
  });
}

/* ── Seção 5: Manifestações ──────────────────────────────────────────── */
function renderManifTable(categorias, globalPub, globalDisc) {
  const tbody = $('#tbody-manif');
  if (!tbody) return;

  tbody.innerHTML = categorias.map((cat) => {
    const pubIsGlobal  = cat.limiar_publicar  == null;
    const discIsGlobal = cat.limiar_descartar == null;
    const pubVal  = pubIsGlobal  ? globalPub  : cat.limiar_publicar;
    const discVal = discIsGlobal ? globalDisc : cat.limiar_descartar;

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
  renderGlobal(data.global);
  renderSignals(data.sinais_veracidade || []);
  renderHighwayTable(data.fatores_via || []);
  renderEventosTable(
    data.categorias_evento,
    data.global.event_publish_min,
    data.global.event_discard_below,
  );
  renderManifTable(
    data.categorias_manif,
    data.global.manif_publish_min,
    data.global.manif_discard_below,
  );
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

  try {
    const data = await fetchModerationPolicy(session.token);
    renderPolicy(data);
  } catch (err) {
    handleAuthError(err);
  }

  $('#btn-save-policy')?.addEventListener('click', savePolicy);
  $('#btn-simulate')?.addEventListener('click', runSimulate);
});
