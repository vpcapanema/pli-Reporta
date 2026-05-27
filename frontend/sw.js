// Service Worker — cache mínimo para shell offline + fila de envio (Background Sync).
const VERSION = 'pli-reporta-v1';
const SHELL_CACHE = `shell-${VERSION}`;
const SHELL = [
  '/',
  '/static/styles.css',
  '/static/js/app.js',
  '/static/js/db.js',
  '/static/js/api.js',
  '/static/js/camera.js',
  '/static/js/map-pick.js',
  '/manifest.webmanifest',
  'https://unpkg.com/maplibre-gl@4.5.0/dist/maplibre-gl.css',
  'https://unpkg.com/maplibre-gl@4.5.0/dist/maplibre-gl.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      cache.addAll(SHELL.map((u) => new Request(u, { cache: 'reload' }))).catch(() => {})
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !k.endsWith(VERSION)).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Nunca interceptar POSTs (envio de reportes).
  if (request.method !== 'GET') return;

  // API: rede primeiro, sem cache (dados precisam ser frescos).
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request).catch(() => new Response('{"offline":true}', {
      status: 503, headers: { 'Content-Type': 'application/json' }
    })));
    return;
  }

  // Shell: cache primeiro com fallback de rede.
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((res) => {
      // Atualiza cache de shell em background.
      const copy = res.clone();
      if (res.ok && (SHELL.includes(url.pathname) || url.pathname.startsWith('/static/'))) {
        caches.open(SHELL_CACHE).then((c) => c.put(request, copy));
      }
      return res;
    }).catch(() => caches.match('/')))
  );
});

// Background Sync: dispara quando voltar conexão.
self.addEventListener('sync', (event) => {
  if (event.tag === 'pli-reporta-flush') {
    event.waitUntil(
      self.clients.matchAll().then((clients) => {
        clients.forEach((c) => c.postMessage({ type: 'flush-queue' }));
      })
    );
  }
});
