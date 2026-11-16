from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from madira.agents.orchestrator import SPECIALIST_NAMES, inspect_subagents
from madira.config import status_payload

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
    from madira.tenancy import demo_posture

    if demo_posture():
        from madira.agents.demo.fixtures import SAMPLE_MENU_TEXT

        payload["sample_menu"] = SAMPLE_MENU_TEXT
    try:
        payload["wiring"] = inspect_subagents()
    except Exception as exc:
        payload["wiring_error"] = str(exc)
    return payload


@fixtures_router.get("/fixtures/sample-menu")
def sample_menu() -> dict[str, str]:
    from madira.domain.errors import require_demo

    require_demo("The sample menu")
    from madira.agents.demo.fixtures import SAMPLE_MENU_TEXT

    return {"text": SAMPLE_MENU_TEXT}
