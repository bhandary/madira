from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.db import SessionLocal, init_db
from madira.fixtures_data import INVENTORY, LESSONS, QUIZ, SUPPLIERS
from madira.models import InventoryItem, Lesson, Quiz, Supplier


def seed(session: Session | None = None) -> None:
    own = False
    if session is None:
        init_db()
        session = SessionLocal()
        own = True
    try:
        if session.scalar(select(Supplier).limit(1)):
            return
        suppliers: dict[str, Supplier] = {}
        for row in SUPPLIERS:
            s = Supplier(**row)
            session.add(s)
            session.flush()
            suppliers[s.name] = s
        for row in INVENTORY:
            supplier = suppliers[row["supplier"]]
            session.add(
                InventoryItem(
                    sku=row["sku"],
                    name=row["name"],
                    category=row["category"],
                    supplier_id=supplier.id,
                    on_hand=row["on_hand"],
                    par=row["par"],
                    unit_cost=row["unit_cost"],
                    depletion_30d=row["depletion_30d"],
                    unit=row.get("unit", "btl"),
                )
            )
        for row in LESSONS:
            lesson = Lesson(**row)
            session.add(lesson)
            session.flush()
            if row["slug"] == "daily-briefing":
                session.add(Quiz(lesson_id=lesson.id, title=QUIZ["title"], questions=QUIZ["questions"]))
        session.commit()
    finally:
        if own:
            session.close()
