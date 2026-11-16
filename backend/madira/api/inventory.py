from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from madira.agents.presenters.inventory import with_inventory
from madira.domain.errors import NotFound
from madira.domain.inventory.service import set_on_hand, snapshot
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter()


class StockBody(BaseModel):
    on_hand: int = Field(ge=0)


@router.get("/inventory", dependencies=[require(Capability.COUNT)])
def inventory() -> dict[str, Any]:
    return with_inventory(snapshot(active_venue_id()))


@router.patch("/inventory/{sku}", dependencies=[require(Capability.COUNT)])
def inventory_patch(sku: str, body: StockBody) -> dict[str, Any]:
    try:
        set_on_hand(active_venue_id(), sku, body.on_hand)
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc
    return with_inventory(snapshot(active_venue_id()))
