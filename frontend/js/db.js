// IndexedDB para fila de envio offline. Sem dependência externa.
const DB_NAME = 'pli-reporta';
const DB_VERSION = 1;
const STORE = 'queue';

let _dbPromise = null;

function openDb() {
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'localId' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return _dbPromise;
}

export async function enqueue(item) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(item);
    tx.oncomplete = () => resolve(item);
    tx.onerror = () => reject(tx.error);
  });
}

export async function dequeue(localId) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete(localId);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function listQueue() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

export async function queueSize() {
  const items = await listQueue();
  return items.length;
}

export function newLocalId() {
  return 'q_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
}

export function getOrCreateClientId() {
  const k = 'pli-reporta-client-id';
  let id = localStorage.getItem(k);
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) ||
         ('c_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10));
    localStorage.setItem(k, id);
  }
  return id;
}
