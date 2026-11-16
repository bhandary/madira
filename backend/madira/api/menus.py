from __future__ import annotations

import io
import json
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import select

from madira.agents.tools import parse_menu, recommend_pairings
from madira.db import SessionLocal
from madira.fixtures_data import SAMPLE_MENU_TEXT
from madira.models import Menu
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id, scoped_get

router = APIRouter()


def _extract_upload_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return SAMPLE_MENU_TEXT + "\n\n[image upload in demo mode — using Maison Madira fixture]"
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return SAMPLE_MENU_TEXT


@router.post("/menus/upload", dependencies=[require(Capability.EDIT)])
async def upload_menu(
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
    source_name: str = Form(default="upload"),
) -> dict[str, Any]:
    raw = text
    if file is not None:
        data = await file.read()
        extracted = _extract_upload_text(file.filename or "", data)
        raw = (raw + "\n" + extracted).strip() if raw else extracted
        source_name = file.filename or source_name
    if not raw.strip():
        raw = SAMPLE_MENU_TEXT
    return json.loads(parse_menu(raw, source_name=source_name))


@router.post("/menus/parse", dependencies=[require(Capability.EDIT)])
def parse_menu_route(body: dict[str, Any]) -> dict[str, Any]:
    return json.loads(parse_menu(body.get("text") or SAMPLE_MENU_TEXT, source_name=body.get("source_name") or "pasted"))


@router.get("/menus", dependencies=[require(Capability.FLOOR)])
def list_menus() -> dict[str, Any]:
    session = SessionLocal()
    try:
        menus = session.scalars(
            select(Menu).where(Menu.venue_id == active_venue_id()).order_by(Menu.created_at.desc(), Menu.id.desc())
        ).all()
        return {
            "menus": [
                {
                    "id": m.id,
                    "name": m.name,
                    "cuisine": m.cuisine,
                    "price_tier": m.price_tier,
                    "dish_count": len(m.dishes),
                }
                for m in menus
            ]
        }
    finally:
        session.close()


@router.get("/menus/{menu_id}", dependencies=[require(Capability.FLOOR)])
def get_menu(menu_id: uuid.UUID) -> dict[str, Any]:
    session = SessionLocal()
    try:
        menu = scoped_get(session, Menu, menu_id)
        if not menu:
            raise HTTPException(404, "menu not found")
        dishes = []
        for dish in menu.dishes:
            dishes.append(
                {
                    "id": dish.id,
                    "name": dish.name,
                    "course": dish.course,
                    "flavor_profile": dish.flavor_profile,
                    "price": dish.price,
                    "currency": dish.currency,
                    "pairings": [
                        {
                            "category": p.category,
                            "name": p.name,
                            "producer": p.producer,
                            "region": p.region,
                            "style": p.style,
                            "rationale": p.rationale,
                            "price_tier": p.price_tier,
                            "glass_price": p.glass_price,
                            "bottle_price": p.bottle_price,
                            "currency": p.currency,
                        }
                        for p in dish.pairings
                    ],
                }
            )
        return {
            "id": menu.id,
            "name": menu.name,
            "cuisine": menu.cuisine,
            "price_tier": menu.price_tier,
            "raw_text": menu.raw_text,
            "dishes": dishes,
        }
    finally:
        session.close()


@router.post("/menus/{menu_id}/pair", dependencies=[require(Capability.EDIT)])
def pair_menu(menu_id: uuid.UUID) -> dict[str, Any]:
    session = SessionLocal()
    try:
        if scoped_get(session, Menu, menu_id) is None:
            raise HTTPException(404, "menu not found")
    finally:
        session.close()
    return json.loads(recommend_pairings(str(menu_id)))
