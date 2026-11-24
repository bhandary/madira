"""Health flags come from the list, the menu, the ledger, and the pricing rules."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.domain.catalog.service import ensure_sku
from madira.domain.lists.service import add_item, curate, health_for, update_item
from madira.domain.session import session_scope
from madira.models import Dish, InventoryItem, ListSection, Menu, MenuVersion, ProductVariant, Sku, StorageZone
from madira.auth import utcnow
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant


def _codes(payload: dict) -> set[str]:
    return {flag["code"] for flag in payload["flags"]}


def test_health_flags_price_window_section_and_slow_stock():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    with session_scope() as session:
        for zone in session.scalars(select(StorageZone).where(StorageZone.venue_id == demo.venue_id)).all():
            zone.capacity_bottles = 80
        session.commit()
    created = curate(demo.venue_id, budget=12000, target_margin=3.2, name="Health list")
    item = created["items"][0]
    with session_scope() as session:
        slow = ensure_sku(
            session,
            demo.venue_id,
            name=f"Quiet Bottle {uuid.uuid4().hex[:6]}",
            category="wine",
            producer="House",
            cost=500,
            barcode=f"H-QUIET-{uuid.uuid4().hex[:8]}",
        )
        session.add(InventoryItem(venue_id=demo.venue_id, sku_id=slow.id, on_hand=4, unit="btl"))
        session.commit()
        slow_id = slow.id
    added = add_item(demo.venue_id, created["list_id"], slow_id, "Wine")
    update_item(demo.venue_id, created["list_id"], item["id"], {"bottle_price": 100, "pour_price": 100})
    with session_scope() as session:
        sku = session.get(Sku, item["sku_id"])
        variant = session.get(ProductVariant, sku.product_variant_id)
        variant.drink_by_year = date.today().year - 1
        sku.best_by = date.today() - timedelta(days=1)
        section = session.scalar(select(ListSection).where(ListSection.list_id == created["list_id"], ListSection.name == "Wine"))
        section.budget_share_pct = 0
        session.commit()
    flags = health_for(demo.venue_id, created["list_id"])
    codes = _codes(flags)
    assert "price_outlier" in codes
    assert "drink_window" in codes
    assert "section_over" in codes
    assert "slow_mover" in codes
    quiet = next(row for row in flags["flags"] if row["code"] == "slow_mover")
    assert "Quiet Bottle" in quiet["message"]
    assert "no sales in 30 days" in quiet["message"]
    assert added["list_id"] == created["list_id"]


def test_health_flags_unpaired_dishes_and_bottles():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    with session_scope() as session:
        sku = ensure_sku(
            session,
            demo.venue_id,
            name="Dry Tannin",
            category="wine",
            producer="House",
            body="light",
            acidity="low",
            sweetness="dry",
            tannin="high",
            cost=1800,
            barcode="H-TAN",
        )
        from madira.models import BeverageList, ListItem

        beverage = BeverageList(
            venue_id=demo.venue_id,
            name="Pair check",
            budget=100000,
            currency="USD",
            target_margin=3,
            notes="",
        )
        session.add(beverage)
        session.flush()
        session.add(
            ListItem(
                venue_id=demo.venue_id,
                list_id=beverage.id,
                sku_id=sku.id,
                section="Wine",
                position=1,
                cost=1800,
                pour_price=1200,
                bottle_price=4900,
                currency="USD",
                margin_pct=0,
            )
        )
        menu = Menu(venue_id=demo.venue_id, name="Rice", source_type="text", raw_text="Plain rice")
        session.add(menu)
        session.flush()
        version = MenuVersion(
            venue_id=demo.venue_id,
            menu_id=menu.id,
            number=1,
            source_type="text",
            status="confirmed",
            confirmed_by=demo.user_id,
            confirmed_at=utcnow(),
        )
        session.add(version)
        session.flush()
        session.add(
            Dish(
                venue_id=demo.venue_id,
                menu_id=menu.id,
                menu_version_id=version.id,
                name="Plain rice",
                price=1200,
                richness=0,
                acidity=0,
                sweetness=5,
                spice=5,
                umami=0,
            )
        )
        session.commit()
        list_id = beverage.id
    flags = _codes(health_for(demo.venue_id, list_id))
    assert "dish_unpaired" in flags
    assert "item_unpaired" in flags
