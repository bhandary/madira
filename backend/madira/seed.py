from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from madira.db import SessionLocal, init_db
from madira.domain.catalog.service import ensure_sku
from madira.money import DEFAULT_CURRENCY, to_minor
from madira.models import InventoryItem, Lesson, Quiz, Sku, StockMovement, Supplier, SupplierContact
from madira.tenancy import bind, demo_posture, ensure_demo_tenant, reset


def seed(session: Session | None = None) -> None:
    if not demo_posture():
        if session is None:
            init_db()
        return

    own = False
    if session is None:
        init_db()
        session = SessionLocal()
        own = True
    try:
        ctx = ensure_demo_tenant(session)
        venue_id = ctx.venue_id
        token = bind(ctx)
        try:
            if session.scalar(select(Supplier.id).where(Supplier.venue_id == venue_id).limit(1)) is None:
                _seed_demo_catalog(session, venue_id)
            _ensure_purchasing_profiles(session, venue_id)
            from madira.domain.compliance.service import ensure_demo_records

            ensure_demo_records(session, ctx)
            _ensure_demo_ledger(session, venue_id)
            session.commit()
        finally:
            reset(token)
    finally:
        if own:
            session.close()


def _seed_demo_catalog(session: Session, venue_id) -> None:
    from madira.agents.demo.fixtures import INVENTORY, LESSONS, QUIZ, SUPPLIERS

    suppliers: dict[str, Supplier] = {}
    for row in SUPPLIERS:
        supplier = Supplier(**row, venue_id=venue_id)
        session.add(supplier)
        session.flush()
        suppliers[supplier.name] = supplier
    for row in INVENTORY:
        supplier = suppliers[row["supplier"]]
        stock = ensure_sku(
            session,
            venue_id,
            category=row["category"],
            name=row["name"],
            barcode=row["sku"],
            par=row["par"],
            cost=to_minor(row["unit_cost"]),
            currency=DEFAULT_CURRENCY,
        )
        session.add(
            InventoryItem(
                venue_id=venue_id,
                sku_id=stock.id,
                supplier_id=supplier.id,
                on_hand=row["on_hand"],
                unit=row.get("unit", "btl"),
            )
        )
    for row in LESSONS:
        lesson = Lesson(**row, venue_id=venue_id)
        session.add(lesson)
        session.flush()
        if row["slug"] == "daily-briefing":
            session.add(
                Quiz(
                    venue_id=venue_id,
                    lesson_id=lesson.id,
                    title=QUIZ["title"],
                    questions=QUIZ["questions"],
                )
            )


_PROFILES = {
    "Kermit Lynch Wine Merchant": {
        "account_number": "KL-1044",
        "order_minimum_cents": 50000,
        "default_case_size": 12,
        "delivery_days": ["Tue", "Thu"],
        "lead_time_days": 7,
        "payment_terms": "Net 30",
        "contact": {
            "name": "Claire Vasseur",
            "role": "Sales",
            "email": "claire.vasseur@kermitlynch.example",
            "phone": "510-555-0148",
        },
    },
    "Skurnik Wines": {
        "account_number": "SK-2201",
        "order_minimum_cents": 30000,
        "default_case_size": 6,
        "delivery_days": ["Mon", "Wed"],
        "lead_time_days": 5,
        "payment_terms": "Net 30",
        "contact": {
            "name": "Jonah Adler",
            "role": "Portfolio manager",
            "email": "jonah.adler@skurnik.example",
            "phone": "212-555-0194",
        },
    },
    "Bay Area Craft Beer Collective": {
        "account_number": "BAC-88",
        "order_minimum_cents": 15000,
        "default_case_size": 12,
        "delivery_days": ["Fri"],
        "lead_time_days": 3,
        "payment_terms": "COD",
        "contact": {
            "name": "Mina Cho",
            "role": "Orders",
            "email": "mina.cho@bacbc.example",
            "phone": "415-555-0172",
        },
    },
    "World Sake Imports": {
        "account_number": "WS-19",
        "order_minimum_cents": 20000,
        "default_case_size": 6,
        "delivery_days": ["Thu"],
        "lead_time_days": 10,
        "payment_terms": "Net 15",
        "contact": {
            "name": "Aiko Mori",
            "role": "Importer",
            "email": "aiko.mori@worldsake.example",
            "phone": "206-555-0160",
        },
    },
}


def _ensure_purchasing_profiles(session: Session, venue_id) -> None:
    """Case sizes, minimums, delivery days, and one contact per demo supplier.

    Does not insert or edit SKUs, menus, or lists.
    """

    for name, profile in _PROFILES.items():
        supplier = session.scalar(select(Supplier).where(Supplier.venue_id == venue_id, Supplier.name == name))
        if supplier is None:
            continue
        if supplier.account_number is None:
            supplier.account_number = profile["account_number"]
        if supplier.payment_terms is None:
            supplier.payment_terms = profile["payment_terms"]
        if int(supplier.order_minimum_cents or 0) == 0:
            supplier.order_minimum_cents = profile["order_minimum_cents"]
        if int(supplier.default_case_size or 12) == 12 and profile["default_case_size"] != 12:
            supplier.default_case_size = profile["default_case_size"]
        if not supplier.delivery_days:
            supplier.delivery_days = list(profile["delivery_days"])
        if int(supplier.lead_time_days or 7) == 7 and profile["lead_time_days"] != 7:
            supplier.lead_time_days = profile["lead_time_days"]
        existing = session.scalar(
            select(SupplierContact.id).where(SupplierContact.supplier_id == supplier.id).limit(1)
        )
        if existing is None:
            contact = profile["contact"]
            session.add(
                SupplierContact(
                    venue_id=venue_id,
                    supplier_id=supplier.id,
                    name=contact["name"],
                    role=contact["role"],
                    email=contact["email"],
                    phone=contact["phone"],
                    is_primary=True,
                )
            )


_WEIGHTS = {
    "wine": (7, 2, 1),
    "beer": (2, 2, 6),
    "spirit": (3, 7, 0),
    "sake": (6, 2, 2),
}


def _split_units(total: int, weights: tuple[int, int, int]) -> list[int]:
    total = int(total)
    if total <= 0:
        return [0, 0, 0]
    base = sum(weights)
    parts = [total * weight // base for weight in weights]
    left = total - sum(parts)
    order = sorted(range(3), key=lambda index: (weights[index], -index), reverse=True)
    cursor = 0
    while left:
        parts[order[cursor % 3]] += 1
        left -= 1
        cursor += 1
    return parts


def _draw_sales(opening: list[int], need: int) -> list[int]:
    sales = [0, 0, 0]
    left = int(need)
    order = sorted(range(3), key=lambda index: (opening[index], -index), reverse=True)
    for index in order:
        if left <= 0:
            break
        take = min(opening[index], left)
        sales[index] = take
        left -= take
    if left:
        raise RuntimeError("seed sales exceed opening stock")
    return sales


def _ensure_demo_ledger(session: Session, venue_id) -> None:
    """Locations, bins, and movements that reproduce the seeded cellar.

    Opening balances are dated outside the 30-day window. POS sales inside the
    window sum to the fixture ``depletion_30d``, and the net of every movement
    is the fixture ``on_hand``. A later count is left alone. A database that
    migration backfilled with only an opening balance gets the missing sales
    without changing that on-hand total.
    """

    from datetime import datetime, timedelta, timezone

    from madira.agents.demo.fixtures import INVENTORY
    from madira.domain.inventory.ledger import as_qty, ensure_bin, ensure_location, post_movement

    session.flush()
    now = datetime.now(timezone.utc)
    cellar = ensure_location(session, venue_id, "Main Cellar", "cellar", "House cellar")
    bar = ensure_location(session, venue_id, "Main Bar", "bar", "Service bar")
    walk_in = ensure_location(session, venue_id, "Walk-In Cooler", "walk_in", "Cold storage")
    places = (cellar, bar, walk_in)
    bins = {
        "CEL-A1": ensure_bin(session, venue_id, cellar.id, "CEL-A1", "Cellar bay A1"),
        "CEL-A2": ensure_bin(session, venue_id, cellar.id, "CEL-A2", "Cellar bay A2"),
        "BAR-01": ensure_bin(session, venue_id, bar.id, "BAR-01", "Main bar well"),
        "WLK-01": ensure_bin(session, venue_id, walk_in.id, "WLK-01", "Walk-in door"),
    }
    opened = now - timedelta(days=40)
    cutoff = now - timedelta(days=30)
    for index, row in enumerate(INVENTORY):
        stock = session.scalar(
            select(Sku).where(Sku.venue_id == venue_id, func.upper(Sku.barcode) == row["sku"].upper())
        )
        if stock is None:
            continue
        item = session.scalar(
            select(InventoryItem).where(InventoryItem.venue_id == venue_id, InventoryItem.sku_id == stock.id)
        )
        if item is None:
            continue
        target_on = Decimal(int(row["on_hand"]))
        target_dep = Decimal(int(row["depletion_30d"]))
        existing = session.scalars(
            select(StockMovement).where(StockMovement.venue_id == venue_id, StockMovement.sku_id == stock.id)
        ).all()
        if not existing:
            weights = _WEIGHTS.get(row["category"], _WEIGHTS["wine"])
            opening = _split_units(int(target_on + target_dep), weights)
            sales = _draw_sales(opening, int(target_dep))
            for place_index, place in enumerate(places):
                spot = _seed_bin(bins, index, place_index)
                if opening[place_index] > 0:
                    post_movement(
                        session,
                        venue_id,
                        sku=row["sku"],
                        location_id=place.id,
                        bin_id=spot.id,
                        quantity=opening[place_index],
                        movement_type="opening_balance",
                        unit_cost_cents=int(stock.cost or 0),
                        source_type="seed",
                        source_id=f"seed:{row['sku']}",
                        reason="Seeded opening balance",
                        created_at=opened,
                    )
                if sales[place_index] > 0:
                    post_movement(
                        session,
                        venue_id,
                        sku=row["sku"],
                        location_id=place.id,
                        bin_id=spot.id,
                        quantity=-sales[place_index],
                        movement_type="sale",
                        unit_cost_cents=int(stock.cost or 0),
                        source_type="pos",
                        source_id=f"seed-sale:{row['sku']}:{place_index}",
                        reason="Seeded POS sale",
                        created_at=now - timedelta(days=3 + place_index * 4),
                    )
            continue
        total = sum((as_qty(move.quantity) for move in existing), Decimal("0"))
        sales_total = sum(
            (
                abs(as_qty(move.quantity))
                for move in existing
                if move.movement_type == "sale" and move.created_at is not None and move.created_at >= cutoff
            ),
            Decimal("0"),
        )
        if total == target_on and sales_total >= target_dep:
            continue
        if total == target_on and sales_total < target_dep:
            gap = target_dep - sales_total
            spot = bins["CEL-A1"] if index % 2 == 0 else bins["CEL-A2"]
            post_movement(
                session,
                venue_id,
                sku=row["sku"],
                location_id=cellar.id,
                bin_id=spot.id,
                quantity=gap,
                movement_type="opening_balance",
                unit_cost_cents=int(stock.cost or 0),
                source_type="seed",
                source_id=f"seed-gap:{row['sku']}",
                reason="Seeded opening balance",
                created_at=opened,
            )
            post_movement(
                session,
                venue_id,
                sku=row["sku"],
                location_id=cellar.id,
                bin_id=spot.id,
                quantity=-gap,
                movement_type="sale",
                unit_cost_cents=int(stock.cost or 0),
                source_type="pos",
                source_id=f"seed-sale:{row['sku']}:gap",
                reason="Seeded POS sale",
                created_at=now - timedelta(days=4),
            )


def _seed_bin(bins: dict, index: int, place_index: int):
    if place_index == 0:
        return bins["CEL-A1"] if index % 2 == 0 else bins["CEL-A2"]
    if place_index == 1:
        return bins["BAR-01"]
    return bins["WLK-01"]
