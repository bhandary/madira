"""Cookie-authenticated writes require a signed CSRF token and a known origin."""

from __future__ import annotations

import logging
import uuid

from fastapi.testclient import TestClient

from madira.auth import SESSION_COOKIE, issue_session
from madira.csrf import BLOCKED, CSRF_COOKIE, CSRF_HEADER, EXEMPTIONS, exemption_reason, sign_csrf
from madira.db import init_db
from madira.main import app
from madira.seed import seed

AUTH_SECRET = "csrf-test-secret"


def _routes() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []

    def walk(routes, prefix: str = "") -> None:
        for route in routes:
            path = getattr(route, "path", "") or ""
            methods = getattr(route, "methods", None) or set()
            full = f"{prefix.rstrip('/')}{path}" if path else prefix
            if not full.startswith("/"):
                full = "/" + full
            for method in methods:
                if method in {"POST", "PUT", "PATCH", "DELETE"}:
                    found.append((method, full.replace("//", "/")))
            children = getattr(route, "routes", None)
            if children and path:
                mount = path if path.startswith("/") else f"/{path}"
                walk(children, prefix + mount.rstrip("/"))

    walk(app.routes)
    unique = sorted(set(found))
    assert unique, "the app registered no mutating routes"
    return unique


def _concrete(path: str) -> str:
    parts = []
    for part in path.split("/"):
        if part.startswith("{") and part.endswith("}"):
            parts.append("x")
        else:
            parts.append(part)
    return "/".join(parts) or "/"


def _session() -> str:
    return issue_session(f"csrf-{uuid.uuid4().hex}")


def _pair(session: str) -> tuple[dict[str, str], dict[str, str]]:
    token = sign_csrf(session)
    assert token
    return {SESSION_COOKIE: session, CSRF_COOKIE: token}, {CSRF_HEADER: token}


def test_exemptions_are_named():
    text = " ".join(item.reason for item in EXEMPTIONS)
    assert "liveness" in text
    assert "OAuth callback" in text
    assert "sensor secret" in text
    assert "guest list" in text
    assert exemption_reason("/sensors/webhook/probe-1")
    assert exemption_reason("/public/lists/abc")
    assert exemption_reason("/auth/logout") is None


def test_every_mutating_session_route_checks_csrf(monkeypatch, caplog):
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    monkeypatch.setenv("MADIRA_CSRF_TEST_RAW", "1")
    caplog.set_level(logging.WARNING, logger="madira.csrf")
    init_db()
    seed()
    session = _session()
    cookies, headers = _pair(session)
    bad = "not-the-session-token"
    with TestClient(app) as client:
        routes = _routes()
        assert any(path == "/ag-ui" or path.startswith("/ag-ui/") for _method, path in routes)
        for method, path in routes:
            if exemption_reason(path):
                continue
            url = _concrete(path)
            missing = client.request(method, url, cookies={SESSION_COOKIE: session})
            assert missing.status_code == 403, (method, path, missing.status_code, missing.text)
            assert missing.json()["detail"] == BLOCKED
            mismatched = client.request(
                method,
                url,
                cookies={SESSION_COOKIE: session, CSRF_COOKIE: bad},
                headers={CSRF_HEADER: bad},
            )
            assert mismatched.status_code == 403, (method, path)
            foreign = client.request(
                method,
                url,
                cookies=cookies,
                headers={**headers, "Origin": "https://evil.example"},
            )
            assert foreign.status_code == 403, (method, path)
            accepted = client.request(
                method,
                url,
                cookies=cookies,
                headers={**headers, "Origin": "http://127.0.0.1:3000"},
            )
            if accepted.status_code == 403:
                assert accepted.json().get("detail") != BLOCKED, (method, path, accepted.text)
    assert bad not in caplog.text
    assert "reason=missing_token" in caplog.text
    assert "reason=foreign_origin" in caplog.text


def test_exemptions_ignore_origin_and_token(monkeypatch, caplog):
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    monkeypatch.setenv("MADIRA_CSRF_TEST_RAW", "1")
    init_db()
    seed()
    caplog.set_level(logging.WARNING, logger="madira.csrf")
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        callback = client.get("/auth/callback", follow_redirects=False)
        assert callback.status_code != 403
        webhook = client.post(
            "/sensors/webhook/missing-probe",
            headers={"Origin": "https://evil.example"},
            content=b"{}",
        )
        assert webhook.status_code != 403 or webhook.json().get("detail") != BLOCKED
        guest = client.get("/public/lists/not-a-token")
        assert guest.status_code != 403 or guest.json().get("detail") != BLOCKED
        posted = client.post(
            "/public/lists/not-a-token",
            headers={"Origin": "https://evil.example"},
        )
        assert posted.status_code != 403 or posted.json().get("detail") != BLOCKED
    assert "/sensors/webhook/" not in caplog.text
    assert "/public/lists/" not in caplog.text


def test_referer_and_null_origin(monkeypatch):
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    monkeypatch.setenv("MADIRA_CSRF_TEST_RAW", "1")
    session = _session()
    cookies, headers = _pair(session)
    with TestClient(app) as client:
        foreign = client.post(
            "/auth/logout",
            cookies=cookies,
            headers={**headers, "Referer": "https://evil.example/steal"},
        )
        assert foreign.status_code == 403
        assert foreign.json()["detail"] == BLOCKED
        null_origin = client.post(
            "/auth/logout",
            cookies=cookies,
            headers={**headers, "Origin": "null"},
        )
        assert null_origin.status_code == 403
        allowed = client.post(
            "/auth/logout",
            cookies=cookies,
            headers={**headers, "Referer": "http://localhost:3000/settings"},
        )
        assert allowed.status_code == 200


def test_csrf_cookie_is_set_for_a_session(monkeypatch):
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    monkeypatch.setenv("MADIRA_CSRF_TEST_RAW", "1")
    session = _session()
    with TestClient(app) as client:
        missing = client.get("/auth/csrf")
        assert missing.status_code == 401
        issued = client.get("/auth/csrf", cookies={SESSION_COOKIE: session})
        assert issued.status_code == 200
        cookie = issued.cookies.get(CSRF_COOKIE)
        assert cookie == sign_csrf(session)
        issued_cookie = ""
        for header in issued.headers.get_list("set-cookie"):
            if header.startswith(f"{CSRF_COOKIE}="):
                issued_cookie = header
        assert issued_cookie
        assert "httponly" not in issued_cookie.lower()
