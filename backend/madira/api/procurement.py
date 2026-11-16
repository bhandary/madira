from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select

from madira.agents.tools import list_tastings, schedule_tasting
from madira.db import SessionLocal
from madira.models import Supplier, Tasting
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id, scoped_get

router = APIRouter()


class TastingBody(BaseModel):
    supplier_name: str = "Kermit Lynch Wine Merchant"
    title: str = "New Loire releases tasting"
    starts_at: str = ""
    ends_at: str = ""
    location: str = "Maison Madira cellar"
    notes: str = "Draft hold — export .ics, do not send invites."


@router.get("/tastings", dependencies=[require(Capability.RECORDS)])
def tastings() -> dict[str, Any]:
    return json.loads(list_tastings())


@router.post("/tastings", dependencies=[require(Capability.EDIT)])
def tastings_create(body: TastingBody) -> dict[str, Any]:
    return json.loads(
        schedule_tasting(
            supplier_name=body.supplier_name,
            title=body.title,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            location=body.location,
            notes=body.notes,
        )
    )


@router.get("/tastings/{tasting_id}/ics", dependencies=[require(Capability.RECORDS)])
def tasting_ics(tasting_id: int) -> PlainTextResponse:
    session = SessionLocal()
    try:
        tasting = scoped_get(session, Tasting, tasting_id)
        if not tasting:
            raise HTTPException(404, "tasting not found")
        return PlainTextResponse(tasting.ics, media_type="text/calendar")
    finally:
        session.close()


@router.get("/suppliers", dependencies=[require(Capability.RECORDS)])
def suppliers() -> dict[str, Any]:
    session = SessionLocal()
    try:
        rows = session.scalars(select(Supplier).where(Supplier.venue_id == active_venue_id())).all()
        return {
            "suppliers": [
                {"id": s.id, "name": s.name, "kind": s.kind, "contact_email": s.contact_email, "notes": s.notes}
                for s in rows
            ]
        }
    finally:
        session.close()
