"""Keep the suite in demo mode no matter which keys the shell exported."""

from __future__ import annotations

import os

import pytest

_PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "MADIRA_API_KEY",
)


@pytest.fixture(autouse=True)
def hermetic_llm_env(monkeypatch):
    for name in _PROVIDER_KEYS:
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("MADIRA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MADIRA_LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.delenv("MADIRA_LLM_MODEL_FAST", raising=False)
    monkeypatch.delenv("MADIRA_LLM_MODEL_STANDARD", raising=False)
    monkeypatch.delenv("MADIRA_STRUCTURED_ATTEMPTS", raising=False)
    monkeypatch.delenv("MADIRA_JOBS_INLINE", raising=False)
    monkeypatch.delenv("MADIRA_JOB_LEASE_SECONDS", raising=False)
    monkeypatch.delenv("MADIRA_JOB_SCHEDULE_SECONDS", raising=False)
    monkeypatch.delenv("MADIRA_STORAGE", raising=False)
    monkeypatch.delenv("MADIRA_S3_BUCKET", raising=False)
    monkeypatch.delenv("MADIRA_S3_REGION", raising=False)
    monkeypatch.delenv("MADIRA_S3_ENDPOINT", raising=False)
    monkeypatch.delenv("MADIRA_S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MADIRA_S3_SECRET_KEY", raising=False)
    monkeypatch.delenv("MADIRA_S3_URL_EXPIRES", raising=False)
    monkeypatch.delenv("MADIRA_DEMO_MODE", raising=False)
    monkeypatch.delenv("MADIRA_LLM_VALIDATOR", raising=False)
    monkeypatch.delenv("MADIRA_OWNER_EMAIL", raising=False)
    _clear_saved_key()


@pytest.fixture(autouse=True)
def attach_csrf_on_session_cookie(monkeypatch):
    """Existing clients send the session cookie. Attach the matching CSRF token.

    ``MADIRA_CSRF_TEST_RAW=1`` leaves the request untouched so the CSRF tests
    can reject a missing or bad token.
    """

    from fastapi.testclient import TestClient

    from madira.auth import SESSION_COOKIE
    from madira.csrf import CSRF_COOKIE, CSRF_HEADER, sign_csrf

    original = TestClient.send

    def wrapped(self, request, **kwargs):
        if os.environ.get("MADIRA_CSRF_TEST_RAW") != "1" and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            header_names = {key.lower() for key in request.headers.keys()}
            if CSRF_HEADER not in header_names:
                cookie_header = request.headers.get("cookie", "")
                session = _cookie_from_header(cookie_header, SESSION_COOKIE)
                token = sign_csrf(session) if session else None
                if token:
                    request.headers[CSRF_HEADER] = token
                    if _cookie_from_header(cookie_header, CSRF_COOKIE) != token:
                        extra = f"{CSRF_COOKIE}={token}"
                        request.headers["cookie"] = f"{cookie_header}; {extra}" if cookie_header else extra
        return original(self, request, **kwargs)

    monkeypatch.setattr(TestClient, "send", wrapped)


def _cookie_from_header(header: str, name: str) -> str:
    prefix = name + "="
    for part in header.split(";"):
        piece = part.strip()
        if piece.startswith(prefix):
            return piece[len(prefix):]
    return ""


def _clear_saved_key() -> None:
    from madira.db import SessionLocal, init_db
    from madira.models import LlmCredential

    from sqlalchemy import delete

    init_db()
    session = SessionLocal()
    try:
        session.execute(delete(LlmCredential))
        session.commit()
    finally:
        session.close()
