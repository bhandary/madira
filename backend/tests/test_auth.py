"""Google sign-in: user create/update, ID tokens, and the session cookie.

The token endpoint and JWKS are fakes. Nothing in this module opens a socket
to Google.
"""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey
from sqlalchemy import delete, func, select

from madira.auth import GOOGLE_JWKS, GOOGLE_TOKEN, clear_jwks_cache
from madira.db import SessionLocal, init_db
from madira.main import app
from madira.models import User

CLIENT_ID = "client-id"
CLIENT_SECRET = "client-secret"
AUTH_SECRET = "test-auth-secret-value"
PUBLIC_URL = "http://localhost:3000"
REDIRECT = PUBLIC_URL + "/madira-api/auth/callback"
PICTURE = "https://lh3.googleusercontent.com/a/ada"
PICTURE_NEXT = "https://lh3.googleusercontent.com/a/ada-2"

_key = RSAKey.generate_key(2048)
_private = _key.as_dict(private=True)
_private["kid"] = "madira-test"
SIGNING = RSAKey.import_key(_private)
PUBLIC = _key.as_dict(private=False)
PUBLIC["kid"] = "madira-test"


def _blocked(*_args, **_kwargs):
    raise AssertionError("Google was contacted")


@pytest.fixture(autouse=True)
def _no_google(monkeypatch):
    monkeypatch.setattr("madira.auth.post_form", _blocked)
    monkeypatch.setattr("madira.auth.get_json", _blocked)
    clear_jwks_cache()
    yield
    clear_jwks_cache()


@pytest.fixture(autouse=True)
def _users():
    init_db()
    _wipe()
    yield
    _wipe()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    monkeypatch.setenv("MADIRA_PUBLIC_URL", PUBLIC_URL)


def _wipe() -> None:
    session = SessionLocal()
    try:
        session.execute(delete(User))
        session.commit()
    finally:
        session.close()


def _load(sub: str = "google-sub-1"):
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.google_sub == sub))
        if user is None:
            return None
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
        }
    finally:
        session.close()


def _count() -> int:
    session = SessionLocal()
    try:
        return int(session.scalar(select(func.count()).select_from(User)) or 0)
    finally:
        session.close()


def _s256(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")


def _id_token(nonce: str, **overrides) -> str:
    from madira.auth import _now

    now = _now()
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-sub-1",
        "email": "Ada@Example.com",
        "email_verified": True,
        "name": "  Ada   Lovelace  ",
        "picture": PICTURE,
        "nonce": nonce,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode({"alg": "RS256", "kid": "madira-test", "typ": "JWT"}, claims, SIGNING)


def _cookie(response, name: str) -> tuple[str, str]:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(name + "="):
            value, _, flags = header.partition(";")
            return value.split("=", 1)[1], flags.lower()
    raise AssertionError(f"{name} cookie missing: {response.headers.get_list('set-cookie')}")


def _start(client: TestClient):
    response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert CLIENT_SECRET not in location
    query = parse_qs(urlparse(location).query)
    value, flags = _cookie(response, "madira_oidc")
    assert "httponly" in flags
    assert "samesite=lax" in flags
    assert "secure" not in flags
    assert "path=/" in flags
    return response, query, value


def test_unconfigured_sign_in_does_not_crash(client: TestClient, monkeypatch):
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "MADIRA_AUTH_SECRET", "MADIRA_PUBLIC_URL"):
        monkeypatch.delenv(name, raising=False)
    assert client.get("/auth/config").json() == {"configured": False}
    start = client.get("/auth/google", follow_redirects=False)
    assert start.status_code == 302
    assert start.headers["location"] == "/login?error=not_configured"
    assert client.get("/auth/me").json() == {"user": None}
    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    assert logout.json() == {"ok": True}

    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "  ")
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    monkeypatch.setenv("MADIRA_PUBLIC_URL", "http://localhost:3000/extra")
    assert client.get("/auth/config").json()["configured"] is False


def test_authorize_request_uses_pkce_state_and_nonce(client: TestClient, configured):
    _response, query, _cookie_value = _start(client)
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid email profile"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"][0]
    assert query["nonce"][0]
    assert query["code_challenge"][0]
    assert "client_secret" not in query


def test_secure_cookie_and_production_redirect(client: TestClient, configured, monkeypatch):
    monkeypatch.setenv("MADIRA_PUBLIC_URL", "https://madira-web-production.up.railway.app")
    response = client.get("/auth/google", follow_redirects=False)
    _value, flags = _cookie(response, "madira_oidc")
    assert "secure" in flags
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["redirect_uri"] == ["https://madira-web-production.up.railway.app/madira-api/auth/callback"]


def test_first_sign_in_creates_user_and_later_sign_in_updates_it(client: TestClient, configured, monkeypatch):
    clock = {"t": 1_700_000_000}
    monkeypatch.setattr("madira.auth._now", lambda: clock["t"])

    def finish(nonce: str, **claims):
        token = _id_token(nonce, **claims)

        def post(url, data):
            assert url == GOOGLE_TOKEN
            assert _s256(data["code_verifier"]) == query["code_challenge"][0]
            assert data["grant_type"] == "authorization_code"
            assert data["code"] == "auth-code"
            assert data["client_id"] == CLIENT_ID
            assert data["client_secret"] == CLIENT_SECRET
            assert data["redirect_uri"] == REDIRECT
            return {"id_token": token, "access_token": "should-not-leak"}

        def jwks(url):
            assert url == GOOGLE_JWKS
            return {"keys": [PUBLIC]}

        monkeypatch.setattr("madira.auth.post_form", post)
        monkeypatch.setattr("madira.auth.get_json", jwks)
        response = client.get(
            "/auth/callback",
            params={"code": "auth-code", "state": query["state"][0]},
            cookies={"madira_oidc": oidc},
            follow_redirects=False,
        )
        assert "should-not-leak" not in response.headers.get("location", "")
        assert "should-not-leak" not in response.text
        assert CLIENT_SECRET not in response.text
        assert token not in "".join(response.headers.get_list("set-cookie"))
        return response

    _response, query, oidc = _start(client)
    created = finish(query["nonce"][0])
    assert created.status_code == 302
    assert created.headers["location"] == "/"
    session_value, session_flags = _cookie(created, "madira_session")
    assert "httponly" in session_flags
    assert "samesite=lax" in session_flags
    row = _load()
    assert row is not None
    assert row["email"] == "ada@example.com"
    assert row["name"] == "Ada Lovelace"
    assert row["picture"] == PICTURE
    assert row["created_at"] == row["last_login_at"]
    me = client.get("/auth/me", cookies={"madira_session": session_value})
    assert me.json() == {"user": {"name": "Ada Lovelace", "email": "ada@example.com", "picture": PICTURE}}
    assert "google-sub-1" not in me.text

    clock["t"] += 120
    _response, query, oidc = _start(client)
    updated = finish(
        query["nonce"][0],
        email="ADA.L@example.com",
        name="Ada L.",
        picture=PICTURE_NEXT,
    )
    assert updated.status_code == 302
    again = _load()
    assert again is not None
    assert _count() == 1
    assert again["id"] == row["id"]
    assert again["created_at"] == row["created_at"]
    assert again["last_login_at"] > row["last_login_at"]
    assert again["email"] == "ada.l@example.com"
    assert again["name"] == "Ada L."
    assert again["picture"] == PICTURE_NEXT


def test_state_mismatch_does_not_call_google(client: TestClient, configured, monkeypatch):
    _response, query, oidc = _start(client)

    def post(*_args, **_kwargs):
        raise AssertionError("token endpoint called")

    monkeypatch.setattr("madira.auth.post_form", post)
    response = client.get(
        "/auth/callback",
        params={"code": "auth-code", "state": "not-the-state"},
        cookies={"madira_oidc": oidc},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=state"
    assert _count() == 0
    assert query["state"][0] != "not-the-state"


def test_rejected_id_tokens_do_not_create_a_user(client: TestClient, configured, monkeypatch):
    cases = [
        {"email_verified": False},
        {"email_verified": "true"},
        {"iss": "https://evil.example"},
        {"aud": "other-client"},
        {"nonce": "wrong-nonce"},
        {"exp_delta": -120},
        {"sub": "has a space"},
    ]
    dropped_pictures = ("javascript:alert(1)", "https://evil.example/a.png", "http://lh3.googleusercontent.com/a/ada")

    def run(**overrides):
        _response, query, oidc = _start(client)
        nonce = query["nonce"][0]
        token_nonce = nonce
        if "nonce" in overrides:
            token_nonce = overrides.pop("nonce")
        exp_delta = overrides.pop("exp_delta", None)
        if exp_delta is not None:
            from madira.auth import _now

            overrides["exp"] = _now() + exp_delta
        token = _id_token(token_nonce, **overrides)
        monkeypatch.setattr(
            "madira.auth.post_form",
            lambda url, data: {"id_token": token},
        )
        monkeypatch.setattr("madira.auth.get_json", lambda url: {"keys": [PUBLIC]})
        return client.get(
            "/auth/callback",
            params={"code": "auth-code", "state": query["state"][0]},
            cookies={"madira_oidc": oidc},
            follow_redirects=False,
        )

    for overrides in cases:
        response = run(**dict(overrides))
        assert response.headers["location"] == "/login?error=id_token", overrides
        assert _count() == 0

    for picture in dropped_pictures:
        response = run(picture=picture)
        assert response.headers["location"] == "/", picture
        row = _load()
        assert row is not None
        assert row["picture"] == ""
        _wipe()


def test_bad_signature_and_unknown_kid_refresh(client: TestClient, configured, monkeypatch):
    other = RSAKey.generate_key(2048)
    foreign = other.as_dict(private=True)
    foreign["kid"] = "madira-test"
    forged = jwt.encode(
        {"alg": "RS256", "kid": "madira-test"},
        _id_token_claims("nonce-placeholder"),
        RSAKey.import_key(foreign),
    )
    _response, query, oidc = _start(client)
    monkeypatch.setattr("madira.auth.post_form", lambda url, data: {"id_token": forged})
    monkeypatch.setattr("madira.auth.get_json", lambda url: {"keys": [PUBLIC]})
    bad = client.get(
        "/auth/callback",
        params={"code": "auth-code", "state": query["state"][0]},
        cookies={"madira_oidc": oidc},
        follow_redirects=False,
    )
    assert bad.headers["location"] == "/login?error=id_token"
    assert _count() == 0

    calls = {"n": 0}

    def jwks(url):
        calls["n"] += 1
        assert url == GOOGLE_JWKS
        if calls["n"] == 1:
            return {"keys": []}
        return {"keys": [PUBLIC]}

    _response, query, oidc = _start(client)
    token = _id_token(query["nonce"][0])
    monkeypatch.setattr("madira.auth.post_form", lambda url, data: {"id_token": token})
    monkeypatch.setattr("madira.auth.get_json", jwks)
    clear_jwks_cache()
    ok = client.get(
        "/auth/callback",
        params={"code": "auth-code", "state": query["state"][0]},
        cookies={"madira_oidc": oidc},
        follow_redirects=False,
    )
    assert ok.headers["location"] == "/"
    assert calls["n"] == 2
    assert _count() == 1


def _id_token_claims(nonce: str) -> dict:
    from madira.auth import _now

    now = _now()
    return {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-sub-1",
        "email": "ada@example.com",
        "email_verified": True,
        "nonce": nonce,
        "iat": now,
        "exp": now + 300,
    }


def test_session_expiry_tamper_and_logout(client: TestClient, configured, monkeypatch):
    clock = {"t": 1_800_000_000}
    monkeypatch.setattr("madira.auth._now", lambda: clock["t"])
    _response, query, oidc = _start(client)
    token = _id_token(query["nonce"][0])
    monkeypatch.setattr("madira.auth.post_form", lambda url, data: {"id_token": token})
    monkeypatch.setattr("madira.auth.get_json", lambda url: {"keys": [PUBLIC]})
    created = client.get(
        "/auth/callback",
        params={"code": "auth-code", "state": query["state"][0]},
        cookies={"madira_oidc": oidc},
        follow_redirects=False,
    )
    session_value, _flags = _cookie(created, "madira_session")
    client.cookies.clear()
    assert client.get("/auth/me", cookies={"madira_session": session_value}).json()["user"]["email"] == "ada@example.com"

    flipped = session_value[:-1] + ("A" if session_value[-1] != "A" else "B")
    client.cookies.clear()
    assert client.get("/auth/me", cookies={"madira_session": flipped}).json() == {"user": None}

    monkeypatch.setenv("MADIRA_AUTH_SECRET", "a-different-auth-secret")
    client.cookies.clear()
    assert client.get("/auth/me", cookies={"madira_session": session_value}).json() == {"user": None}
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)

    clock["t"] += 14 * 24 * 60 * 60 + 5
    client.cookies.clear()
    assert client.get("/auth/me", cookies={"madira_session": session_value}).json() == {"user": None}

    clock["t"] = 1_800_000_000
    client.cookies.clear()
    logout = client.post("/auth/logout", cookies={"madira_session": session_value})
    assert logout.status_code == 200
    cleared, flags = _cookie(logout, "madira_session")
    assert cleared == '""'
    assert "max-age=0" in flags
    assert "httponly" in flags
    client.cookies.clear()
    assert client.get("/auth/me").json() == {"user": None}


def test_expired_oidc_ticket_and_cancelled_google(client: TestClient, configured, monkeypatch):
    clock = {"t": 1_900_000_000}
    monkeypatch.setattr("madira.auth._now", lambda: clock["t"])
    _response, query, oidc = _start(client)
    clock["t"] += 601
    stale = client.get(
        "/auth/callback",
        params={"code": "auth-code", "state": query["state"][0]},
        cookies={"madira_oidc": oidc},
        follow_redirects=False,
    )
    assert stale.headers["location"] == "/login?error=state"
    assert _count() == 0

    denied = client.get("/auth/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert denied.headers["location"] == "/login?error=denied"
    echoed = client.get("/auth/callback", params={"error": "server_error<script>"}, follow_redirects=False)
    assert echoed.headers["location"] == "/login?error=token"
    assert "<script>" not in echoed.headers["location"]


def test_plain_issuer_and_audience_list(client: TestClient, configured, monkeypatch):
    _response, query, oidc = _start(client)
    token = _id_token(query["nonce"][0], iss="accounts.google.com", aud=[CLIENT_ID, "another"])
    monkeypatch.setattr("madira.auth.post_form", lambda url, data: {"id_token": token})
    monkeypatch.setattr("madira.auth.get_json", lambda url: {"keys": [PUBLIC]})
    response = client.get(
        "/auth/callback",
        params={"code": "auth-code", "state": query["state"][0]},
        cookies={"madira_oidc": oidc},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/"
    assert _load()["email"] == "ada@example.com"
