// Orquestrador da tela de captura.
import { getOrCreateClientId, enqueue, listQueue, dequeue, newLocalId, queueSize } from './db.js';
import { getCaptureNonce, postReport } from './api.js';
import { startCamera, stopCamera, captureFrame, getPositionOnce } from './camera.js';
import { createPickMap } from './map-pick.js';

const EVENT_CATEGORIES = [
  { id: 'buraco',                 ico: 'BU', label: 'Buraco' },
  { id: 'alagamento',             ico: 'AL', label: 'Alagamento' },
  { id: 'acidente',               ico: 'AC', label: 'Acidente' },
  { id: 'incendio',               ico: 'IN', label: 'Incêndio' },
  { id: 'animal_na_pista',        ico: 'AN', label: 'Animal na pista' },
  { id: 'objeto_na_pista',        ico: 'OP', label: 'Objeto na pista' },
  { id: 'queda_arvore',           ico: 'AR', label: 'Queda de árvore' },
  { id: 'veiculo_quebrado',       ico: 'VQ', label: 'Veículo quebrado' },
  { id: 'bloqueio_total',         ico: 'BL', label: 'Bloqueio total' },
  { id: 'obra_grande',            ico: 'OB', label: 'Obra' },
  { id: 'lentidao_corredor',      ico: 'LE', label: 'Lentidão' },
  { id: 'sinalizacao_quebrada',   ico: 'SI', label: 'Sinalização' },
  { id: 'outro',                  ico: 'OU', label: 'Outro' },
];

const MANIF_TYPES = [
  { id: 'elogio',     ico: 'EL', label: 'Elogio' },
  { id: 'sugestao',   ico: 'SG', label: 'Sugestão' },
  { id: 'reclamacao', ico: 'RC', label: 'Reclamação' },
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
    b.innerHTML = `<span class="ico">${c.ico}</span><span>${c.label}</span>`;
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
    b.innerHTML = `<span class="ico">${c.ico}</span><span>${c.label}</span>`;
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

/** Fluxo sem câmera: captura GPS, gera placeholder e vai direto para confirmação. */
async function openConfirmDirectly() {
  const btn = $('#btn-step1-manifestacao');
  btn.disabled = true;
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

    $('#preview-img').hidden = true;
    $('#no-photo-notice').hidden = false;
    $('#magnitude-wrap').hidden = true;
    $('#extras-details').open = true;

    hideAllSteps();
    show('#step-3');
    initPickMapLazy();
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
    ico.textContent  = '✓';
    if (desc) desc.textContent = 'Câmera será aberta ao continuar';
  } else {
    pill.textContent = 'Não';
    ico.textContent  = '📷';
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
    onPhoto(blob);
  } catch (err) {
    toast('Falha ao capturar: ' + err.message, 'err');
  }
}

function onPhoto(blob) {
  state.photoBlob = blob;
  state.capturedAt = new Date().toISOString();
  if (state.photoPreviewUrl) URL.revokeObjectURL(state.photoPreviewUrl);
  state.photoPreviewUrl = URL.createObjectURL(blob);
  $('#preview-img').src = state.photoPreviewUrl;
  $('#preview-img').hidden = false;
  $('#no-photo-notice').hidden = true;

  const isEvent = state.interactionType === 'evento_trafego';
  $('#magnitude-wrap').hidden = !isEvent;
  $('#extras-details').open = false;

  hideAllSteps();
  show('#step-3');
  stopCamera(state.stream);
  state.stream = null;
  initPickMapLazy();
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

function buildPayload() {
  const isManif = state.interactionType === 'manifestacao';
  let description = $('#txt-desc').value.trim();
  if (isManif) {
    description = state.description || $('#txt-manif').value.trim();
    if ($('#txt-desc').value.trim()) {
      description = description + '\n' + $('#txt-desc').value.trim();
    }
  }
  return {
    photoBlob: state.photoBlob,
    lat: state.position.lat,
    lon: state.position.lon,
    accuracy: state.accuracy,
    category: state.category,
    interactionType: state.interactionType,
    magnitude: isManif ? 'normal' : ($('#sel-magnitude').value || 'normal'),
    description,
    capturedAt: state.capturedAt,
    captureNonce: state.nonce,
    clientId,
  };
}

async function submit() {
  $('#btn-submit').disabled = true;
  const payload = buildPayload();

  if (!navigator.onLine) {
    await enqueueOffline(payload);
    $('#btn-submit').disabled = false;
    return;
  }

  try {
    const res = await postReport(payload);
    showResult(res);
  } catch (err) {
    console.error(err);
    await enqueueOffline(payload);
  } finally {
    $('#btn-submit').disabled = false;
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
  $('#result-message').textContent =
    'Salvo no celular. Enviaremos automaticamente quando você estiver online.';
  $('#result-id').textContent = 'pendente';
}

function showResult(res) {
  hideAllSteps();
  show('#step-4');
  $('#result-message').textContent =
    res.message || 'Estamos analisando. Você pode fechar o app.';
  $('#result-id').textContent = res.id;
}

function resetForNext() {
  state.interactionType = null;
  state.category = null;
  state.description = '';
  state.photoBlob = null;
  state.withPhoto = false;
  if (state.photoPreviewUrl) URL.revokeObjectURL(state.photoPreviewUrl);
  state.photoPreviewUrl = null;
  state.nonce = null;
  state.mapInitialized = false;
  state.pickMap = null;
  $('#txt-desc').value = '';
  $('#txt-manif').value = '';
  $('#btn-step1-evento').disabled = true;
  $('#btn-step1-manifestacao').disabled = true;
  // Reset toggle de foto
  const toggleBtn = $('#btn-toggle-photo');
  if (toggleBtn) {
    toggleBtn.classList.remove('active');
    toggleBtn.setAttribute('aria-pressed', 'false');
  }
  const pill = $('#photo-toggle-pill');
  if (pill) pill.textContent = 'Não';
  const ico = $('#photo-toggle-icon');
  if (ico) ico.textContent = '📷';
  const desc = $('#photo-toggle-desc');
  if (desc) desc.textContent = 'Clique para abrir a câmera ao continuar';
  // Reset preview
  $('#preview-img').hidden = false;
  $('#no-photo-notice').hidden = true;
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
  for (const it of items) {
    try {
      const blob = new Blob([it.photoBuffer], { type: 'image/jpeg' });
      await postReport({
        ...it.payload,
        photoBlob: blob,
        offlineCapture: true,
        queuedAt: it.queuedAt,
      });
      await dequeue(it.localId);
      sent++;
    } catch (e) {
      console.warn('Fila: item falhou, continua depois', it.localId, e);
    }
  }
  await updateQueueBadge();
  if (sent > 0) toast(`${sent} reporte(s) enviado(s).`, 'ok');
}

function onFallbackFile(ev) {
  const f = ev.target.files && ev.target.files[0];
  if (!f) return;
  onPhoto(f);
}

function bindUI() {
  renderEventCategories();
  renderManifTypes();

  $('#branch-evento').addEventListener('click', () => startBranch('evento_trafego'));
  $('#branch-manifestacao').addEventListener('click', () => startBranch('manifestacao'));

  $('#btn-back-0').addEventListener('click', resetForNext);
  $('#btn-back-0b').addEventListener('click', resetForNext);

  $('#btn-step1-evento').addEventListener('click', openCameraStep);
  $('#btn-step1-manifestacao').addEventListener('click', () => {
    state.description = $('#txt-manif').value.trim();
    if (state.withPhoto) {
      openCameraStep();
    } else {
      openConfirmDirectly();
    }
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
