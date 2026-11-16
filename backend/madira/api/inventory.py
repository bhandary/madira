from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from madira.agents.tools import get_inventory, update_stock

router = APIRouter()


class StockBody(BaseModel):
    on_hand: int = Field(ge=0)


@router.get("/inventory")
def inventory() -> dict[str, Any]:
    return json.loads(get_inventory())


@router.patch("/inventory/{sku}")
def inventory_patch(sku: str, body: StockBody) -> dict[str, Any]:
    return json.loads(update_stock(sku, body.on_hand))
