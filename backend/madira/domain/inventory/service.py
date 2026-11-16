"""On-hand stock, par, and low-stock alerts. Quantities are computed here."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.errors import NotFound
from madira.domain.session import session_scope
from madira.models import InventoryItem


def rows(session: Session, venue_id: uuid.UUID) -> list[dict]:
    items = session.scalars(
        select(InventoryItem).where(InventoryItem.venue_id == venue_id).order_by(InventoryItem.sku)
    ).all()
    out = []
    for item in items:
        supplier = item.supplier.name if item.supplier else ""
        low = item.on_hand < item.par
        out.append(
            {
                "id": item.id,
                "sku": item.sku,
                "name": item.name,
                "category": item.category,
                "supplier": supplier,
                "supplier_id": item.supplier_id,
                "on_hand": item.on_hand,
                "par": item.par,
                "unit_cost": item.unit_cost,
                "currency": item.currency,
                "depletion_30d": item.depletion_30d,
                "unit": item.unit,
                "low": low,
                "reorder_qty": max(item.par - item.on_hand, 0),
            }
        )
    return out


def snapshot(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        items = rows(session, venue_id)
    alerts = [
        {
            "sku": item["sku"],
            "name": item["name"],
            "on_hand": item["on_hand"],
            "par": item["par"],
            "message": f"{item['name']} is at {item['on_hand']} {item['unit']} (par {item['par']})",
        }
        for item in items
        if item["low"]
    ]
    return {"items": items, "alerts": alerts}


def set_on_hand(venue_id: uuid.UUID, sku: str, on_hand: int) -> None:
    with session_scope() as session:
        item = session.scalar(
            select(InventoryItem).where(
                InventoryItem.venue_id == venue_id,
                InventoryItem.sku == sku.strip().upper(),
            )
        )
        if item is None:
            raise NotFound(f"unknown sku {sku}")
        item.on_hand = int(on_hand)
        session.commit()
