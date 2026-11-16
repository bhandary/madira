from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.db import SessionLocal, init_db
from madira.fixtures_data import INVENTORY, LESSONS, QUIZ, SUPPLIERS
from madira.money import DEFAULT_CURRENCY, to_minor
from madira.models import InventoryItem, Lesson, Quiz, Supplier
from madira.tenancy import bind, ensure_demo_tenant, reset


def seed(session: Session | None = None) -> None:
    own = False
    if session is None:
        init_db()
        session = SessionLocal()
        own = True
    try:
        ctx = ensure_demo_tenant(session)
        venue_id = ctx.venue_id
        if session.scalar(select(Supplier.id).where(Supplier.venue_id == venue_id).limit(1)):
            return
        token = bind(ctx)
        try:
            suppliers: dict[str, Supplier] = {}
            for row in SUPPLIERS:
                supplier = Supplier(**row, venue_id=venue_id)
                session.add(supplier)
                session.flush()
                suppliers[supplier.name] = supplier
            for row in INVENTORY:
                supplier = suppliers[row["supplier"]]
                session.add(
                    InventoryItem(
                        venue_id=venue_id,
                        sku=row["sku"],
                        name=row["name"],
                        category=row["category"],
                        supplier_id=supplier.id,
                        on_hand=row["on_hand"],
                        par=row["par"],
                        unit_cost=to_minor(row["unit_cost"]),
                        currency=DEFAULT_CURRENCY,
                        depletion_30d=row["depletion_30d"],
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
            session.commit()
        finally:
            reset(token)
    finally:
        if own:
            session.close()
