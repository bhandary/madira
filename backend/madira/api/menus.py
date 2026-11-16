from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from madira.agents.presenters.menu import with_dishes, with_pairings
from madira.domain.errors import NotFound
from madira.domain.menu.service import (
    coerce_parse_text,
    coerce_upload_text,
    extract_upload_text,
    get_menu,
    list_menus,
    parse_menu,
    recommend_pairings,
)
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter()


@router.post("/menus/upload", dependencies=[require(Capability.EDIT)])
async def upload_menu(
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
    source_name: str = Form(default="upload"),
) -> dict[str, Any]:
    raw = text
    if file is not None:
        data = await file.read()
        extracted = extract_upload_text(file.filename or "", data)
        raw = (raw + "\n" + extracted).strip() if raw else extracted
        source_name = file.filename or source_name
    raw = coerce_upload_text(raw)
    return with_dishes(parse_menu(active_venue_id(), raw, source_name))


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


@router.post("/menus/{menu_id}/pair", dependencies=[require(Capability.EDIT)])
def pair_menu(menu_id: uuid.UUID) -> dict[str, Any]:
    payload = recommend_pairings(active_venue_id(), str(menu_id))
    if "error" in payload:
        raise HTTPException(404, "menu not found")
    return with_pairings(payload)
