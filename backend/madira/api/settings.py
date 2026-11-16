from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from madira.api.agent import refresh_sommelier_agent
from madira.rbac import Capability, require

router = APIRouter()


class SettingsSaveBody(BaseModel):
    provider: str
    model: str = ""
    api_key: str = ""


def _public_error(message: str, secret: str) -> str:
    if secret:
        message = message.replace(secret, "")
    return " ".join(message.split()) or "The API key was rejected."


@router.get("/settings/llm", dependencies=[require(Capability.SETTINGS)])
def settings_get() -> dict[str, Any]:
    from madira.llm_runtime import resolve_runtime, settings_payload

    return settings_payload(resolve_runtime())


@router.post("/settings/llm", dependencies=[require(Capability.SETTINGS)])
def settings_save(body: SettingsSaveBody) -> dict[str, Any]:
    from madira.llm_runtime import (
        ALLOWED_PROVIDERS,
        canonical_provider,
        read_stored,
        restore_stored,
        save_credential,
        settings_payload,
    )
    from madira.llm_validate import validate_provider_key

    provider = canonical_provider(body.provider)
    api_key = body.api_key.strip()
    model = body.model.strip()
    if provider not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail="Provider must be OpenAI, Anthropic, or Google.")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required.")
    if len(model) > 120:
        raise HTTPException(status_code=400, detail="Model id is too long.")
    try:
        validate_provider_key(provider, api_key, model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_public_error(str(exc), api_key)) from exc
    previous = read_stored()
    try:
        runtime = save_credential(provider, model, api_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=_public_error(str(exc), api_key)) from exc
    try:
        refresh_sommelier_agent()
    except Exception as exc:
        restore_stored(previous)
        try:
            refresh_sommelier_agent()
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=_public_error(f"Could not switch the sommelier to this provider: {exc}", api_key),
        ) from exc
    return settings_payload(runtime)


@router.delete("/settings/llm", dependencies=[require(Capability.SETTINGS)])
def settings_delete() -> dict[str, Any]:
    from madira.llm_runtime import delete_credential, settings_payload

    runtime = delete_credential()
    try:
        refresh_sommelier_agent()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"The key was removed, but the sommelier could not be rebuilt: {exc}") from exc
    return settings_payload(runtime)
