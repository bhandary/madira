/** Service-worker registration and the versioned offline caches. */

const CACHE_PREFIX = "madira-";

export function serviceWorkerRequested(): boolean {
  if (typeof document === "undefined") return false;
  if (process.env.NODE_ENV === "production") return true;
  return document.cookie.split(";").some((part) => part.trim() === "madira_sw=1");
}

export function registerServiceWorker(): void {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
  if (!serviceWorkerRequested()) return;
  void navigator.serviceWorker.register("/sw.js").catch(() => {
    // The floor still works when the worker cannot install.
  });
}

export async function clearOfflineCaches(): Promise<void> {
  if (typeof window === "undefined") return;
  const worker = navigator.serviceWorker?.controller;
  worker?.postMessage({ type: "SIGN_OUT" });
  if (typeof caches === "undefined") return;
  const keys = await caches.keys();
  await Promise.all(keys.filter((key) => key.startsWith(CACHE_PREFIX)).map((key) => caches.delete(key)));
}

export async function readCachedJson<T>(path: string): Promise<T | null> {
  if (typeof caches === "undefined") return null;
  const keys = await caches.keys();
  for (const key of keys) {
    if (!key.startsWith(CACHE_PREFIX)) continue;
    const cache = await caches.open(key);
    const hit = await cache.match(path);
    if (!hit) continue;
    try {
      return (await hit.json()) as T;
    } catch {
      return null;
    }
  }
  return null;
}
