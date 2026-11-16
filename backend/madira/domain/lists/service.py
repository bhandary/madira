"""List curation. The selector and the margin math live here, not in the model."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from madira.domain.session import session_scope
from madira.fixtures_data import curate_list as curate_list_fixture
from madira.models import BeverageList, ListItem


def curate(
    venue_id: uuid.UUID,
    budget: float = 12000,
    target_margin: float = 3.2,
    name: str = "Maison Madira autumn list",
) -> dict:
    payload = curate_list_fixture(budget=budget, target_margin=target_margin)
    payload["name"] = name
    with session_scope() as session:
        beverage_list = BeverageList(
            venue_id=venue_id,
            name=name,
            budget=payload["budget"],
            currency=payload["currency"],
            target_margin=target_margin,
            notes=payload["notes"],
        )
        session.add(beverage_list)
        session.flush()
        for item in payload["items"]:
            session.add(
                ListItem(
                    venue_id=venue_id,
                    list_id=beverage_list.id,
                    category=item["category"],
                    name=item["name"],
                    producer=item["producer"],
                    region=item["region"],
                    style=item["style"],
                    vintage=item["vintage"],
                    cost=item["cost"],
                    pour_price=item["pour_price"],
                    bottle_price=item["bottle_price"],
                    currency=item["currency"],
                    margin_pct=item["margin_pct"],
                )
            )
        payload["list_id"] = beverage_list.id
        session.commit()
        return payload


def list_lists(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        rows = session.scalars(
            select(BeverageList)
            .where(BeverageList.venue_id == venue_id)
            .order_by(BeverageList.created_at.desc(), BeverageList.id.desc())
        ).all()
        return {
            "lists": [
                {
                    "id": row.id,
                    "name": row.name,
                    "budget": row.budget,
                    "currency": row.currency,
                    "target_margin": row.target_margin,
                    "item_count": len(row.items),
                    "notes": row.notes,
                    "items": [
                        {
                            "category": item.category,
                            "name": item.name,
                            "producer": item.producer,
                            "region": item.region,
                            "style": item.style,
                            "cost": item.cost,
                            "pour_price": item.pour_price,
                            "bottle_price": item.bottle_price,
                            "currency": item.currency,
                            "margin_pct": item.margin_pct,
                        }
                        for item in row.items
                    ],
                }
                for row in rows
            ]
        }
