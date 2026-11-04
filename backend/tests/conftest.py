"""Keep the suite in demo mode no matter which keys the shell exported."""

from __future__ import annotations

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
    monkeypatch.delenv("MADIRA_DEMO_MODE", raising=False)
    monkeypatch.delenv("MADIRA_LLM_VALIDATOR", raising=False)
    _clear_saved_key()


def _clear_saved_key() -> None:
    from madira.db import SessionLocal, init_db
    from madira.models import LlmCredential

    init_db()
    session = SessionLocal()
    try:
        row = session.get(LlmCredential, 1)
        if row is not None:
            session.delete(row)
            session.commit()
    finally:
        session.close()
