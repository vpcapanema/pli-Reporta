// Service Worker — SEM cache. Tudo é servido direto da rede.
// Mantém apenas o background sync da fila offline.

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Sem handler de 'fetch': o navegador faz todas as requisições normalmente,
// sempre buscando a versão atual de HTML, CSS e JS no servidor.

self.addEventListener('sync', (event) => {
  if (event.tag === 'pli-reporta-flush') {
    event.waitUntil(
      self.clients.matchAll().then((clients) => {
        clients.forEach((c) => c.postMessage({ type: 'flush-queue' }));
      }),
    );
  }
});
