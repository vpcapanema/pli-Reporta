// Orquestrador da tela de captura.
//
// Fluxo — Evento de tráfego:
//   step-0 → step-1-evento (categoria) → step-2 (foto) → step-3 → step-4
//   descrição extra (txt-desc) revisada no envio
// Fluxo — Manifestação cidadã:
//   step-0 → step-1-manifestacao (tipo + texto revisado) → step-2 (se foto) OU step-3 → step-4
//   descrição extra (txt-desc) revisada no envio, se preenchida
import { getOrCreateClientId, enqueue, listQueue, dequeue, newLocalId, queueSize } from './db.js';
import { getCaptureNonce, postReport } from './api.js';
import { startCamera, stopCamera, captureFrame, getPositionOnce } from './camera.js';
import { createPickMap } from './map-pick.js';
import { categoryIconUrl } from './gestao-markers.js';
import { setReportIcon, mountReportPageIcons } from './report-icons.js';
import { formatDescriptionText } from './text-format.js';

const INTERACTION_LABELS = {
  evento_trafego: 'Evento de Tráfego',
  manifestacao: 'Manifestação cidadã',
};

const EVENT_CATEGORIES = [
  { id: 'buraco',                 label: 'Buraco' },
  { id: 'alagamento',             label: 'Alagamento' },
  { id: 'acidente',               label: 'Acidente' },
  { id: 'incendio',               label: 'Incêndio' },
  { id: 'animal_na_pista',        label: 'Animal na pista' },
  { id: 'objeto_na_pista',        label: 'Objeto na pista' },
  { id: 'queda_arvore',           label: 'Queda de árvore' },
  { id: 'veiculo_quebrado',       label: 'Veículo quebrado' },
  { id: 'bloqueio_total',         label: 'Bloqueio total' },
  { id: 'obra_grande',            label: 'Obra' },
  { id: 'lentidao_corredor',      label: 'Lentidão' },
  { id: 'sinalizacao_quebrada',   label: 'Sinalização' },
  { id: 'outro',                  label: 'Outro' },
];

const MANIF_TYPES = [
  { id: 'elogio',     icon: 'elogio',     label: 'Elogio' },
  { id: 'sugestao',   icon: 'sugestao',   label: 'Sugestão' },
  { id: 'reclamacao', icon: 'reclamacao', label: 'Reclamação' },
];

const state = {
  interactionType: null,
  category: null,
  description: '',
  position: null,
  accuracy: null,
  photoBlob: null,
  photoPreviewUrl: null,
  capturedAt: null,
  nonce: null,
  stream: null,
  pickMap: null,
  mapInitialized: false,
  withPhoto: false,
};

const clientId = getOrCreateClientId();

const DESCRIPTION_MAX = 500;

function bindCharCounter(fieldSel, counterSel) {
  const field = $(fieldSel);
  const counter = $(counterSel);
  if (!field || !counter) return () => {};
  const max = Number(field.maxLength) || DESCRIPTION_MAX;
  const update = () => {
    const len = field.value.length;
    counter.textContent = `${len} / ${max}`;
    counter.classList.toggle('is-limit', len >= max);
  };
  field.addEventListener('input', update);
  update();
  return update;
}

function $(sel) { return document.querySelector(sel); }
function show(id) { $(id).hidden = false; }
function hide(id) { $(id).hidden = true; }
function hideAllSteps() {
  ['#step-0', '#step-1-evento', '#step-1-manifestacao', '#step-2', '#step-3', '#step-4']
    .forEach((id) => hide(id));
}

function toast(msg, type) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast show' + (type ? ' ' + type : '');
  setTimeout(() => t.classList.remove('show'), 3500);
}

async function updateQueueBadge() {
  const n = await queueSize();
  const badge = $('#queue-badge');
  if (n > 0) {
    badge.hidden = false;
    badge.textContent = `${n} na fila`;
  } else {
    badge.hidden = true;
  }
}

function renderEventCategories() {
  const grid = $('#cat-grid');
  grid.innerHTML = '';
  for (const c of EVENT_CATEGORIES) {
    const b = document.createElement('button');
    b.type = 'button';
    b.dataset.id = c.id;
    const url = categoryIconUrl(c.id);
    b.innerHTML = `<span class="ico ico-img"><img src="${url}" alt="" width="28" height="28"/></span><span>${c.label}</span>`;
    b.addEventListener('click', () => selectEventCategory(c.id));
    grid.appendChild(b);
  }
}

function renderManifTypes() {
  const grid = $('#manif-grid');
  grid.innerHTML = '';
  for (const c of MANIF_TYPES) {
    const b = document.createElement('button');
    b.type = 'button';
    b.dataset.id = c.id;
    b.innerHTML = `<span class="ico"></span><span>${c.label}</span>`;
    setReportIcon(b.querySelector('.ico'), c.icon);
    b.addEventListener('click', () => selectManifType(c.id));
    grid.appendChild(b);
  }
}

function selectEventCategory(id) {
  state.category = id;
  document.querySelectorAll('#cat-grid button').forEach((b) => {
    b.classList.toggle('selected', b.dataset.id === id);
  });
  $('#btn-step1-evento').disabled = false;
}

function selectManifType(id) {
  state.category = id;
  document.querySelectorAll('#manif-grid button').forEach((b) => {
    b.classList.toggle('selected', b.dataset.id === id);
  });
  validateManifStep();
}

function validateManifStep() {
  const ok = state.category && $('#txt-manif').value.trim().length >= 15;
  $('#btn-step1-manifestacao').disabled = !ok;
}

function categoryLabel(id) {
  const event = EVENT_CATEGORIES.find((c) => c.id === id);
  if (event) return event.label;
  const manif = MANIF_TYPES.find((c) => c.id === id);
  return manif?.label || id || '—';
}

function fillSubmitSummary() {
  $('#summary-interaction').textContent =
    INTERACTION_LABELS[state.interactionType] || '—';
  $('#summary-category').textContent = categoryLabel(state.category);
  $('#summary-description').textContent = state.description || '—';
}

/** Formata texto, grava no campo (se houver) e devolve o resultado. */
async function applyFormattedText(text, fieldEl) {
  const formatted = await formatDescriptionText(text);
  if (fieldEl) fieldEl.value = formatted;
  return formatted;
}

/** Manifestação: revisa descrição principal ao sair da etapa 1. */
async function prepareManifestacaoDescription() {
  const el = $('#txt-manif');
  const formatted = await applyFormattedText(el.value.trim(), el);
  state.description = formatted;
  return formatted;
}

/** Revisa descrição extra (step 3) quando preenchida. */
async function prepareExtraDescription() {
  return applyFormattedText($('#txt-desc').value.trim(), $('#txt-desc'));
}

/** Revisa todos os textos do reporte antes do envio (versão corrigida vai ao banco). */
async function prepareDescriptionsForSubmit() {
  if (state.interactionType === 'manifestacao') {
    await prepareManifestacaoDescription();
  }
  await prepareExtraDescription();
}

function buildReportDescription() {
  const isManif = state.interactionType === 'manifestacao';
  if (isManif) {
    const main = state.description || $('#txt-manif').value.trim();
    const extra = $('#txt-desc').value.trim();
    if (main && extra) return `${main}\n${extra}`;
    return main || extra;
  }
  return $('#txt-desc').value.trim();
}

function buildPayload() {
  const isManif = state.interactionType === 'manifestacao';
  return {
    photoBlob: state.photoBlob,
    lat: state.position.lat,
    lon: state.position.lon,
    accuracy: state.accuracy,
    category: state.category,
    interactionType: state.interactionType,
    magnitude: isManif ? 'normal' : ($('#sel-magnitude').value || 'normal'),
    description: buildReportDescription(),
    capturedAt: state.capturedAt,
    captureNonce: state.nonce,
    clientId,
  };
}

function isLikelyNetworkError(err) {
  if (!err) return false;
  if (err.name === 'TypeError') return true;
  const msg = String(err.message || '').toLowerCase();
  return msg.includes('failed to fetch')
    || msg.includes('networkerror')
    || msg.includes('network')
    || msg.includes('load failed');
}

function validateSubmissionPayload(payload) {
  if (!payload.photoBlob || payload.photoBlob.size === 0) {
    throw new Error('Foto do reporte ausente. Volte e tente novamente.');
  }
  if (!payload.capturedAt) {
    throw new Error('Data de captura ausente. Volte e tente novamente.');
  }
  if (payload.lat == null || payload.lon == null || Number.isNaN(payload.lat) || Number.isNaN(payload.lon)) {
    throw new Error('Localização GPS ausente. Ajuste o ponto no mapa.');
  }
  if (payload.interactionType === 'manifestacao') {
    const desc = (payload.description || '').trim();
    if (desc.length < 15) {
      throw new Error('Descrição obrigatória (mínimo 15 caracteres).');
    }
  }
}

function setResultHeader(title) {
  const label = document.querySelector('#step-4 .label');
  if (label) label.textContent = title;
}

/** Ajusta visibilidade dos blocos do step-3 conforme o fluxo. */
function configureConfirmStep(mode) {
  const isManifTextOnly = mode === 'manifestacao-text-only';
  const photoWrap = $('#photo-preview-wrap');
  const noPhoto = $('#no-photo-notice');
  const preview = $('#preview-img');
  const extraDesc = $('#extra-desc-wrap');
  const magnitude = $('#magnitude-wrap');

  $('#submit-summary').hidden = !isManifTextOnly;
  extraDesc.hidden = isManifTextOnly;
  magnitude.hidden = isManifTextOnly || state.interactionType !== 'evento_trafego';

  if (isManifTextOnly) {
    photoWrap.hidden = true;
    noPhoto.hidden = true;
    preview.hidden = true;
    preview.removeAttribute('src');
    $('#extras-details').open = true;
    fillSubmitSummary();
  } else {
    const showPreview = Boolean(state.photoPreviewUrl);
    photoWrap.hidden = !showPreview;
    noPhoto.hidden = true;
    preview.hidden = !showPreview;
    if (!showPreview) preview.removeAttribute('src');
    magnitude.hidden = state.interactionType !== 'evento_trafego';
    $('#extras-details').open = false;
  }
}

function showConfirmStep(mode) {
  configureConfirmStep(mode);
  hideAllSteps();
  show('#step-3');
  initPickMapLazy();
}

function startBranch(type) {
  state.interactionType = type;
  hideAllSteps();
  if (type === 'evento_trafego') {
    show('#step-1-evento');
  } else {
    show('#step-1-manifestacao');
  }
}

/** Gera imagem 1×1 cinza como placeholder quando não há foto. */
async function createPlaceholderPhoto() {
  const canvas = document.createElement('canvas');
  canvas.width = 1;
  canvas.height = 1;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#cccccc';
  ctx.fillRect(0, 0, 1, 1);
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.5);
  });
}

/** Fluxo sem câmera: captura GPS e vai para confirmação com resumo. */
async function openConfirmDirectly() {
  const btn = $('#btn-step1-manifestacao');
  btn.textContent = 'Buscando GPS…';

  try {
    state.nonce = null;
    state.capturedAt = new Date().toISOString();

    const [nonceRes, pos] = await Promise.all([
      navigator.onLine ? getCaptureNonce(clientId).catch(() => null) : Promise.resolve(null),
      getPositionOnce().catch(() => null),
    ]);

    if (nonceRes) state.nonce = nonceRes.nonce;
    if (pos) {
      state.position = { lat: pos.lat, lon: pos.lon };
      state.accuracy = pos.accuracy;
    } else {
      state.position = { lat: -23.55, lon: -46.63 };
      state.accuracy = null;
    }

    state.photoBlob = await createPlaceholderPhoto();
    if (state.photoPreviewUrl) URL.revokeObjectURL(state.photoPreviewUrl);
    state.photoPreviewUrl = null;

    showConfirmStep('manifestacao-text-only');
  } finally {
    btn.textContent = 'Continuar';
  }
}

/** Manifestação etapa 1 → etapa 2 ou 3 (sempre revisa o texto antes). */
async function continueManifestacaoStep1() {
  const btn = $('#btn-step1-manifestacao');
  btn.disabled = true;
  try {
    btn.textContent = 'Formatando texto…';
    await prepareManifestacaoDescription();
    if (state.withPhoto) {
      await openCameraStep();
    } else {
      await openConfirmDirectly();
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Continuar';
    validateManifStep();
  }
}

function togglePhotoOption() {
  state.withPhoto = !state.withPhoto;
  const btn  = $('#btn-toggle-photo');
  const pill = $('#photo-toggle-pill');
  const ico  = $('#photo-toggle-icon');
  const desc = $('#photo-toggle-desc');

  btn.classList.toggle('active', state.withPhoto);
  btn.setAttribute('aria-pressed', String(state.withPhoto));

  if (state.withPhoto) {
    pill.textContent = 'Sim';
    setReportIcon(ico, 'check');
    if (desc) desc.textContent = 'Câmera será aberta ao continuar';
  } else {
    pill.textContent = 'Não';
    setReportIcon(ico, 'camera');
    if (desc) desc.textContent = 'Clique para abrir a câmera ao continuar';
  }
}

async function openCameraStep() {
  hideAllSteps();
  show('#step-2');
  $('#status-line').textContent = 'Buscando GPS e preparando câmera…';

  state.nonce = null;
  state.position = null;
  state.accuracy = null;

  const gpsPromise = getPositionOnce().catch(() => null);
  const noncePromise = navigator.onLine
    ? getCaptureNonce(clientId).catch(() => null)
    : Promise.resolve(null);

  const [nonceRes, pos] = await Promise.all([noncePromise, gpsPromise]);

  if (nonceRes) state.nonce = nonceRes.nonce;
  if (pos) {
    state.position = { lat: pos.lat, lon: pos.lon };
    state.accuracy = pos.accuracy;
    $('#gps-line').textContent =
      `GPS: ${pos.lat.toFixed(5)}, ${pos.lon.toFixed(5)} (±${Math.round(pos.accuracy)} m)`;
  } else {
    $('#gps-line').textContent = 'GPS indisponível — ajuste no mapa depois da foto.';
    state.position = { lat: -23.55, lon: -46.63 };
  }

  const video = $('#cam-video');
  const cam = await startCamera(video);
  if (cam.ok) {
    state.stream = cam.stream;
    $('#cam-status').textContent = 'Câmera ativa';
    $('#btn-shoot').disabled = false;
    $('#fallback-input').hidden = true;
  } else {
    $('#cam-status').textContent = 'Câmera indisponível — use o botão abaixo.';
    $('#btn-shoot').disabled = true;
    $('#fallback-input').hidden = false;
  }
  $('#status-line').textContent = '';
}

async function shoot() {
  try {
    const blob = await captureFrame($('#cam-video'));
    await onPhoto(blob);
  } catch (err) {
    toast('Falha ao capturar: ' + err.message, 'err');
  }
}

async function onPhoto(blob) {
  state.photoBlob = blob;
  state.capturedAt = new Date().toISOString();
  if (state.photoPreviewUrl) URL.revokeObjectURL(state.photoPreviewUrl);
  state.photoPreviewUrl = URL.createObjectURL(blob);
  $('#preview-img').src = state.photoPreviewUrl;

  if (state.interactionType === 'manifestacao' && !state.description) {
    await prepareManifestacaoDescription();
  }

  showConfirmStep('with-photo');
  stopCamera(state.stream);
  state.stream = null;
}

function initPickMapLazy() {
  if (state.mapInitialized) return;
  state.pickMap = createPickMap('pickmap', state.position, (pt) => {
    state.position = pt;
    $('#picked-line').textContent =
      `Local ajustado: ${pt.lat.toFixed(5)}, ${pt.lon.toFixed(5)}`;
  });
  state.mapInitialized = true;
}

async function submit() {
  const btn = $('#btn-submit');
  btn.disabled = true;
  try {
    btn.textContent = 'Formatando texto…';
    await prepareDescriptionsForSubmit();
    btn.textContent = 'Enviando…';
    const payload = buildPayload();
    validateSubmissionPayload(payload);

    if (!navigator.onLine) {
      await enqueueOffline(payload);
      return;
    }

    try {
      const res = await postReport(payload);
      if (!res?.id) {
        throw new Error('Servidor não confirmou o reporte (sem ID).');
      }
      showResult(res);
    } catch (err) {
      console.error(err);
      if (err.status === 422) {
        toast(err.detail || err.message, 'err');
        return;
      }
      if (err.status >= 400 && err.status < 500) {
        toast(err.detail || err.message || 'Envio rejeitado pelo servidor.', 'err');
        return;
      }
      if (isLikelyNetworkError(err)) {
        await enqueueOffline(payload);
        return;
      }
      toast(err.message || 'Falha ao enviar o reporte.', 'err');
    }
  } catch (err) {
    console.error(err);
    toast(err.message || 'Não foi possível preparar o envio.', 'err');
  } finally {
    btn.textContent = 'Enviar';
    btn.disabled = false;
  }
}

async function enqueueOffline(payload) {
  const buf = await payload.photoBlob.arrayBuffer();
  await enqueue({
    localId: newLocalId(),
    photoBuffer: buf,
    payload: { ...payload, photoBlob: undefined },
    queuedAt: new Date().toISOString(),
    retries: 0,
  });
  await updateQueueBadge();
  toast('Salvo no celular — enviará quando houver internet.', 'warn');
  showOfflineResult();
  registerBackgroundSync();
}

function showOfflineResult() {
  hideAllSteps();
  show('#step-4');
  setResultHeader('Salvo neste aparelho');
  $('#result-message').textContent =
    'Ainda não chegou ao servidor. Mantenha esta página aberta ou volte com internet no mesmo aparelho para envio automático.';
  $('#result-id').textContent = 'pendente (fila local)';
}

function showResult(res) {
  hideAllSteps();
  show('#step-4');
  setResultHeader('Reporte recebido');
  $('#result-message').textContent =
    res.message || 'Registrado no servidor. Você pode fechar o app.';
  $('#result-id').textContent = res.id;
}

function resetForNext() {
  if (state.stream) {
    stopCamera(state.stream);
    state.stream = null;
  }
  state.interactionType = null;
  state.category = null;
  state.description = '';
  state.position = null;
  state.accuracy = null;
  state.capturedAt = null;
  state.photoBlob = null;
  state.withPhoto = false;
  if (state.photoPreviewUrl) URL.revokeObjectURL(state.photoPreviewUrl);
  state.photoPreviewUrl = null;
  state.nonce = null;
  state.mapInitialized = false;
  state.pickMap = null;
  $('#txt-desc').value = '';
  $('#txt-manif').value = '';
  refreshManifCharCount();
  refreshDescCharCount();
  $('#btn-step1-evento').disabled = true;
  $('#btn-step1-manifestacao').disabled = true;
  const toggleBtn = $('#btn-toggle-photo');
  if (toggleBtn) {
    toggleBtn.classList.remove('active');
    toggleBtn.setAttribute('aria-pressed', 'false');
  }
  const pill = $('#photo-toggle-pill');
  if (pill) pill.textContent = 'Não';
  setReportIcon($('#photo-toggle-icon'), 'camera');
  const desc = $('#photo-toggle-desc');
  if (desc) desc.textContent = 'Clique para abrir a câmera ao continuar';
  $('#preview-img').hidden = true;
  $('#preview-img').removeAttribute('src');
  $('#photo-preview-wrap').hidden = true;
  $('#no-photo-notice').hidden = true;
  $('#submit-summary').hidden = true;
  $('#extra-desc-wrap').hidden = false;
  document.querySelectorAll('.cat-grid button').forEach((b) => b.classList.remove('selected'));
  hideAllSteps();
  show('#step-0');
}

async function registerBackgroundSync() {
  if ('serviceWorker' in navigator && 'SyncManager' in window) {
    try {
      const reg = await navigator.serviceWorker.ready;
      await reg.sync.register('pli-reporta-flush');
    } catch (_) { /* iOS não suporta */ }
  }
}

async function flushQueue() {
  const items = await listQueue();
  if (items.length === 0) {
    await updateQueueBadge();
    return;
  }
  let sent = 0;
  let failed = 0;
  for (const it of items) {
    try {
      const blob = new Blob([it.photoBuffer], { type: 'image/jpeg' });
      const res = await postReport({
        ...it.payload,
        photoBlob: blob,
        offlineCapture: true,
        queuedAt: it.queuedAt,
      });
      if (!res?.id) throw new Error('sem ID na resposta');
      await dequeue(it.localId);
      sent++;
    } catch (e) {
      failed++;
      console.warn('Fila: item falhou, continua depois', it.localId, e);
    }
  }
  await updateQueueBadge();
  if (sent > 0) toast(`${sent} reporte(s) enviado(s) ao servidor.`, 'ok');
  if (failed > 0 && sent === 0) {
    toast('Há reportes na fila local aguardando conexão com o servidor.', 'warn');
  }
}

async function onFallbackFile(ev) {
  const f = ev.target.files && ev.target.files[0];
  if (!f) return;
  await onPhoto(f);
}

let refreshManifCharCount = () => {};
let refreshDescCharCount = () => {};

function bindUI() {
  mountReportPageIcons();
  renderEventCategories();
  renderManifTypes();
  refreshManifCharCount = bindCharCounter('#txt-manif', '#txt-manif-count');
  refreshDescCharCount = bindCharCounter('#txt-desc', '#txt-desc-count');

  $('#branch-evento').addEventListener('click', () => startBranch('evento_trafego'));
  $('#branch-manifestacao').addEventListener('click', () => startBranch('manifestacao'));

  $('#btn-back-0').addEventListener('click', resetForNext);
  $('#btn-back-0b').addEventListener('click', resetForNext);

  $('#btn-step1-evento').addEventListener('click', openCameraStep);
  $('#btn-step1-manifestacao').addEventListener('click', () => {
    continueManifestacaoStep1();
  });

  $('#txt-manif').addEventListener('input', validateManifStep);
  $('#btn-toggle-photo').addEventListener('click', togglePhotoOption);

  $('#btn-shoot').addEventListener('click', shoot);
  $('#fallback-input').addEventListener('change', onFallbackFile);
  $('#btn-submit').addEventListener('click', submit);
  $('#btn-new').addEventListener('click', resetForNext);

  $('#btn-back').addEventListener('click', () => {
    stopCamera(state.stream);
    state.stream = null;
    hideAllSteps();
    if (state.interactionType === 'evento_trafego') {
      show('#step-1-evento');
    } else {
      show('#step-1-manifestacao');
    }
  });

  window.addEventListener('online', flushQueue);
  navigator.serviceWorker?.addEventListener('message', (ev) => {
    if (ev.data && ev.data.type === 'flush-queue') flushQueue();
  });
}

function registerSW() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
}

document.addEventListener('DOMContentLoaded', () => {
  bindUI();
  registerSW();
  updateQueueBadge();
  flushQueue();
});
