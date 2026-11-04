"""Turn a failed provider call into a short JSON-safe message. The API key is removed."""

from __future__ import annotations

import os
import re

_KEY_ENV = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "MADIRA_API_KEY",
)

_FALLBACK = {
    401: "The provider rejected the API key.",
    402: "The provider rejected the request because of billing.",
    403: "The provider refused the request.",
    429: "The provider rejected the request because of quota or rate limits.",
}


def describe_provider_failure(exc: BaseException) -> tuple[int, str]:
    status = _status_from(exc)
    detail = _scrub(_message_from(exc))
    if not detail:
        detail = _FALLBACK.get(status or 0, "The sommelier could not complete the request.")
    if status is None:
        status = 502
    elif status >= 500:
        status = 502
    return status, detail


def _chain(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _status_from(exc: BaseException) -> int | None:
    for item in _chain(exc):
        for candidate in (getattr(item, "status_code", None), getattr(getattr(item, "response", None), "status_code", None)):
            if isinstance(candidate, int) and candidate >= 400:
                return candidate
        match = re.search(r"\b(401|402|403|429)\b", str(item))
        if match:
            return int(match.group(1))
    return None


def _message_from(exc: BaseException) -> str:
    for item in _chain(exc):
        found = _find_message(getattr(item, "body", None))
        if found:
            return found
    for item in _chain(exc):
        text = str(item).strip()
        if text and text != "None":
            return text
    return ""


def _find_message(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    if isinstance(error, str) and error.strip():
        return error.strip()
    message = data.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return ""


def _secrets() -> list[str]:
    found: list[str] = []
    for name in _KEY_ENV:
        value = os.environ.get(name, "").strip()
        if value and value not in found:
            found.append(value)
    try:
        from madira.llm_runtime import resolve_runtime

        key = resolve_runtime().api_key.strip()
    except Exception:
        key = ""
    if key and key not in found:
        found.append(key)
    return found


def _scrub(text: str) -> str:
    for secret in _secrets():
        text = text.replace(secret, "")
    return " ".join(text.split())[:400]
