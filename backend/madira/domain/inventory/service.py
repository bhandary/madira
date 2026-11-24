"""On-hand stock, par, and low-stock alerts.

Quantities shown here come from the cached movement sum. Thirty-day depletion
and the per-location breakdown are computed from the ledger on read.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import (
    as_qty,
    balances_by_sku,
    depletion_by_sku,
    list_locations,
    public_qty,
    reorder_bottles,
    valuation_cents,
)
from madira.domain.inventory.ledger import apply_count
from madira.domain.session import session_scope
from madira.models import InventoryItem, Location, Sku


def rows(session: Session, venue_id: uuid.UUID) -> list[dict]:
    items = session.scalars(
        select(InventoryItem)
        .join(Sku, InventoryItem.sku_id == Sku.id)
        .where(InventoryItem.venue_id == venue_id)
        .order_by(func.upper(Sku.barcode), InventoryItem.id)
    ).all()
    places = session.scalars(select(Location).where(Location.venue_id == venue_id).order_by(Location.name)).all()
    balances = balances_by_sku(session, venue_id)
    depletion = depletion_by_sku(session, venue_id)
    out = []
    for item in items:
        stock = item.sku
        product = stock.variant.product
        supplier = item.supplier.name if item.supplier else ""
        qty = as_qty(item.on_hand)
        shown = public_qty(qty)
        cost = int(stock.cost or 0)
        by_location = balances.get(item.sku_id, {})
        locations = []
        for place in places:
            amount = by_location.get(place.id, Decimal("0"))
            locations.append(
                {
                    "location_id": str(place.id),
                    "location_name": place.name,
                    "quantity": public_qty(amount),
                    "valuation_cents": valuation_cents(amount, cost),
                }
            )
        low = qty < Decimal(int(stock.par or 0))
        out.append(
            {
                "id": item.id,
                "sku": stock.barcode,
                "name": product.name,
                "category": product.category,
                "supplier": supplier,
                "supplier_id": item.supplier_id,
                "on_hand": shown,
                "par": stock.par,
                "unit_cost": cost,
                "unit_cost_cents": cost,
                "currency": stock.currency,
                "depletion_30d": public_qty(depletion.get(item.sku_id, Decimal("0"))),
                "unit": item.unit,
                "low": low,
                "reorder_qty": reorder_bottles(qty, int(stock.par or 0)),
                "valuation_cents": valuation_cents(qty, cost),
                "locations": locations,
            }
        )
    return out


def snapshot(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        items = rows(session, venue_id)
        places = list_locations(session, venue_id)
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
    return {"items": items, "alerts": alerts, "locations": places}


def set_on_hand(venue_id: uuid.UUID, sku: str, on_hand) -> None:
    with session_scope() as session:
        try:
            apply_count(session, venue_id, sku, on_hand)
            session.commit()
        except NotFound:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
