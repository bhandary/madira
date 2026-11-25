"""CSRF checks for cookie-authenticated writes.

The session cookie is first-party and SameSite=Lax. A signed double-submit
token is still required when that cookie is present: the browser cannot set
the header from another site, and the token is an HMAC of the session cookie
so a forged cookie does not match. Origin or Referer must be one of the app
origins when the browser sends either. A missing Origin is allowed so a
non-browser client can call the API. The token value is never logged.

Exemptions are requests that are not authenticated by the session cookie.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("madira.csrf")

CSRF_COOKIE = "madira_csrf"
CSRF_HEADER = "x-csrf-token"
BLOCKED = "This request was blocked. Reload the page and try again."
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class Exemption:
    path: str
    reason: str


# Paths are matched on the backend path, after the Next.js `/madira-api` prefix.
EXEMPTIONS = (
    Exemption(
        "/health",
        "Unauthenticated liveness probe. It does not use a session cookie.",
    ),
    Exemption(
        "/auth/google",
        "OAuth start. The browser is sent to Google before a session exists.",
    ),
    Exemption(
        "/auth/callback",
        "OAuth callback. Google redirects the browser here. The OIDC state cookie binds the request, not the session.",
    ),
    Exemption(
        "/sensors/webhook/",
        "Signed by the sensor secret. The venue comes from the sensor row, not a session cookie.",
    ),
    Exemption(
        "/public/lists/",
        "Public read-only guest list. It does not use a session cookie.",
    ),
)


def _secret() -> bytes:
    raw = os.environ.get("MADIRA_AUTH_SECRET", "").strip()
    if not raw:
        return b""
    return hashlib.sha256(b"madira-csrf-v1" + raw.encode("utf-8")).digest()


def sign_csrf(session_token: str) -> str | None:
    """HMAC of the session cookie. None when there is nothing to sign."""

    secret = _secret()
    token = session_token or ""
    if not secret or not token:
        return None
    digest = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).digest()
    return _b64(digest)


def _b64(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _same(left: str, right: str) -> bool:
    if not left or not right or len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def _normalize_path(path: str) -> str:
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


def exemption_reason(path: str) -> str | None:
    cleaned = _normalize_path(path)
    for item in EXEMPTIONS:
        prefix = item.path
        if prefix.endswith("/"):
            base = prefix.rstrip("/")
            if cleaned == base or cleaned.startswith(prefix):
                return item.reason
        elif cleaned == prefix or cleaned.startswith(prefix + "/"):
            return item.reason
    return None


def _normalize_origin(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _loopback_aliases(origin: str) -> set[str]:
    parsed = urlparse(origin)
    host = (parsed.hostname or "").lower()
    if host not in {"localhost", "127.0.0.1"} or parsed.scheme not in {"http", "https"}:
        return set()
    port = f":{parsed.port}" if parsed.port else ""
    return {
        f"{parsed.scheme}://localhost{port}",
        f"{parsed.scheme}://127.0.0.1{port}",
    }


def allowed_origins() -> set[str]:
    """App origins. `MADIRA_CSRF_ORIGINS` adds more. It does not remove the defaults."""

    found: set[str] = set()
    frontend = os.environ.get("MADIRA_FRONTEND_ORIGIN", "http://localhost:3000").strip().rstrip("/")
    normalized = _normalize_origin(frontend)
    if normalized:
        found.add(normalized)
        found |= _loopback_aliases(normalized)
    public = os.environ.get("MADIRA_PUBLIC_URL", "").strip().rstrip("/")
    if _normalize_origin(public):
        found.add(_normalize_origin(public))
    for item in os.environ.get("MADIRA_CSRF_ORIGINS", "").split(","):
        origin = _normalize_origin(item.strip().rstrip("/"))
        if origin:
            found.add(origin)
    return found


def _origin_reason(request: Request) -> str | None:
    header = request.headers.get("origin")
    if header is None:
        referer = request.headers.get("referer")
        if not referer:
            return None
        header = _normalize_origin(referer)
        if not header:
            return "foreign_origin"
    else:
        if header.strip().lower() == "null":
            return "foreign_origin"
        header = _normalize_origin(header)
        if not header:
            return "foreign_origin"
    if header not in allowed_origins():
        return "foreign_origin"
    return None


def rejection_reason(request: Request) -> str | None:
    if request.method.upper() not in _MUTATING:
        return None
    path = request.url.path
    if exemption_reason(path):
        return None
    origin = _origin_reason(request)
    if origin:
        return origin
    from madira.auth import SESSION_COOKIE, session_subject

    session = request.cookies.get(SESSION_COOKIE) or ""
    # A cookie authenticates the request only when its signature still verifies.
    if not session_subject(session):
        return None
    header = request.headers.get(CSRF_HEADER) or ""
    cookie = request.cookies.get(CSRF_COOKIE) or ""
    if not header or not cookie:
        return "missing_token"
    expected = sign_csrf(session)
    if not expected or not _same(header, cookie) or not _same(header, expected):
        return "bad_token"
    return None


def reject(request: Request) -> JSONResponse | None:
    reason = rejection_reason(request)
    if reason is None:
        return None
    logger.warning("csrf rejected method=%s path=%s reason=%s", request.method, request.url.path, reason)
    return JSONResponse({"detail": BLOCKED}, status_code=403)
