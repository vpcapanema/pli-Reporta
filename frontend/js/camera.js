// Captura de foto via getUserMedia. Fallback para <input capture> em browsers restritos.
import { canUseCamera, canUseGeolocation } from './device-capabilities.js';

export { canUseCamera, canUseGeolocation, isSecureReportContext } from './device-capabilities.js';

export async function startCamera(videoEl) {
  if (!canUseCamera()) {
    return { ok: false, reason: 'Câmera indisponível (exige HTTPS ou permissão)' };
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1600 }, height: { ideal: 1200 } },
      audio: false,
    });
    videoEl.srcObject = stream;
    await videoEl.play();
    return { ok: true, stream };
  } catch (err) {
    return { ok: false, reason: String(err) };
  }
}

export function stopCamera(stream) {
  if (!stream) return;
  stream.getTracks().forEach((t) => t.stop());
}

export async function captureFrame(videoEl, maxSide = 1600) {
  const w = videoEl.videoWidth;
  const h = videoEl.videoHeight;
  if (!w || !h) throw new Error('vídeo não pronto');
  const ratio = Math.min(1, maxSide / Math.max(w, h));
  const cw = Math.round(w * ratio);
  const ch = Math.round(h * ratio);
  const canvas = document.createElement('canvas');
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(videoEl, 0, 0, cw, ch);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85));
  if (!blob) throw new Error('falha ao gerar JPEG');
  return blob;
}

export async function getPositionOnce(timeoutMs = 12000) {
  if (!canUseGeolocation()) {
    throw new Error('Geolocation indisponível (exige HTTPS ou permissão)');
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
      }),
      (err) => reject(err),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 0 }
    );
  });
}
