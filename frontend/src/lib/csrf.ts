/** Shared CSRF header for cookie-authenticated writes. The token is not logged. */

export const CSRF_COOKIE = "madira_csrf";
export const CSRF_HEADER = "X-CSRF-Token";
export const CSRF_BLOCKED = "This request was blocked. Reload the page and try again.";

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

type CsrfRequest = {
  method: string;
  url: string;
  headers: { get(name: string): string | null };
};

export function apiPath(pathname: string): string {
  if (pathname === "/madira-api" || pathname.startsWith("/madira-api/")) {
    const rest = pathname.slice("/madira-api".length);
    return rest || "/";
  }
  return pathname;
}

/**
 * Routes that are not authenticated by the session cookie.
 * Keep these reasons in step with backend/madira/csrf.py.
 */
export function exemptionReason(pathname: string): string | null {
  const path = apiPath(pathname).replace(/\/$/, "") || "/";
  if (path === "/health") return "Unauthenticated liveness probe. It does not use a session cookie.";
  if (path === "/auth/google") return "OAuth start. The browser is sent to Google before a session exists.";
  if (path === "/auth/callback") {
    return "OAuth callback. Google redirects the browser here. The OIDC state cookie binds the request, not the session.";
  }
  if (path === "/sensors/webhook" || path.startsWith("/sensors/webhook/")) {
    return "Signed by the sensor secret. The venue comes from the sensor row, not a session cookie.";
  }
  if (path === "/public/lists" || path.startsWith("/public/lists/")) {
    return "Public read-only guest list. It does not use a session cookie.";
  }
  return null;
}

function normalizeOrigin(value: string): string {
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "";
    return `${url.protocol}//${url.host}`.toLowerCase();
  } catch {
    return "";
  }
}

function loopbackAliases(origin: string): string[] {
  const url = new URL(origin);
  const host = url.hostname.toLowerCase();
  if (host !== "localhost" && host !== "127.0.0.1") return [];
  const port = url.port ? `:${url.port}` : "";
  return [`${url.protocol}//localhost${port}`, `${url.protocol}//127.0.0.1${port}`];
}

export function allowedOrigins(requestHost?: string): Set<string> {
  const found = new Set<string>();
  const frontend = (process.env.MADIRA_FRONTEND_ORIGIN || "http://localhost:3000").replace(/\/$/, "");
  const normalized = normalizeOrigin(frontend);
  if (normalized) {
    found.add(normalized);
    for (const alias of loopbackAliases(normalized)) found.add(alias.toLowerCase());
  }
  const pub = (process.env.MADIRA_PUBLIC_URL || "").replace(/\/$/, "");
  const publicOrigin = normalizeOrigin(pub);
  if (publicOrigin) found.add(publicOrigin);
  for (const item of (process.env.MADIRA_CSRF_ORIGINS || "").split(",")) {
    const origin = normalizeOrigin(item.trim().replace(/\/$/, ""));
    if (origin) found.add(origin);
  }
  if (requestHost) {
    const hostOrigin = normalizeOrigin(requestHost);
    if (hostOrigin) found.add(hostOrigin);
  }
  return found;
}

function cookieValue(header: string, name: string): string {
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() === name) {
      const raw = part.slice(eq + 1).trim();
      try {
        return decodeURIComponent(raw);
      } catch {
        return raw;
      }
    }
  }
  return "";
}

function sameValue(left: string, right: string): boolean {
  if (!left || !right || left.length !== right.length) return false;
  let diff = 0;
  for (let index = 0; index < left.length; index += 1) {
    diff |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return diff === 0;
}

export function readCookie(name: string): string {
  if (typeof document === "undefined") return "";
  return cookieValue(document.cookie, name);
}

let csrfAttempt: Promise<string> | null = null;

export function ensureCsrfToken(): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return Promise.resolve(existing);
  if (!csrfAttempt) {
    csrfAttempt = fetch("/madira-api/auth/csrf", { credentials: "same-origin", cache: "no-store" })
      .then((res) => (res.ok ? readCookie(CSRF_COOKIE) : ""))
      .catch(() => "");
  }
  return csrfAttempt.then((token) => token || readCookie(CSRF_COOKIE));
}

export function csrfBlock(request: CsrfRequest, requestHost = ""): string | null {
  if (!MUTATING.has(request.method.toUpperCase())) return null;
  const path = new URL(request.url).pathname;
  if (exemptionReason(path)) return null;
  const originHeader = request.headers.get("origin");
  const referer = request.headers.get("referer");
  let origin = "";
  if (originHeader !== null) {
    if (originHeader.trim().toLowerCase() === "null") return "foreign_origin";
    origin = normalizeOrigin(originHeader);
    if (!origin) return "foreign_origin";
  } else if (referer) {
    origin = normalizeOrigin(referer);
    if (!origin) return "foreign_origin";
  }
  if (origin && !allowedOrigins(requestHost).has(origin)) return "foreign_origin";
  const cookies = request.headers.get("cookie") || "";
  const session = cookieValue(cookies, "madira_session");
  if (!session) return null;
  const header = request.headers.get(CSRF_HEADER) || "";
  const cookie = cookieValue(cookies, CSRF_COOKIE);
  if (!header || !cookie) return "missing_token";
  if (!sameValue(header, cookie)) return "bad_token";
  return null;
}
