// Orquestrador da tela de captura.
import { getOrCreateClientId, enqueue, listQueue, dequeue, newLocalId } from './db.js';
import { getCaptureNonce, postReport } from './api.js';
import { startCamera, stopCamera, captureFrame, getPositionOnce } from './camera.js';
import { createPickMap } from './map-pick.js';

const CATEGORIES = [
  { id: 'buraco',                 ico: 'BU', label: 'Buraco' },
  { id: 'alagamento',             ico: 'AL', label: 'Alagamento' },
  { id: 'acidente',               ico: 'AC', label: 'Acidente' },
  { id: 'bloqueio_total',         ico: 'BL', label: 'Bloqueio total' },
  { id: 'obra_grande',            ico: 'OB', label: 'Obra' },
  { id: 'lentidao_corredor',      ico: 'LE', label: 'Lentidão' },
  { id: 'sinalizacao_quebrada',   ico: 'SI', label: 'Sinalização' },
  { id: 'outro',                  ico: 'OU', label: 'Outro' },
];

const state = {
  category: null,
  magnitude: 'normal',
  description: '',
  position: null,
  accuracy: null,
  photoBlob: null,
  photoPreviewUrl: null,
  capturedAt: null,
  nonce: null,
  stream: null,
  pickMap: null,
};

const clientId = getOrCreateClientId();

function $(sel) { return document.querySelector(sel); }
function show(id) { $(id).hidden = false; }
function hide(id) { $(id).hidden = true; }

function toast(msg, type) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast show' + (type ? ' ' + type : '');
  setTimeout(() => t.classList.remove('show'), 3500);
}

function renderCategories() {
  const grid = $('#cat-grid');
  grid.innerHTML = '';
  for (const c of CATEGORIES) {
    const b = document.createElement('button');
    b.type = 'button';
    b.dataset.id = c.id;
    b.innerHTML = `<span class="ico">${c.ico}</span><span>${c.label}</span>`;
    b.addEventListener('click', () => selectCategory(c.id));
    grid.appendChild(b);
  }
}

function selectCategory(id) {
  state.category = id;
  document.querySelectorAll('#cat-grid button').forEach((b) => {
    b.classList.toggle('selected', b.dataset.id === id);
  });
  $('#btn-step1').disabled = false;
}

async function step1Next() {
  // Pede nonce e GPS em paralelo, depois inicia câmera.
  show('#step-2'); hide('#step-1');
  $('#status-line').textContent = 'Buscando GPS e preparando câmera…';
  try {
    const [nonceRes, pos] = await Promise.all([
      getCaptureNonce(clientId).catch(() => null),
      getPositionOnce().catch((e) => { throw e; }),
    ]);
    state.nonce = nonceRes ? nonceRes.nonce : null;
    state.position = { lat: pos.lat, lon: pos.lon };
    state.accuracy = pos.accuracy;
    $('#gps-line').textContent = `GPS: ${pos.lat.toFixed(5)}, ${pos.lon.toFixed(5)} (±${Math.round(pos.accuracy)} m)`;
  } catch (err) {
    $('#gps-line').textContent = 'Não foi possível obter GPS. Você poderá ajustar no mapa.';
    state.position = { lat: -23.55, lon: -46.63 }; // fallback SP
  }

  const video = $('#cam-video');
  const cam = await startCamera(video);
  if (cam.ok) {
    state.stream = cam.stream;
    $('#cam-status').textContent = 'Câmera ativa';
    $('#btn-shoot').disabled = false;
    $('#fallback-input').hidden = true;
  } else {
    $('#cam-status').textContent = 'Câmera não disponível, use o botão abaixo.';
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
  show('#step-3'); hide('#step-2');
  stopCamera(state.stream);
  state.stream = null;
  initPickMap();
}

function initPickMap() {
  if (state.pickMap) return;
  state.pickMap = createPickMap('pickmap', state.position, (pt) => {
    state.position = pt;
    $('#picked-line').textContent = `Local ajustado: ${pt.lat.toFixed(5)}, ${pt.lon.toFixed(5)}`;
  });
}

async function submit() {
  $('#btn-submit').disabled = true;
  const payload = {
    photoBlob: state.photoBlob,
    lat: state.position.lat,
    lon: state.position.lon,
    accuracy: state.accuracy,
    category: state.category,
    magnitude: $('#sel-magnitude').value,
    description: $('#txt-desc').value.trim(),
    capturedAt: state.capturedAt,
    captureNonce: state.nonce,
    clientId,
  };

  if (!navigator.onLine) {
    await enqueueOffline(payload);
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
  // Converte Blob em ArrayBuffer para guardar em IndexedDB.
  const buf = await payload.photoBlob.arrayBuffer();
  await enqueue({
    localId: newLocalId(),
    photoBuffer: buf,
    payload: { ...payload, photoBlob: undefined },
    queuedAt: new Date().toISOString(),
  });
  toast('Sem conexão — reporte salvo na fila e enviará quando voltar.', 'warn');
  resetForNext();

  // Tenta registrar background sync.
  if ('serviceWorker' in navigator && 'SyncManager' in window) {
    try {
      const reg = await navigator.serviceWorker.ready;
      await reg.sync.register('pli-reporta-flush');
    } catch (_) {}
  }
}

async function flushQueue() {
  const items = await listQueue();
  if (items.length === 0) return;
  for (const it of items) {
    try {
      const blob = new Blob([it.photoBuffer], { type: 'image/jpeg' });
      await postReport({ ...it.payload, photoBlob: blob });
      await dequeue(it.localId);
    } catch (e) {
      // Falhou — para e tenta depois.
      return;
    }
  }
  toast('Fila enviada com sucesso.', 'ok');
}

function showResult(res) {
  hide('#step-3');
  show('#step-4');
  const badge = res.status === 'validado' ? 'ok'
    : res.status === 'em_moderacao' ? 'warn' : 'err';
  $('#result-status').className = 'badge ' + badge;
  $('#result-status').textContent = res.status.replace('_', ' ');
  $('#result-id').textContent = res.id;
  $('#result-v').textContent = res.veracity_score.toFixed(2);
  $('#result-r').textContent = res.relevance_score.toFixed(2);
  $('#result-p').textContent = res.priority.toFixed(2);
  const ul = $('#result-explain'); ul.innerHTML = '';
  res.explanation.forEach((line) => {
    const li = document.createElement('li');
    li.textContent = line;
    ul.appendChild(li);
  });
}

function resetForNext() {
  state.category = null;
  state.photoBlob = null;
  if (state.photoPreviewUrl) URL.revokeObjectURL(state.photoPreviewUrl);
  state.photoPreviewUrl = null;
  $('#cat-grid').querySelectorAll('button').forEach((b) => b.classList.remove('selected'));
  $('#txt-desc').value = '';
  $('#btn-step1').disabled = true;
  hide('#step-2'); hide('#step-3'); hide('#step-4');
  show('#step-1');
}

function onFallbackFile(ev) {
  const f = ev.target.files && ev.target.files[0];
  if (!f) return;
  onPhoto(f);
}

function bindUI() {
  renderCategories();
  $('#btn-step1').addEventListener('click', step1Next);
  $('#btn-shoot').addEventListener('click', shoot);
  $('#fallback-input').addEventListener('change', onFallbackFile);
  $('#btn-submit').addEventListener('click', submit);
  $('#btn-new').addEventListener('click', resetForNext);
  $('#btn-back').addEventListener('click', () => {
    stopCamera(state.stream);
    state.stream = null;
    hide('#step-2'); show('#step-1');
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
  flushQueue();
});
