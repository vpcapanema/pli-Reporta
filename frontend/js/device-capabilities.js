/** GPS e câmera exigem contexto seguro (HTTPS ou localhost). */
export function isSecureReportContext() {
  return window.isSecureContext === true;
}

export function canUseGeolocation() {
  return isSecureReportContext() && 'geolocation' in navigator;
}

export function canUseCamera() {
  return (
    isSecureReportContext() &&
    !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)
  );
}

export function deviceCapabilitiesMessage() {
  if (isSecureReportContext()) return null;
  return (
    'GPS e câmera do navegador só funcionam com HTTPS (ou em localhost). ' +
    'Na VM, o administrador deve habilitar TLS — veja .deploy/enable_https_vm.sh. ' +
    'Enquanto isso, use o mapa para ajustar o local; a foto pode ser capturada pelo botão alternativo.'
  );
}
