"""An active register makes depletion and par follow POS sales."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, select

from madira.db import SessionLocal, init_db
from madira.domain.inventory.ledger import depletion_by_sku, ensure_location, post_movement
from madira.domain.inventory.par import propose_par_changes, suggested_par
from madira.domain.pos.adapter import SaleLine
from madira.domain.pos.service import run_sync
from madira.models import InventoryItem, Organization, PosConnection, PosItemMapping, PosSale, PosSyncRun, Product, ProductVariant, Sku, Venue
from madira.seed import seed
from madira.tenancy import OWNER, RequestContext, bind, ensure_demo_tenant, reset


class OneSale:
    def __init__(self, line: SaleLine) -> None:
        self.line = line

    def list_locations(self):
        return []

    def list_variations(self):
        return []

    def search_sales(self, location_id, start_at, end_at):
        del location_id, start_at, end_at
        return [self.line]


def _clear(venue_id) -> None:
    session = SessionLocal()
    try:
        session.execute(delete(PosSale).where(PosSale.venue_id == venue_id))
        session.execute(delete(PosItemMapping).where(PosItemMapping.venue_id == venue_id))
        session.execute(delete(PosSyncRun).where(PosSyncRun.venue_id == venue_id))
        session.execute(delete(PosConnection).where(PosConnection.venue_id == venue_id))
        session.commit()
    finally:
        session.close()


def test_active_pos_replaces_the_count_estimate():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    token = bind(
        RequestContext(
            user_id=demo.user_id,
            email="owner@maison-madira.demo",
            name="Owner",
            venue_id=demo.venue_id,
            organization_id=demo.organization_id,
            role=OWNER,
        )
    )
    barcode = f"P-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc)
    try:
        _clear(demo.venue_id)
        session = SessionLocal()
        try:
            org = session.get(Organization, demo.organization_id)
            assert org is not None
            venue = session.get(Venue, demo.venue_id)
            product = Product(organization_id=org.id, category="wine", producer="House", name=f"POS depletion {barcode}")
            session.add(product)
            session.flush()
            variant = ProductVariant(product_id=product.id, vintage="2022", bottle_size="750ml")
            session.add(variant)
            session.flush()
            sku = Sku(venue_id=venue.id, product_variant_id=variant.id, barcode=barcode, par=4)
            session.add(sku)
            session.flush()
            place = ensure_location(session, venue.id, "Main Bar", "bar", "Service bar")
            post_movement(
                session,
                venue.id,
                sku=barcode,
                location_id=place.id,
                quantity=90,
                movement_type="opening_balance",
                created_at=now - timedelta(days=40),
                reason="opening",
            )
            post_movement(
                session,
                venue.id,
                sku=barcode,
                location_id=place.id,
                quantity=-60,
                movement_type="count_adjustment",
                created_at=now - timedelta(days=2),
                reason="count",
            )
            session.commit()
            sku_id = sku.id
            without = depletion_by_sku(session, venue.id, now=now)
            assert without[sku_id] == Decimal("60")
            session.add(
                PosConnection(
                    venue_id=venue.id,
                    provider="demo",
                    status="active",
                    location_id="demo-bar",
                    location_name="Main Bar",
                )
            )
            session.commit()
            quiet = depletion_by_sku(session, venue.id, now=now)
            assert sku_id not in quiet
            from madira.models import PosItemMapping

            session.add(
                PosItemMapping(
                    venue_id=venue.id,
                    provider="demo",
                    item_id="item-pos",
                    variation_id="var-pos",
                    sku_id=sku_id,
                    pour_ml=750,
                    units_per_sale=Decimal("1"),
                )
            )
            session.commit()
            closed = now - timedelta(hours=3)
            result = run_sync(
                session,
                venue.id,
                OneSale(SaleLine("order-pos", "line-pos", "item-pos", "var-pos", "POS depletion", "30", closed.isoformat())),
            )
            session.commit()
            assert result["posted"] == 1
            posted = depletion_by_sku(session, venue.id, now=now)
            assert posted[sku_id] == Decimal("30")
            item = session.scalar(select(InventoryItem).where(InventoryItem.venue_id == venue.id, InventoryItem.sku_id == sku_id))
            assert item is not None
            assert item.on_hand == Decimal("0")
        finally:
            session.close()
        proposed, rationale = suggested_par(Decimal("30"), 4, 7, 4)
        assert proposed == 11
        assert "30" in rationale
        found = next(row for row in propose_par_changes(demo.venue_id)["proposals"] if row["sku"] == barcode)
        assert found["depletion_30d"] == 30
        assert found["proposed_par"] == 11
        assert "count" not in found["rationale"].lower()
    finally:
        reset(token)
        _clear(demo.venue_id)
