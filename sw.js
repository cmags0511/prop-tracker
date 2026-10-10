// Prop Tracker service worker: app works offline, data is always fetched fresh when online.
const VERSION = "pt-v42";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icons/icon-192.png", "./icons/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const same = url.origin === self.location.origin;
  // Live APIs (ESPN live box scores, etc.): never cache, let the browser go straight to the network.
  if (!same && !/fonts\.(googleapis|gstatic)\.com|cdnjs\.cloudflare\.com/.test(url.host)) return;
  // The page and every data file: network first so updates show immediately, cache as a fallback offline.
  if (same && (url.pathname.endsWith(".json") || url.pathname.endsWith(".gz") || req.mode === "navigate")) {
    e.respondWith(fetch(req, { cache: "no-store" }).then(res => {
      const copy = res.clone(); caches.open(VERSION).then(c => c.put(req, copy)); return res;
    }).catch(() => caches.match(req).then(r => r || caches.match("./index.html"))));
    return;
  }
  // Fonts, icons and libraries: cache first.
  e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(res => {
    if (res.ok || res.type === "opaque") { const copy = res.clone(); caches.open(VERSION).then(c => c.put(req, copy)); }
    return res;
  })));
});
