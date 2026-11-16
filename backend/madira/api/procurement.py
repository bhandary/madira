from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from madira.agents.presenters.procurement import with_scheduled, with_tasting_list
from madira.domain.errors import NotFound
from madira.domain.procurement.service import ics_text, list_suppliers, list_tastings, schedule
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

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
    return with_tasting_list(list_tastings(active_venue_id()))


@router.post("/tastings", dependencies=[require(Capability.EDIT)])
def tastings_create(body: TastingBody) -> dict[str, Any]:
    payload = schedule(
        active_venue_id(),
        supplier_name=body.supplier_name,
        title=body.title,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        location=body.location,
        notes=body.notes,
    )
    if "error" in payload:
        return payload
    return with_scheduled(payload)


@router.get("/tastings/{tasting_id}/ics", dependencies=[require(Capability.RECORDS)])
def tasting_ics(tasting_id: uuid.UUID) -> PlainTextResponse:
    try:
        body = ics_text(active_venue_id(), tasting_id)
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc
    return PlainTextResponse(body, media_type="text/calendar")


@router.get("/suppliers", dependencies=[require(Capability.RECORDS)])
def suppliers() -> dict[str, Any]:
    return list_suppliers(active_venue_id())
