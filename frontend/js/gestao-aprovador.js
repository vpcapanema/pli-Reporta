/** Configuração amigável do aprovador automático. */
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

let currentPolicy = null;

/* ── Presets ─────────────────────────────────────────────────────────── */
function renderPresets(data) {
  const el = $('#policy-presets');
  if (!el) return;
  el.innerHTML = (data.presets || []).map((p) => `
    <label class="gestao-preset${data.preset === p.id ? ' active' : ''}">
      <input type="radio" name="preset" value="${p.id}" ${data.preset === p.id ? 'checked' : ''}/>
      <strong>${p.label}</strong>
      <span class="muted">${p.descricao}</span>
    </label>
  `).join('');
}

/* ── Critérios (sinais) ──────────────────────────────────────────────── */
function renderSignals(signals, containerId) {
  const el = $(`#${containerId}`);
  if (!el || !signals?.length) return;
  el.innerHTML = signals.map((s) => `
    <div class="policy-signal-card">
      <div class="signal-head">
        <strong>${s.label}</strong>
        <span class="signal-badge">${s.peso} pts</span>
      </div>
      <p class="muted">${s.como}</p>
    </div>
  `).join('');
}

/* ── Zona de decisão colorida ────────────────────────────────────────── */
/**
 * Renderiza a zona colorida (descarte | fila | publicação) com dois sliders
 * e campos numéricos explícitos.
 *
 * @param {string} wrapId    id do wrapper <div>
 * @param {string} prefixLo  prefixo do slider de descarte (ex: "event-discard")
 * @param {string} prefixHi  prefixo do slider de publicação (ex: "event-publish")
 * @param {number} valLo     valor inicial limiar de descarte
 * @param {number} valHi     valor inicial limiar de publicação
 */
function renderZone(wrapId, prefixLo, prefixHi, valLo, valHi) {
  const wrap = $(`#${wrapId}`);
  if (!wrap) return;

  wrap.innerHTML = `
    <div class="policy-zone">
      <div class="policy-zone-bar" id="${wrapId}-bar">
        <div class="zone-seg zone-discard" id="${wrapId}-seg-d">
          <span>Descarte automático</span>
        </div>
        <div class="zone-seg zone-fila" id="${wrapId}-seg-f">
          <span>Fila humana</span>
        </div>
        <div class="zone-seg zone-publish" id="${wrapId}-seg-p">
          <span>Publicação automática</span>
        </div>
      </div>
      <div class="policy-zone-ruler">
        <span>0</span>
        <span id="${wrapId}-lo-label" class="zone-ruler-mid">${valLo}</span>
        <span id="${wrapId}-hi-label" class="zone-ruler-mid">${valHi}</span>
        <span>100</span>
      </div>
    </div>

    <div class="policy-thresholds">
      <div class="policy-threshold">
        <label for="${prefixLo}-slider">
          Arquivar sozinho abaixo de
          <strong id="${prefixLo}-value">${valLo}</strong> pontos
        </label>
        <input type="range" id="${prefixLo}-slider"
               min="5" max="60" step="1" value="${valLo}"/>
        <p class="muted">Confiança muito baixa — sistema descarta sem perguntar</p>
      </div>
      <div class="policy-threshold">
        <label for="${prefixHi}-slider">
          Publicar sozinho acima de
          <strong id="${prefixHi}-value">${valHi}</strong> pontos
        </label>
        <input type="range" id="${prefixHi}-slider"
               min="40" max="95" step="1" value="${valHi}"/>
        <p class="muted">Confiança alta — sistema publica no mapa sem revisão humana</p>
      </div>
    </div>
  `;

  updateZoneBar(wrapId, valLo, valHi);
  bindZoneSliders(wrapId, prefixLo, prefixHi);
}

function updateZoneBar(wrapId, lo, hi) {
  const bar = $(`#${wrapId}-bar`);
  if (!bar) return;
  const pLo = lo;
  const pHi = hi;
  bar.style.setProperty('--pct-lo', `${pLo}%`);
  bar.style.setProperty('--pct-hi', `${pHi}%`);

  const segD = $(`#${wrapId}-seg-d`);
  const segF = $(`#${wrapId}-seg-f`);
  const segP = $(`#${wrapId}-seg-p`);
  if (segD) segD.style.flexBasis = `${pLo}%`;
  if (segF) segF.style.flexBasis = `${pHi - pLo}%`;
  if (segP) segP.style.flexBasis = `${100 - pHi}%`;

  const loLabel = $(`#${wrapId}-lo-label`);
  const hiLabel = $(`#${wrapId}-hi-label`);
  if (loLabel) { loLabel.textContent = lo; loLabel.style.left = `${pLo}%`; }
  if (hiLabel) { hiLabel.textContent = hi; hiLabel.style.left = `${pHi}%`; }
}

function bindZoneSliders(wrapId, prefixLo, prefixHi) {
  const sliderLo = $(`#${prefixLo}-slider`);
  const sliderHi = $(`#${prefixHi}-slider`);
  const valLo    = $(`#${prefixLo}-value`);
  const valHi    = $(`#${prefixHi}-value`);
  if (!sliderLo || !sliderHi) return;

  const sync = () => {
    const lo = Number(sliderLo.value);
    const hi = Number(sliderHi.value);
    if (lo >= hi) {
      sliderLo.value = hi - 5;
    }
    if (valLo) valLo.textContent = sliderLo.value;
    if (valHi) valHi.textContent = sliderHi.value;
    updateZoneBar(wrapId, Number(sliderLo.value), Number(sliderHi.value));
  };

  sliderLo.oninput = sync;
  sliderHi.oninput = sync;
}

/* ── Checkboxes ──────────────────────────────────────────────────────── */
function bindCheckboxes(rev) {
  if (!rev) return;
  $('#rev-bloqueio').checked  = rev.bloqueio_alagamento;
  $('#rev-offline').checked   = rev.envio_offline;
  $('#rev-primeiro').checked  = rev.primeiro_na_regiao;
  $('#rev-outro').checked     = rev.categoria_outro;
}

/* ── Render completo da política ─────────────────────────────────────── */
function renderPolicy(data) {
  currentPolicy = data;
  $('#policy-intro').textContent = data.intro;

  renderPresets(data);

  // Sinais
  renderSignals(data.sinais_evento, 'sinais-evento');
  renderSignals(data.sinais_manif,  'sinais-manif');

  // Zonas de decisão
  renderZone(
    'event-zone-wrap',
    'event-discard', 'event-publish',
    data.eventos.arquivar_sozinho.valor,
    data.eventos.publicar_sozinho.valor,
  );
  renderZone(
    'manif-zone-wrap',
    'manif-discard', 'manif-publish',
    data.manifestacoes.arquivar_sozinho.valor,
    data.manifestacoes.publicar_sozinho.valor,
  );

  // Checkboxes
  bindCheckboxes(data.eventos.sempre_revisar);

  // Decisões imediatas
  const auto = $('#policy-auto-list');
  if (auto) {
    auto.innerHTML = (data.auto_nunca_filas || []).map((t) => `<li>${t}</li>`).join('');
  }
}

/* ── Coleta payload para salvar ──────────────────────────────────────── */
function collectPayload() {
  const preset = document.querySelector('input[name="preset"]:checked')?.value;
  return {
    preset,
    eventos: {
      publicar_sozinho: Number($('#event-publish-slider')?.value),
      arquivar_sozinho: Number($('#event-discard-slider')?.value),
      sempre_revisar: {
        bloqueio_alagamento: $('#rev-bloqueio')?.checked,
        envio_offline:       $('#rev-offline')?.checked,
        primeiro_na_regiao:  $('#rev-primeiro')?.checked,
        categoria_outro:     $('#rev-outro')?.checked,
      },
    },
    manifestacoes: {
      publicar_sozinho: Number($('#manif-publish-slider')?.value),
      arquivar_sozinho: Number($('#manif-discard-slider')?.value),
    },
  };
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
    msg.textContent = 'Configuração salva.';
    msg.className = 'gestao-feedback ok';
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
  box.innerHTML = '<p class="muted">Calculando…</p>';
  try {
    const sim = await simulateModerationPolicy(session.token, 7);
    const total = sim.total || 0;
    const pct = (n) => total ? Math.round((n / total) * 100) : 0;
    const examples = (sim.exemplos_fila || [])
      .map((e) => `<li>${e.motivo} <code>${e.id.slice(0, 8)}</code></li>`)
      .join('');
    box.innerHTML = `
      <div class="policy-sim-stats">
        <div class="sim-stat sim-publish">
          <strong>${sim.publicados_auto}</strong>
          <span>publicados automaticamente</span>
          <small class="muted">${pct(sim.publicados_auto)}% do total</small>
        </div>
        <div class="sim-stat sim-queue">
          <strong>${sim.sua_fila}</strong>
          <span>chegariam na sua fila</span>
          <small class="muted">${pct(sim.sua_fila)}% do total</small>
        </div>
        <div class="sim-stat sim-discard">
          <strong>${sim.arquivados_auto}</strong>
          <span>arquivados automaticamente</span>
          <small class="muted">${pct(sim.arquivados_auto)}% do total</small>
        </div>
      </div>
      <p class="muted" style="margin-top:var(--space-md)">
        Últimos <strong>${sim.periodo_dias}</strong> dias ·
        <strong>${total}</strong> reportes analisados
      </p>
      ${examples ? `<p class="muted">Exemplos que chegariam na sua fila:</p><ul class="gestao-considera">${examples}</ul>` : ''}
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

  document.addEventListener('change', async (e) => {
    const r = e.target;
    if (r.name !== 'preset' || !r.checked) return;
    const session = requireAuth();
    if (!session) return;
    try {
      const updated = await updateModerationPolicy(session.token, { preset: r.value });
      renderPolicy(updated);
    } catch (err) {
      handleAuthError(err);
    }
  });
});
