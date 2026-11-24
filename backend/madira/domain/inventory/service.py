"""On-hand stock, par, and low-stock alerts. Quantities are computed here."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from madira.domain.compliance.service import ACTION_INVENTORY, record_audit_event
from madira.domain.errors import NotFound
from madira.domain.session import session_scope
from madira.models import InventoryItem, Sku, Venue


def rows(session: Session, venue_id: uuid.UUID) -> list[dict]:
    items = session.scalars(
        select(InventoryItem)
        .join(Sku, InventoryItem.sku_id == Sku.id)
        .where(InventoryItem.venue_id == venue_id)
        .order_by(func.upper(Sku.barcode), InventoryItem.id)
    ).all()
    out = []
    for item in items:
        stock = item.sku
        product = stock.variant.product
        supplier = item.supplier.name if item.supplier else ""
        low = item.on_hand < stock.par
        out.append(
            {
                "id": item.id,
                "sku": stock.barcode,
                "name": product.name,
                "category": product.category,
                "supplier": supplier,
                "supplier_id": item.supplier_id,
                "on_hand": item.on_hand,
                "par": stock.par,
                "unit_cost": stock.cost,
                "currency": stock.currency,
                "depletion_30d": item.depletion_30d,
                "unit": item.unit,
                "low": low,
                "reorder_qty": max(stock.par - item.on_hand, 0),
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
    code = sku.strip().upper()
    with session_scope() as session:
        items = session.scalars(
            select(InventoryItem)
            .join(Sku, InventoryItem.sku_id == Sku.id)
            .where(InventoryItem.venue_id == venue_id, func.upper(Sku.barcode) == code)
        ).all()
        if not items:
            raise NotFound(f"unknown sku {sku}")
        venue = session.get(Venue, venue_id)
        if venue is None:
            raise NotFound(f"unknown sku {sku}")
        for item in items:
            previous = int(item.on_hand)
            item.on_hand = int(on_hand)
            record_audit_event(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                action=ACTION_INVENTORY,
                entity_type="inventory_item",
                entity_id=item.id,
                before={"sku": code, "on_hand": previous},
                after={"sku": code, "on_hand": int(on_hand)},
            )
        session.commit()
