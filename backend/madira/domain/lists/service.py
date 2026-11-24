"""List curation. The selector and the margin math live here, not in the model."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from madira.domain.catalog.service import beverage_fields, ensure_sku
from madira.domain.errors import require_demo
from madira.domain.session import session_scope
from madira.models import BeverageList, ListItem


def curate(
    venue_id: uuid.UUID,
    budget: float = 12000,
    target_margin: float = 3.2,
    name: str = "Maison Madira autumn list",
) -> dict:
    require_demo("List curation")
    from madira.agents.demo.fixtures import curate_list as curate_list_fixture

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
            stock = ensure_sku(
                session,
                venue_id,
                category=item["category"],
                name=item["name"],
                producer=item["producer"],
                region=item["region"],
                style=item["style"],
                vintage=item["vintage"],
            )
            session.add(
                ListItem(
                    venue_id=venue_id,
                    list_id=beverage_list.id,
                    sku_id=stock.id,
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


def item_view(item: ListItem) -> dict:
    """List row text comes from the catalog SKU, not a copy on the row."""

    fields = beverage_fields(item.sku)
    return {
        "category": fields["category"],
        "name": fields["name"],
        "producer": fields["producer"],
        "region": fields["region"],
        "style": fields["style"],
        "vintage": fields["vintage"],
        "section": item.section,
        "bottle_size": item.sku.variant.bottle_size,
        "cost": item.cost,
        "pour_price": item.pour_price,
        "bottle_price": item.bottle_price,
        "currency": item.currency,
        "margin_pct": item.margin_pct,
        "product_id": item.sku.variant.product_id,
    }


def _ordered_items(row: BeverageList) -> list[ListItem]:
    items = list(row.items)
    if any(item.position for item in items):
        items.sort(key=lambda item: (item.position, str(item.id)))
    return items


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
                    "source_filename": row.source_filename,
                    "items": [item_view(item) for item in _ordered_items(row)],
                }
                for row in rows
            ]
        }
