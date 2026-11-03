"""Confirm a provider key with one cheap list-models call.

Tests inject a validator with `set_key_validator`. `MADIRA_LLM_VALIDATOR=accept`
skips the network call and is for local tests only — never set it in production.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import httpx

Validator = Callable[[str, str, str], None]
_override: Validator | None = None

_TIMEOUT = 20.0


def set_key_validator(fn: Validator | None) -> None:
    global _override
    _override = fn


def validate_provider_key(provider: str, api_key: str, model: str = "") -> None:
    if _override is not None:
        _override(provider, api_key, model)
        return
    if os.environ.get("MADIRA_LLM_VALIDATOR", "").strip().lower() == "accept":
        return
    validate_provider_key_live(provider, api_key, model)


def validate_provider_key_live(provider: str, api_key: str, model: str = "") -> None:
    """Hit the provider's model list. `model` is unused; the call only checks the key."""
    del model
    try:
        if provider == "openai":
            response = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=_TIMEOUT,
            )
            label = "OpenAI"
        elif provider == "anthropic":
            response = httpx.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=_TIMEOUT,
            )
            label = "Anthropic"
        elif provider == "google_genai":
            response = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
                timeout=_TIMEOUT,
            )
            label = "Google"
        else:
            raise ValueError("Provider must be OpenAI, Anthropic, or Google.")
    except httpx.HTTPError as exc:
        raise ValueError(
            f"Could not reach the provider to verify the API key ({exc.__class__.__name__})."
        ) from exc
    if response.status_code >= 400:
        detail = _safe_body(response.text, api_key)
        message = f"{label} rejected the API key ({response.status_code})."
        if detail:
            message = f"{message} {detail}"
        raise ValueError(message)


def _safe_body(text: str, api_key: str) -> str:
    cleaned = text.replace(api_key, "") if api_key else text
    return " ".join(cleaned.split())[:180]
