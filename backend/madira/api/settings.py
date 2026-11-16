from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from madira.api.agent import refresh_sommelier_agent

router = APIRouter()


class SettingsLoginBody(BaseModel):
    password: str = ""


class SettingsSaveBody(BaseModel):
    provider: str
    model: str = ""
    api_key: str = ""


def _bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return ""


def require_admin(
    x_madira_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    from madira.admin_auth import UNSET_MESSAGE, admin_configured, verify_admin_token

    if not admin_configured():
        raise HTTPException(status_code=403, detail=UNSET_MESSAGE)
    token = (x_madira_admin_token or "").strip() or _bearer(authorization)
    if not verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Admin sign-in required.")


def _public_error(message: str, secret: str) -> str:
    if secret:
        message = message.replace(secret, "")
    return " ".join(message.split()) or "The API key was rejected."


@router.post("/settings/session")
def settings_session(body: SettingsLoginBody) -> dict[str, Any]:
    from madira.admin_auth import TOKEN_TTL_SECONDS, UNSET_MESSAGE, admin_configured, check_password, issue_admin_token

    if not admin_configured():
        raise HTTPException(status_code=403, detail=UNSET_MESSAGE)
    if not check_password(body.password):
        raise HTTPException(status_code=401, detail="Incorrect admin password.")
    return {"token": issue_admin_token(), "expires_in": TOKEN_TTL_SECONDS}


@router.get("/settings/llm", dependencies=[Depends(require_admin)])
def settings_get() -> dict[str, Any]:
    from madira.llm_runtime import resolve_runtime, settings_payload

    return settings_payload(resolve_runtime())


@router.post("/settings/llm", dependencies=[Depends(require_admin)])
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


@router.delete("/settings/llm", dependencies=[Depends(require_admin)])
def settings_delete() -> dict[str, Any]:
    from madira.llm_runtime import delete_credential, settings_payload

    runtime = delete_credential()
    try:
        refresh_sommelier_agent()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"The key was removed, but the sommelier could not be rebuilt: {exc}") from exc
    return settings_payload(runtime)
