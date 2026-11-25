const cacheName = 'agrosphere-notebook-v1';
const files = [
  '/offline-farm.html', '/farm-notebook.css', '/farm-notebook.js',
  '/farm-notebook.webmanifest', '/farm-notebook-192.png', '/farm-notebook-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(cacheName).then(cache => cache.addAll(files)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(
    key => key.startsWith('agrosphere-notebook-') && key !== cacheName
  ).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const {request} = event;
  const url = new URL(request.url);
  if (request.method === 'GET' && url.origin === self.location.origin && files.includes(url.pathname)) {
    event.respondWith(caches.open(cacheName).then(cache => cache.match(url.pathname)).then(hit => hit || fetch(request)));
  }
});
