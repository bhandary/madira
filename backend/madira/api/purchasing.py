from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from madira.agents.tools import draft_purchase_orders
from madira.db import SessionLocal
from madira.models import PurchaseOrder

router = APIRouter()


@router.post("/purchase-orders/draft")
def po_draft() -> dict[str, Any]:
    return json.loads(draft_purchase_orders())


@router.get("/purchase-orders")
def po_list() -> dict[str, Any]:
    session = SessionLocal()
    try:
        rows = session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id.desc())).all()
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
