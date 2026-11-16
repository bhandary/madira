from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from madira.agents.tools import draft_purchase_orders
from madira.db import SessionLocal
from madira.models import PurchaseOrder
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter()


@router.post("/purchase-orders/draft", dependencies=[require(Capability.APPROVE)])
def po_draft() -> dict[str, Any]:
    return json.loads(draft_purchase_orders())


@router.get("/purchase-orders", dependencies=[require(Capability.RECORDS)])
def po_list() -> dict[str, Any]:
    session = SessionLocal()
    try:
        rows = session.scalars(
            select(PurchaseOrder).where(PurchaseOrder.venue_id == active_venue_id()).order_by(PurchaseOrder.id.desc())
        ).all()
        return {
            "orders": [
                {
                    "id": po.id,
                    "status": po.status,
                    "supplier": po.supplier.name if po.supplier else "",
                    "notes": po.notes,
                    "lines": [
                        {"sku": line.sku, "name": line.name, "qty": line.qty, "unit_cost": line.unit_cost}
                        for line in po.lines
                    ],
                }
                for po in rows
            ]
        }
    finally:
        session.close()
