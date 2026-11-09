"""Google OpenID Connect sign-in and the first-party session cookie.

The browser only talks to the Next.js origin. `/madira-api/*` is rewritten to
this service, so the redirect URI registered in Google Cloud is on the public
site (`{MADIRA_PUBLIC_URL}/madira-api/auth/callback`) and the session cookie
is first-party: HttpOnly, SameSite=Lax, and Secure when that URL is https.

The flow is the authorization code grant with S256 PKCE, `state`, and
`nonce`. joserfc checks the ID token (RS256, issuer, audience, expiry,
nonce) before a User row is written. The cookie is an HMAC of the Google
subject, not the Google token. Settings stays on `MADIRA_ADMIN_PASSWORD`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, MissingKeyError
from joserfc.jwk import KeySet
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from madira.db import SessionLocal
from madira.models import User

logger = logging.getLogger("madira")

router = APIRouter()

GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

SESSION_COOKIE = "madira_session"
OIDC_COOKIE = "madira_oidc"
SESSION_TTL = 14 * 24 * 60 * 60
OIDC_TTL = 10 * 60
LEEWAY = 60
_RETRYABLE = (InvalidKeyIdError, MissingKeyError)
_ERRORS = {"denied", "state", "token", "id_token", "not_configured", "server"}
_PICTURE_HOSTS = ("googleusercontent.com", "ggpht.com")

_jwks_cache: dict[str, Any] = {"exp": 0, "body": None}


class AuthError(Exception):
    def __init__(self, code: str):
        self.code = code if code in _ERRORS else "server"
        super().__init__(self.code)


def _now() -> int:
    return int(time.time())


def utcnow() -> datetime:
    return datetime.fromtimestamp(_now(), timezone.utc).replace(tzinfo=None)


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def client_id() -> str:
    return _env("GOOGLE_CLIENT_ID")


def client_secret() -> str:
    return _env("GOOGLE_CLIENT_SECRET")


def auth_secret() -> str:
    return _env("MADIRA_AUTH_SECRET")


def public_url() -> str:
    raw = _env("MADIRA_PUBLIC_URL")
    if not raw:
        return ""
    parsed = urlparse(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def redirect_uri() -> str:
    return public_url() + "/madira-api/auth/callback"


def google_configured() -> bool:
    return bool(client_id() and client_secret() and auth_secret() and public_url())


def cookie_secure() -> bool:
    return public_url().startswith("https://")


def clear_jwks_cache() -> None:
    _jwks_cache["exp"] = 0
    _jwks_cache["body"] = None


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: bytes, purpose: bytes) -> str:
    secret = auth_secret()
    if not secret:
        raise AuthError("not_configured")
    key = hashlib.sha256(purpose + secret.encode("utf-8")).digest()
    signature = hmac.new(key, payload, hashlib.sha256).digest()
    return _b64e(payload) + "." + _b64e(signature)


def _read(token: str, purpose: bytes) -> dict[str, Any] | None:
    secret = auth_secret()
    if not secret or not token or token.count(".") != 1:
        return None
    payload_b64, signature_b64 = token.split(".", 1)
    try:
        payload = _b64d(payload_b64)
        signature = _b64d(signature_b64)
    except (ValueError, TypeError):
        return None
    key = hashlib.sha256(purpose + secret.encode("utf-8")).digest()
    expected = hmac.new(key, payload, hashlib.sha256).digest()
    if len(signature) != len(expected) or not hmac.compare_digest(signature, expected):
        return None
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _eq(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def _pkce_challenge(verifier: str) -> str:
    return _b64e(hashlib.sha256(verifier.encode("ascii")).digest())


def post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, data=data)
    except httpx.HTTPError:
        raise AuthError("token") from None
    if response.status_code != 200:
        logger.info("google token endpoint status %s", response.status_code)
        raise AuthError("token")
    try:
        body = response.json()
    except ValueError:
        raise AuthError("token") from None
    if not isinstance(body, dict):
        raise AuthError("token")
    return body


def get_json(url: str) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
    except httpx.HTTPError:
        raise AuthError("id_token") from None
    if response.status_code != 200:
        logger.info("google jwks status %s", response.status_code)
        raise AuthError("id_token")
    try:
        body = response.json()
    except ValueError:
        raise AuthError("id_token") from None
    if not isinstance(body, dict):
        raise AuthError("id_token")
    return body


def load_jwks() -> dict[str, Any]:
    now = _now()
    cached = _jwks_cache["body"]
    if isinstance(cached, dict) and int(_jwks_cache["exp"]) > now:
        return cached
    fresh = get_json(GOOGLE_JWKS)
    if not isinstance(fresh.get("keys"), list):
        raise AuthError("id_token")
    _jwks_cache["body"] = fresh
    _jwks_cache["exp"] = now + 3600
    return fresh


def _picture(value: object) -> str:
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw or len(raw) > 2048:
        return ""
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    allowed = host in _PICTURE_HOSTS or any(host.endswith("." + suffix) for suffix in _PICTURE_HOSTS)
    if parsed.scheme != "https" or not allowed or parsed.username or parsed.password:
        return ""
    return raw


def _profile(claims: dict[str, Any]) -> dict[str, str]:
    sub = claims.get("sub")
    email = claims.get("email")
    if not isinstance(sub, str) or not sub or len(sub) > 255 or any(ch.isspace() for ch in sub):
        raise AuthError("id_token")
    if claims.get("email_verified") is not True:
        raise AuthError("id_token")
    if not isinstance(email, str) or "@" not in email or len(email) > 320:
        raise AuthError("id_token")
    name = " ".join(str(claims.get("name") or "").split())[:200]
    return {
        "sub": sub,
        "email": email.strip().lower(),
        "name": name,
        "picture": _picture(claims.get("picture")),
    }


def verify_id_token(token: str, *, nonce: str) -> dict[str, str]:
    if not isinstance(token, str) or token.count(".") != 2 or len(token) > 16000:
        raise AuthError("id_token")
    if not nonce:
        raise AuthError("id_token")
    for attempt in (1, 2):
        try:
            keys = KeySet.import_key_set(load_jwks())
            decoded = jwt.decode(token, keys, algorithms=["RS256"])
            claims = dict(decoded.claims)
            jwt.JWTClaimsRegistry(
                now=_now,
                leeway=LEEWAY,
                iss={"essential": True, "values": list(GOOGLE_ISSUERS)},
                aud={"essential": True, "value": client_id()},
                exp={"essential": True},
                iat={"essential": True},
                sub={"essential": True},
                nonce={"essential": True, "value": nonce},
            ).validate(claims)
            return _profile(claims)
        except AuthError:
            raise
        except _RETRYABLE:
            clear_jwks_cache()
            if attempt == 2:
                raise AuthError("id_token") from None
        except Exception:
            raise AuthError("id_token") from None
    raise AuthError("id_token")


def upsert_google_user(profile: dict[str, str]) -> str:
    sub = profile["sub"]
    now = utcnow()
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.google_sub == sub))
        if user is None:
            user = User(
                google_sub=sub,
                email=profile["email"],
                name=profile["name"],
                picture=profile["picture"],
                created_at=now,
                last_login_at=now,
            )
            session.add(user)
            try:
                session.commit()
                return sub
            except IntegrityError:
                session.rollback()
                user = session.scalar(select(User).where(User.google_sub == sub))
                if user is None:
                    raise AuthError("server") from None
        user.email = profile["email"]
        user.name = profile["name"]
        user.picture = profile["picture"]
        user.last_login_at = now
        session.commit()
        return sub
    except AuthError:
        raise
    except Exception:
        session.rollback()
        logger.info("google user upsert failed")
        raise AuthError("server") from None
    finally:
        session.close()


def issue_session(google_sub: str) -> str:
    payload = json.dumps({"sub": google_sub, "exp": _now() + SESSION_TTL}, separators=(",", ":")).encode("utf-8")
    return _sign(payload, b"madira-session-v1")


def user_from_session(token: str | None) -> dict[str, str] | None:
    if not google_configured() or not token:
        return None
    data = _read(token, b"madira-session-v1")
    if not data:
        return None
    try:
        exp = int(data.get("exp", 0))
    except (TypeError, ValueError):
        return None
    if exp < _now():
        return None
    sub = data.get("sub")
    if not isinstance(sub, str) or not sub:
        return None
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.google_sub == sub))
        if user is None:
            return None
        return {"name": user.name, "email": user.email, "picture": user.picture}
    finally:
        session.close()


def begin_google_login() -> tuple[str, str]:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    query = urlencode(
        {
            "client_id": client_id(),
            "redirect_uri": redirect_uri(),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    ticket = json.dumps(
        {"state": state, "nonce": nonce, "verifier": verifier, "exp": _now() + OIDC_TTL},
        separators=(",", ":"),
    ).encode("utf-8")
    return GOOGLE_AUTHORIZE + "?" + query, _sign(ticket, b"madira-oidc-v1")


def finish_google_login(*, code: str, state: str, ticket: str) -> str:
    if not google_configured():
        raise AuthError("not_configured")
    saved = _read(ticket, b"madira-oidc-v1")
    if not saved:
        raise AuthError("state")
    try:
        exp = int(saved.get("exp", 0))
    except (TypeError, ValueError):
        raise AuthError("state") from None
    if exp < _now():
        raise AuthError("state")
    expected_state = saved.get("state")
    nonce = saved.get("nonce")
    verifier = saved.get("verifier")
    if not isinstance(expected_state, str) or not isinstance(nonce, str) or not isinstance(verifier, str):
        raise AuthError("state")
    if not _eq(state, expected_state):
        raise AuthError("state")
    if not code:
        raise AuthError("token")
    token = post_form(
        GOOGLE_TOKEN,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
            "client_id": client_id(),
            "client_secret": client_secret(),
            "code_verifier": verifier,
        },
    )
    id_token = token.get("id_token")
    if not isinstance(id_token, str):
        raise AuthError("id_token")
    profile = verify_id_token(id_token, nonce=nonce)
    return issue_session(upsert_google_user(profile))


def _no_store(response: JSONResponse | RedirectResponse) -> JSONResponse | RedirectResponse:
    response.headers["Cache-Control"] = "no-store"
    return response


def _set_cookie(response: JSONResponse | RedirectResponse, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def _clear_cookie(response: JSONResponse | RedirectResponse, name: str) -> None:
    response.delete_cookie(name, path="/", secure=cookie_secure(), httponly=True, samesite="lax")


def _fail(code: str) -> RedirectResponse:
    safe = code if code in _ERRORS else "server"
    response = RedirectResponse(f"/login?error={safe}", status_code=302)
    _clear_cookie(response, OIDC_COOKIE)
    _no_store(response)
    return response


@router.get("/auth/config")
def auth_config() -> JSONResponse:
    return _no_store(JSONResponse({"configured": google_configured()}))


@router.get("/auth/me")
def auth_me(request: Request) -> JSONResponse:
    return _no_store(JSONResponse({"user": user_from_session(request.cookies.get(SESSION_COOKIE))}))


@router.post("/auth/logout")
def auth_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    _clear_cookie(response, SESSION_COOKIE)
    _clear_cookie(response, OIDC_COOKIE)
    return _no_store(response)


@router.get("/auth/google")
def auth_google() -> RedirectResponse:
    if not google_configured():
        return _fail("not_configured")
    url, ticket = begin_google_login()
    response = RedirectResponse(url, status_code=302)
    _set_cookie(response, OIDC_COOKIE, ticket, OIDC_TTL)
    return _no_store(response)


@router.get("/auth/callback")
def auth_callback(request: Request, code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    if not google_configured():
        return _fail("not_configured")
    if error:
        return _fail("denied" if error == "access_denied" else "token")
    if len(state) > 512:
        return _fail("state")
    if len(code) > 2048:
        return _fail("token")
    try:
        session_token = finish_google_login(code=code, state=state, ticket=request.cookies.get(OIDC_COOKIE, ""))
    except AuthError as exc:
        logger.info("google sign-in rejected: %s", exc.code)
        return _fail(exc.code)
    response = RedirectResponse("/", status_code=302)
    _set_cookie(response, SESSION_COOKIE, session_token, SESSION_TTL)
    _clear_cookie(response, OIDC_COOKIE)
    return _no_store(response)
