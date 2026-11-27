"""Shared-tablet routes. Cookies carry the device and the acting person.

The PIN and the cookie values are not logged. CSRF still covers these writes
when a sign-in session cookie is present.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from madira.auth import SESSION_TTL, cookie_secure
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.tablet import (
    ACTOR_COOKIE,
    TABLET_COOKIE,
    TabletResult,
    clear_pin,
    disable_tablet,
    enable_tablet,
    idle_seconds,
    lock_tablet,
    set_pin,
    tablet_state,
    touch_tablet,
    unlock_tablet,
)

router = APIRouter()


class PinBody(BaseModel):
    pin: str


class UnlockBody(BaseModel):
    user_id: uuid.UUID
    pin: str


def _raise(exc: Exception) -> None:
    if isinstance(exc, NotFound):
        raise HTTPException(404, exc.message) from exc
    if isinstance(exc, DraftFailed):
        raise HTTPException(exc.status, exc.message) from exc
    raise exc


def _set(response: JSONResponse, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def _clear(response: JSONResponse, name: str) -> None:
    response.delete_cookie(name, path="/", secure=cookie_secure(), httponly=True, samesite="lax")


def _json(result: TabletResult) -> JSONResponse:
    response = JSONResponse(result.body)
    response.headers["Cache-Control"] = "no-store"
    if result.clear_tablet:
        _clear(response, TABLET_COOKIE)
    if result.clear_actor:
        _clear(response, ACTOR_COOKIE)
    if result.tablet_token:
        _set(response, TABLET_COOKIE, result.tablet_token, SESSION_TTL)
    if result.actor_token:
        _set(response, ACTOR_COOKIE, result.actor_token, idle_seconds())
    return response


@router.get("/tablet")
def get_tablet(request: Request) -> dict:
    try:
        return tablet_state(request)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/me/pin")
def me_pin(body: PinBody) -> dict:
    try:
        return set_pin(body.pin)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.delete("/team/members/{user_id}/pin")
def member_pin_clear(user_id: uuid.UUID) -> dict:
    try:
        return clear_pin(user_id)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/tablet/enable")
def tablet_enable() -> JSONResponse:
    try:
        return _json(enable_tablet())
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/tablet/disable")
def tablet_disable(body: PinBody, request: Request) -> JSONResponse:
    try:
        return _json(disable_tablet(request, body.pin))
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/tablet/unlock")
def tablet_unlock(body: UnlockBody, request: Request) -> JSONResponse:
    try:
        return _json(unlock_tablet(request, body.user_id, body.pin))
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/tablet/lock")
def tablet_lock(request: Request) -> JSONResponse:
    try:
        return _json(lock_tablet(request))
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/tablet/touch")
def tablet_touch(request: Request) -> JSONResponse:
    try:
        return _json(touch_tablet(request))
    except (NotFound, DraftFailed) as exc:
        _raise(exc)
