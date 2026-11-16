from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from madira.agents.orchestrator import SPECIALIST_NAMES, inspect_subagents
from madira.config import status_payload
from madira.fixtures_data import SAMPLE_MENU_TEXT

router = APIRouter()
status_router = APIRouter()
fixtures_router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", **status_payload()}


@status_router.get("/status")
def status() -> dict[str, Any]:
    payload = status_payload()
    payload["specialists"] = list(SPECIALIST_NAMES)
    payload["sample_menu"] = SAMPLE_MENU_TEXT
    try:
        payload["wiring"] = inspect_subagents()
    except Exception as exc:
        payload["wiring_error"] = str(exc)
    return payload


@fixtures_router.get("/fixtures/sample-menu")
def sample_menu() -> dict[str, str]:
    return {"text": SAMPLE_MENU_TEXT}
