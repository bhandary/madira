"""Inventory and purchasing services: reorder math is integer, and stock stays in its venue."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.domain.errors import NotFound
from madira.domain.inventory.service import set_on_hand, snapshot
from madira.domain.purchasing.service import draft, list_orders
from madira.main import app
from madira.models import InventoryItem, Supplier, Venue
from madira.money import DEFAULT_CURRENCY
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant


def _other_venue(organization_id: uuid.UUID) -> uuid.UUID:
    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "cellar-service-other"))
        if venue is None:
            venue = Venue(organization_id=organization_id, name="Cellar Service Other", slug="cellar-service-other")
            session.add(venue)
            session.flush()
            supplier = Supplier(venue_id=venue.id, name="Other House Wines", kind="distributor")
            session.add(supplier)
            session.flush()
            session.add(
                InventoryItem(
                    venue_id=venue.id,
                    sku="B-ONLY-01",
                    name="Other House Bottle",
                    category="wine",
                    supplier_id=supplier.id,
                    on_hand=0,
                    par=4,
                    unit_cost=500,
                    currency=DEFAULT_CURRENCY,
                    depletion_30d=1,
                    unit="btl",
                )
            )
            session.commit()
            return venue.id
        return venue.id
    finally:
        session.close()


def test_reorder_quantity_and_line_cost_are_integers():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    set_on_hand(demo.venue_id, "w-mus-01", 1)
    body = snapshot(demo.venue_id)
    muscadet = next(item for item in body["items"] if item["sku"] == "W-MUS-01")
    assert muscadet["on_hand"] == 1
    assert muscadet["unit_cost"] == 1800
    assert muscadet["reorder_qty"] == 11
    assert muscadet["low"] is True
    alert = next(row for row in body["alerts"] if row["sku"] == "W-MUS-01")
    assert alert["message"] == "Muscadet Domaine de l'Ecu is at 1 btl (par 12)"
    drafted = draft(demo.venue_id)
    line = next(
        item
        for order in drafted["orders"]
        for item in order["lines"]
        if item["sku"] == "W-MUS-01"
    )
    assert line["line_cost"] == 1800 * 11
    assert all(isinstance(order["total"], int) for order in drafted["orders"])
    assert "a2ui_operations" not in drafted


def test_stock_and_drafts_stay_inside_the_venue():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    other = _other_venue(demo.organization_id)
    with pytest.raises(NotFound) as raised:
        set_on_hand(demo.venue_id, "B-ONLY-01", 9)
    assert raised.value.message == "unknown sku B-ONLY-01"
    assert all(item["sku"] != "B-ONLY-01" for item in snapshot(demo.venue_id)["items"])
    set_on_hand(other, "B-ONLY-01", 1)
    other_orders = draft(other)
    assert other_orders["orders"]
    assert other_orders["orders"][0]["lines"][0]["sku"] == "B-ONLY-01"
    assert other_orders["orders"][0]["lines"][0]["line_cost"] == 500 * 3
    demo_skus = {line["sku"] for order in list_orders(demo.venue_id)["orders"] for line in order["lines"]}
    assert "B-ONLY-01" not in demo_skus


def test_inventory_routes_return_the_same_surfaces():
    init_db()
    seed()
    with TestClient(app) as client:
        missing = client.patch("/inventory/NO-SUCH-01", json={"on_hand": 1})
        assert missing.status_code == 404
        assert missing.json()["detail"] == "unknown sku NO-SUCH-01"
        patched = client.patch("/inventory/W-MUS-01", json={"on_hand": 1})
        assert patched.status_code == 200
        body = patched.json()
        assert body["a2ui_operations"][0]["createSurface"]["surfaceId"] == "inventory"
        muscadet = next(item for item in body["items"] if item["sku"] == "W-MUS-01")
        assert muscadet["on_hand"] == 1
        drafted = client.post("/purchase-orders/draft")
        assert drafted.status_code == 200
        orders = drafted.json()
        assert orders["a2ui_operations"][0]["createSurface"]["surfaceId"] == "purchase-orders"
        assert "PurchaseOrderTable" in json.dumps(orders["a2ui_operations"])
