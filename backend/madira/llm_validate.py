"""Confirm a provider key with one 1-token generation.

Listing models accepts keys that have no quota. A tiny completion against the
configured model rejects auth errors, permission errors, and empty credit.

Tests inject a validator with `set_key_validator`. `MADIRA_LLM_VALIDATOR=accept`
skips the network call and is for local tests only — never set it in production.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable

import httpx

from madira.llm_runtime import PROVIDER_DEFAULTS

Validator = Callable[[str, str, str], None]
_override: Validator | None = None

_TIMEOUT = 20.0
_LABELS = {"openai": "OpenAI", "anthropic": "Anthropic", "google_genai": "Google"}


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
    label = _LABELS.get(provider)
    if label is None:
        raise ValueError("Provider must be OpenAI, Anthropic, or Google.")
    chosen = (model or "").strip() or PROVIDER_DEFAULTS[provider]
    try:
        response = _probe(provider, api_key, chosen)
    except httpx.HTTPError as exc:
        raise ValueError(f"Could not reach {label} to verify the API key ({exc.__class__.__name__}).") from exc
    if response.status_code >= 400:
        detail = _error_detail(response.text, api_key)
        message = f"{label} rejected the API key ({response.status_code})."
        if detail:
            message = f"{message} {detail}"
        raise ValueError(message)


def _probe(provider: str, api_key: str, model: str) -> httpx.Response:
    if provider == "openai":
        return httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_completion_tokens": 1,
            },
            timeout=_TIMEOUT,
        )
    if provider == "anthropic":
        return httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=_TIMEOUT,
        )
    model_id = model.removeprefix("models/")
    return httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent",
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": "hi"}]}],
            "generationConfig": {"maxOutputTokens": 1},
        },
        timeout=_TIMEOUT,
    )


def _error_detail(text: str, api_key: str) -> str:
    message = ""
    try:
        message = _find_message(json.loads(text))
    except json.JSONDecodeError:
        message = ""
    return _safe_body(message or text, api_key)


def _find_message(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        nested = error.get("message")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    if isinstance(error, str) and error.strip():
        return error.strip()
    message = data.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return ""


def _safe_body(text: str, api_key: str) -> str:
    cleaned = text.replace(api_key, "") if api_key else text
    return " ".join(cleaned.split())[:300]
