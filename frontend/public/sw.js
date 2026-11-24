/* Madira floor cache. Network-first for the briefing and the lookup pack.
   Cache-first for static assets. Non-GET requests and Settings are never stored. */

const VERSION = "madira-pwa-2";

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("madira-pwa-") && key !== VERSION)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (!event.data || event.data.type !== "SIGN_OUT") return;
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith("madira-")).map((key) => caches.delete(key)))),
  );
});

function isPrefetch(request) {
  return request.headers.get("next-router-prefetch") === "1" || request.headers.get("purpose") === "prefetch";
}

function isSettings(url) {
  const path = url.pathname;
  return path === "/settings" || path.startsWith("/settings/") || path === "/madira-api/settings" || path.startsWith("/madira-api/settings/");
}

function isFloorData(url) {
  return url.pathname === "/madira-api/tonight/briefing" || url.pathname === "/madira-api/lookup/pack";
}

function isStatic(url) {
  if (url.pathname === "/sw.js") return false;
  if (url.pathname.startsWith("/_next/static/")) return true;
  if (url.pathname.startsWith("/icons/")) return true;
  return /\.(?:js|css|png|jpg|jpeg|webp|svg|ico|woff2?|map)$/i.test(url.pathname);
}

function storageRequest(request) {
  const url = new URL(request.url);
  url.searchParams.delete("_rsc");
  const accept = request.headers.get("accept") || "";
  if (request.headers.get("rsc") === "1" || accept.includes("text/x-component")) {
    url.searchParams.set("__madira_rsc", "1");
    const from = request.headers.get("next-url");
    if (from) url.searchParams.set("__madira_from", from);
  }
  if (url.toString() === request.url && request.headers.get("rsc") !== "1") return request;
  return new Request(url.toString(), { method: "GET" });
}

async function forCache(response) {
  const headers = new Headers(response.headers);
  headers.delete("cache-control");
  headers.delete("set-cookie");
  headers.delete("content-encoding");
  headers.delete("content-length");
  headers.delete("transfer-encoding");
  const body = await response.blob();
  return new Response(body, { status: response.status, statusText: response.statusText, headers });
}

async function remember(cache, request, response) {
  if (!response || response.status !== 200) return;
  const key = storageRequest(request);
  if (await cache.match(key)) return;
  try {
    await cache.put(key, await forCache(response.clone()));
  } catch (error) {
    // The page still receives the network response when a body cannot be stored.
  }
}

async function fromNetwork(request) {
  const cache = await caches.open(VERSION);
  const response = await fetch(request);
  await remember(cache, request, response);
  return response;
}

async function networkFirst(request) {
  const cache = await caches.open(VERSION);
  const cached = await cache.match(storageRequest(request));
  let timer;
  const expired = cached
    ? new Promise((resolve) => {
        timer = setTimeout(() => resolve(cached), 1200);
      })
    : null;
  try {
    const response = await Promise.race([fromNetwork(request), expired].filter(Boolean));
    return response;
  } catch (error) {
    if (cached) return cached;
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(VERSION);
  const cached = await cache.match(storageRequest(request));
  if (cached) return cached;
  if (!navigator.onLine) return new Response("", { status: 503, statusText: "offline" });
  return fromNetwork(request);
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname === "/sw.js") return;
  if (isSettings(url) || isPrefetch(request)) return;
  if (isStatic(url)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (isFloorData(url) || request.mode === "navigate" || url.pathname.startsWith("/_next/") || !url.pathname.startsWith("/madira-api/")) {
    event.respondWith(networkFirst(request));
  }
});
