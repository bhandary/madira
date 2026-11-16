from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from madira.agents.tools import curate_beverage_list
from madira.db import SessionLocal
from madira.models import BeverageList

router = APIRouter()


class ListBody(BaseModel):
    budget: float = 12000
    target_margin: float = 3.2
    name: str = "Maison Madira autumn list"


@router.post("/lists/curate")
def lists_curate(body: ListBody) -> dict[str, Any]:
    return json.loads(curate_beverage_list(budget=body.budget, target_margin=body.target_margin, name=body.name))


@router.get("/lists")
def lists() -> dict[str, Any]:
    session = SessionLocal()
    try:
        rows = session.scalars(select(BeverageList).order_by(BeverageList.id.desc())).all()
        return {
            "lists": [
                {
                    "id": row.id,
                    "name": row.name,
                    "budget": row.budget,
                    "target_margin": row.target_margin,
                    "item_count": len(row.items),
                    "notes": row.notes,
                    "items": [
                        {
                            "category": i.category,
                            "name": i.name,
                            "producer": i.producer,
                            "region": i.region,
                            "style": i.style,
                            "cost": i.cost,
                            "pour_price": i.pour_price,
                            "bottle_price": i.bottle_price,
                            "margin_pct": i.margin_pct,
                        }
                        for i in row.items
                    ],
                }
                for row in rows
            ]
        }
    finally:
        session.close()
