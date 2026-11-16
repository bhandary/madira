from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from madira.agents.tools import get_inventory, update_stock
from madira.rbac import Capability, require

router = APIRouter()


class StockBody(BaseModel):
    on_hand: int = Field(ge=0)


@router.get("/inventory", dependencies=[require(Capability.COUNT)])
def inventory() -> dict[str, Any]:
    return json.loads(get_inventory())


@router.patch("/inventory/{sku}", dependencies=[require(Capability.COUNT)])
def inventory_patch(sku: str, body: StockBody) -> dict[str, Any]:
    payload = json.loads(update_stock(sku, body.on_hand))
    if payload.get("error"):
        raise HTTPException(404, payload["error"])
    return payload
