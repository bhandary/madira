from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from madira.agents.presenters.purchasing import with_orders
from madira.domain.purchasing.service import draft, list_orders
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter()


@router.post("/purchase-orders/draft", dependencies=[require(Capability.APPROVE)])
def po_draft() -> dict[str, Any]:
    return with_orders(draft(active_venue_id()))


@router.get("/purchase-orders", dependencies=[require(Capability.RECORDS)])
def po_list() -> dict[str, Any]:
    return list_orders(active_venue_id())
