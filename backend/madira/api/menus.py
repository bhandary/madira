from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from madira.agents.presenters.menu import with_dishes, with_pairings, with_review
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.menu.service import (
    coerce_parse_text,
    confirm_version,
    edit_dish,
    get_menu,
    ingest_menu,
    list_menus,
    parse_menu,
    recommend_pairings,
)
from madira.rbac import Capability, require
from madira.storage import StorageError, upload_max_bytes
from madira.tenancy import active_venue_id

router = APIRouter()


class DishFieldEdit(BaseModel):
    field: str
    value: Any = None


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, DraftFailed):
        return HTTPException(exc.status, exc.message)
    if isinstance(exc, StorageError):
        return HTTPException(exc.status, exc.message)
    raise exc


def _menu_key(raw: str) -> uuid.UUID | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return uuid.UUID(text)
    except ValueError as exc:
        raise DraftFailed("That menu id is not valid.", 400) from exc


async def _ingest(
    file: UploadFile | None,
    text: str,
    url: str,
    menu_id: str,
) -> dict[str, Any]:
    venue_id = active_venue_id()
    body = b""
    filename = ""
    content_type = None
    if file is not None:
        body = await file.read(upload_max_bytes() + 1)
        if body:
            filename = file.filename or ""
            content_type = file.content_type
        else:
            body = b""
    try:
        payload = ingest_menu(
            venue_id,
            filename=filename,
            body=body,
            content_type=content_type,
            text="" if body else text,
            url="" if body else url,
            menu_id=_menu_key(menu_id),
        )
    except (NotFound, DraftFailed, StorageError) as exc:
        raise _fail(exc) from exc
    return with_review(payload)


@router.post("/menus/upload", dependencies=[require(Capability.EDIT)])
@router.post("/menus/ingest", dependencies=[require(Capability.EDIT)])
async def upload_menu(
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
    url: str = Form(default=""),
    menu_id: str = Form(default=""),
) -> dict[str, Any]:
    return await _ingest(file, text, url, menu_id)


@router.post("/menus/parse", dependencies=[require(Capability.EDIT)])
def parse_menu_route(body: dict[str, Any]) -> dict[str, Any]:
    text = coerce_parse_text(body.get("text"))
    source_name = body.get("source_name") or "pasted"
    return with_dishes(parse_menu(active_venue_id(), text, source_name))


@router.get("/menus", dependencies=[require(Capability.FLOOR)])
def list_menus_route() -> dict[str, Any]:
    return list_menus(active_venue_id())


@router.get("/menus/{menu_id}", dependencies=[require(Capability.FLOOR)])
def get_menu_route(menu_id: uuid.UUID) -> dict[str, Any]:
    try:
        return get_menu(active_venue_id(), menu_id)
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc


@router.patch("/menus/{menu_id}/versions/{version_id}/dishes/{dish_id}", dependencies=[require(Capability.EDIT)])
def edit_dish_route(menu_id: uuid.UUID, version_id: uuid.UUID, dish_id: uuid.UUID, body: DishFieldEdit) -> dict[str, Any]:
    try:
        payload = edit_dish(active_venue_id(), menu_id, version_id, dish_id, body.field, body.value)
    except (NotFound, DraftFailed) as exc:
        raise _fail(exc) from exc
    return with_review(payload)


@router.post("/menus/{menu_id}/versions/{version_id}/confirm", dependencies=[require(Capability.EDIT)])
def confirm_menu(menu_id: uuid.UUID, version_id: uuid.UUID) -> dict[str, Any]:
    try:
        payload = confirm_version(active_venue_id(), menu_id, version_id)
    except (NotFound, DraftFailed) as exc:
        raise _fail(exc) from exc
    return with_review(payload)


@router.post("/menus/{menu_id}/pair", dependencies=[require(Capability.EDIT)])
def pair_menu(menu_id: uuid.UUID) -> dict[str, Any]:
    payload = recommend_pairings(active_venue_id(), str(menu_id))
    if payload.get("error") == "menu not found":
        raise HTTPException(404, "menu not found")
    if payload.get("error"):
        raise HTTPException(409, payload["error"])
    return with_pairings(payload)
