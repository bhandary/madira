"""Structured drafts retry with the validation error and do not log the prompt."""

from __future__ import annotations

import json
import logging

import pytest
from pydantic import BaseModel

from madira.domain.errors import DraftFailed
from madira.structured_output import attempt_limit, run_structured


class _Ok(BaseModel):
    ok: bool


def test_attempt_limit_defaults_to_two(monkeypatch):
    monkeypatch.delenv("MADIRA_STRUCTURED_ATTEMPTS", raising=False)
    assert attempt_limit() == 2
    monkeypatch.setenv("MADIRA_STRUCTURED_ATTEMPTS", "nope")
    assert attempt_limit() == 2
    monkeypatch.setenv("MADIRA_STRUCTURED_ATTEMPTS", "3")
    assert attempt_limit() == 3


def test_retry_succeeds_on_the_second_attempt(monkeypatch):
    monkeypatch.setenv("MADIRA_STRUCTURED_ATTEMPTS", "2")
    seen: list[str] = []

    def call(prompt: str) -> str:
        seen.append(prompt)
        if len(seen) == 1:
            return "not json"
        return json.dumps({"ok": True})

    result = run_structured(
        "PROMPT-SECRET",
        call,
        lambda raw: _Ok.model_validate(json.loads(raw)),
        label="Example",
    )
    assert result.ok is True
    assert len(seen) == 2
    assert "did not match the schema" in seen[1]
    assert "not json" not in seen[1]


def test_give_up_after_n_logs_no_prompt(monkeypatch, caplog):
    monkeypatch.setenv("MADIRA_STRUCTURED_ATTEMPTS", "2")
    seen: list[str] = []

    def call(prompt: str) -> str:
        seen.append(prompt)
        return "still not json"

    with caplog.at_level(logging.WARNING, logger="madira.structured"):
        with pytest.raises(DraftFailed) as caught:
            run_structured(
                "PROMPT-SECRET sk-should-not-log",
                call,
                lambda raw: _Ok.model_validate(json.loads(raw)),
                label="Example",
            )
    assert "after 2 attempts" in caught.value.message
    assert len(seen) == 2
    assert "PROMPT-SECRET" not in caplog.text
    assert "sk-should-not-log" not in caplog.text
    assert "still not json" not in caplog.text
    assert "structured output rejected" in caplog.text
    assert "label=Example" in caplog.text
    assert "attempts=2" in caplog.text


def test_transport_errors_are_not_retried(monkeypatch):
    monkeypatch.setenv("MADIRA_STRUCTURED_ATTEMPTS", "3")
    seen: list[str] = []

    def call(prompt: str) -> str:
        seen.append(prompt)
        raise RuntimeError("socket down")

    with pytest.raises(DraftFailed) as caught:
        run_structured("PROMPT-SECRET", call, lambda raw: raw, label="Example")
    assert caught.value.message == "Example failed (RuntimeError)."
    assert len(seen) == 1
