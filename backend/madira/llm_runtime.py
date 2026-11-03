"""Which model the sommelier uses right now.

Precedence, unless `MADIRA_DEMO_MODE=true` (that always forces demo):

1. A key saved in Settings.
2. The provider key in the environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
   `GOOGLE_API_KEY`, or `MADIRA_API_KEY`).
3. Demo mode.

`MADIRA_DEMO_MODE=false` keeps the previous behavior: stay live even when no
key is present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

PROVIDER_DEFAULTS = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "google_genai": "gemini-3.5-flash",
}
ALLOWED_PROVIDERS = frozenset(PROVIDER_DEFAULTS)


def canonical_provider(name: str) -> str:
    normalized = (name or "").strip().lower()
    if normalized in {"google", "gemini", "google_genai"}:
        return "google_genai"
    return normalized


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def env_provider() -> str:
    return canonical_provider(_env("MADIRA_LLM_PROVIDER") or "openai")


def env_model() -> str:
    return _env("MADIRA_LLM_MODEL") or PROVIDER_DEFAULTS["openai"]


def env_api_key(provider: str) -> str:
    generic = _env("MADIRA_API_KEY")
    if provider in {"openai", "azure"}:
        return _env("OPENAI_API_KEY") or generic
    if provider == "anthropic":
        return _env("ANTHROPIC_API_KEY") or generic
    if provider == "google_genai":
        return _env("GOOGLE_API_KEY") or generic
    return generic or _env("OPENAI_API_KEY") or _env("ANTHROPIC_API_KEY") or _env("GOOGLE_API_KEY")


@dataclass
class StoredCredential:
    provider: str
    model: str
    ciphertext: str
    key_last4: str


@dataclass
class LlmRuntime:
    demo_mode: bool
    provider: str
    model: str
    api_key: str
    source: str
    stored: bool
    configured: bool
    key_hint: str | None
    saved_provider: str | None
    saved_model: str | None
    warning: str = ""


def _open_session(session):
    if session is not None:
        return session, False
    from madira.db import SessionLocal

    return SessionLocal(), True


def read_stored(session=None) -> StoredCredential | None:
    from madira.models import LlmCredential

    sess, own = _open_session(session)
    try:
        row = sess.get(LlmCredential, 1)
        if row is None:
            return None
        return StoredCredential(
            provider=row.provider,
            model=row.model or "",
            ciphertext=row.ciphertext,
            key_last4=row.key_last4 or "",
        )
    except SQLAlchemyError:
        sess.rollback()
        return None
    finally:
        if own:
            sess.close()


def _upsert(provider: str, model: str, ciphertext: str, key_last4: str) -> None:
    from madira.db import SessionLocal
    from madira.models import LlmCredential

    session = SessionLocal()
    try:
        row = session.get(LlmCredential, 1)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if row is None:
            session.add(
                LlmCredential(
                    id=1,
                    provider=provider,
                    model=model,
                    ciphertext=ciphertext,
                    key_last4=key_last4,
                    updated_at=now,
                )
            )
        else:
            row.provider = provider
            row.model = model
            row.ciphertext = ciphertext
            row.key_last4 = key_last4
            row.updated_at = now
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def save_credential(provider: str, model: str, api_key: str) -> LlmRuntime:
    from madira.crypto import encrypt_secret

    canonical = canonical_provider(provider)
    if canonical not in ALLOWED_PROVIDERS:
        raise ValueError("Provider must be OpenAI, Anthropic, or Google.")
    key = api_key.strip()
    if not key:
        raise ValueError("API key is required.")
    chosen = model.strip() or PROVIDER_DEFAULTS[canonical]
    _upsert(canonical, chosen, encrypt_secret(key), key[-4:])
    return resolve_runtime()


def restore_stored(previous: StoredCredential | None) -> None:
    if previous is None:
        delete_credential()
        return
    _upsert(previous.provider, previous.model, previous.ciphertext, previous.key_last4)


def delete_credential() -> LlmRuntime:
    from madira.db import SessionLocal
    from madira.models import LlmCredential

    session = SessionLocal()
    try:
        row = session.get(LlmCredential, 1)
        if row is not None:
            session.delete(row)
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return resolve_runtime()


def _runtime(provider: str, model: str, source: str, *, demo_mode: bool, api_key: str, stored: StoredCredential | None, configured: bool, saved_provider: str | None, saved_model: str | None, warning: str) -> LlmRuntime:
    return LlmRuntime(
        demo_mode=demo_mode,
        provider=provider,
        model=model,
        api_key=api_key,
        source=source,
        stored=stored is not None,
        configured=configured,
        key_hint=stored.key_last4 if configured and stored is not None else None,
        saved_provider=saved_provider,
        saved_model=saved_model,
        warning=warning,
    )


def resolve_runtime(session=None) -> LlmRuntime:
    flag = _env("MADIRA_DEMO_MODE").lower()
    forced_demo = flag in {"1", "true", "yes", "on"}
    forced_live = flag in {"0", "false", "no", "off"}
    provider = env_provider()
    model = env_model()
    warning = ""
    stored = read_stored(session)
    saved_key = ""
    if stored is not None:
        try:
            from madira.crypto import decrypt_secret

            saved_key = decrypt_secret(stored.ciphertext)
        except RuntimeError as exc:
            warning = str(exc)
            saved_key = ""

    configured = stored is not None and bool(saved_key) and not warning
    saved_provider = canonical_provider(stored.provider) if configured and stored is not None else None
    saved_model = None
    if configured and stored is not None and saved_provider is not None:
        saved_model = stored.model.strip() or PROVIDER_DEFAULTS.get(saved_provider, model)

    if forced_demo:
        return _runtime(
            saved_provider or provider,
            saved_model or model,
            "forced-demo",
            demo_mode=True,
            api_key="",
            stored=stored,
            configured=configured,
            saved_provider=saved_provider,
            saved_model=saved_model,
            warning=warning,
        )

    if configured and saved_provider is not None and saved_model is not None:
        return _runtime(
            saved_provider,
            saved_model,
            "settings",
            demo_mode=False,
            api_key=saved_key,
            stored=stored,
            configured=True,
            saved_provider=saved_provider,
            saved_model=saved_model,
            warning=warning,
        )

    key = env_api_key(provider)
    if key or forced_live:
        return _runtime(
            provider,
            model,
            "env",
            demo_mode=False,
            api_key=key,
            stored=stored,
            configured=False,
            saved_provider=None,
            saved_model=None,
            warning=warning,
        )

    return _runtime(
        provider,
        model,
        "demo",
        demo_mode=True,
        api_key="",
        stored=stored,
        configured=False,
        saved_provider=None,
        saved_model=None,
        warning=warning,
    )


def describe_runtime(runtime: LlmRuntime) -> dict:
    if runtime.demo_mode and runtime.source == "forced-demo":
        label = "DEMO MODE — forced by MADIRA_DEMO_MODE"
        shown_model = "madira-demo-fixtures"
    elif runtime.demo_mode:
        label = "DEMO MODE — deterministic fixtures, no API key"
        shown_model = "madira-demo-fixtures"
    else:
        label = f"LIVE — {runtime.provider}:{runtime.model}"
        shown_model = runtime.model
    return {
        "demo_mode": runtime.demo_mode,
        "llm_provider": runtime.provider,
        "llm_model": shown_model,
        "llm_source": runtime.source,
        "label": label,
    }


def settings_payload(runtime: LlmRuntime) -> dict:
    info = describe_runtime(runtime)
    return {
        "configured": runtime.configured,
        "stored": runtime.stored,
        "provider": runtime.saved_provider,
        "model": runtime.saved_model,
        "key_hint": runtime.key_hint if runtime.configured else None,
        "demo_mode": info["demo_mode"],
        "demo_forced": runtime.source == "forced-demo",
        "source": info["llm_source"],
        "label": info["label"],
        "warning": runtime.warning,
        "default_models": dict(PROVIDER_DEFAULTS),
    }
