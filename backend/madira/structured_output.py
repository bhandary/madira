"""Validate one structured completion and retry with the validation error.

This is the retry already used by menu, note, lesson, and pairing drafts.
`MADIRA_STRUCTURED_ATTEMPTS` is the number of tries, including the first.
The default is 2. A bad value falls back to 2. The cap is 5.

The log line names the draft and the field error. It does not include the
prompt, the completion, or any API key.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import TypeVar

from pydantic import ValidationError

from madira.domain.errors import DraftFailed

logger = logging.getLogger("madira.structured")

T = TypeVar("T")
_DEFAULT_ATTEMPTS = 2
_MAX_ATTEMPTS = 5

Parse = Callable[[str], T]
Call = Callable[[str], str]
GiveUp = Callable[[Exception, str, int], DraftFailed]


def attempt_limit() -> int:
    raw = os.environ.get("MADIRA_STRUCTURED_ATTEMPTS", "").strip()
    if not raw:
        return _DEFAULT_ATTEMPTS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_ATTEMPTS
    if value < 1:
        return 1
    if value > _MAX_ATTEMPTS:
        return _MAX_ATTEMPTS
    return value


def field_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"]) or "draft"
            parts.append(f"{loc}: {err['msg']}")
        return "; ".join(parts)[:300]
    text = str(exc).strip() or "The response was not JSON."
    return text[:300]


def feedback_prompt(prompt: str, error: str) -> str:
    return (
        prompt
        + "\nThe previous JSON did not match the schema. "
        + "Fix these fields and return one JSON object:\n"
        + error
        + "\n"
    )


def log_rejection(label: str, attempts: int, reason: str) -> None:
    logger.warning(
        "structured output rejected label=%s attempts=%s reason=%s",
        label,
        attempts,
        reason,
    )


def run_structured(
    prompt: str,
    call: Call,
    parse: Parse[T],
    *,
    label: str,
    failure: str | None = None,
    give_up: GiveUp | None = None,
) -> T:
    """Call `call`, validate with `parse`, and retry a validation error up to N.

    A `DraftFailed` from `call` is the model's transport error and is not
    retried. Validation errors are `ValidationError`, `JSONDecodeError`, and
    `ValueError`.
    """

    n = attempt_limit()
    error = ""
    last: Exception | None = None
    for attempt in range(1, n + 1):
        text = prompt if attempt == 1 else feedback_prompt(prompt, error)
        try:
            raw = call(text)
        except DraftFailed:
            raise
        except Exception as exc:
            raise DraftFailed(f"{label} failed ({type(exc).__name__}).", 502) from exc
        try:
            return parse(raw)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last = exc
            error = field_error(exc)
    log_rejection(label, n, error)
    if give_up is not None and last is not None:
        raise give_up(last, error, n)
    message = failure or f"{label} did not match the schema after {{n}} attempts."
    raise DraftFailed(message.format(n=n)) from last
