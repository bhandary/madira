"""List health. Every flag is computed here. The model does not invent one."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.inventory.ledger import as_qty, depletion_by_sku
from madira.domain.lists.coverage import confirmed_dishes
from madira.domain.lists.pricing import economics, load_rules, normalize_category, price_for
from madira.domain.pairing.profiles import derive_profile
from madira.domain.pairing.slots import dish_profile, score
from madira.models import BeverageList, InventoryItem, ListSection, TastingNote

PAIR_FLOOR = 30
_UNDER = 85


def _notes(session: Session, venue_id: uuid.UUID) -> dict:
    rows = session.scalars(
        select(TastingNote)
        .where(TastingNote.venue_id == venue_id, TastingNote.status == "approved")
        .order_by(TastingNote.approved_at.desc(), TastingNote.id.desc())
    ).all()
    found = {}
    for row in rows:
        found.setdefault(row.product_id, row)
    return found


def _on_hand(session: Session, venue_id: uuid.UUID) -> dict[uuid.UUID, int]:
    found: dict[uuid.UUID, int] = {}
    rows = session.scalars(select(InventoryItem).where(InventoryItem.venue_id == venue_id)).all()
    for row in rows:
        found[row.sku_id] = found.get(row.sku_id, 0) + int(as_qty(row.on_hand))
    return found


def _outlier(actual: int, rule: int) -> bool:
    if actual <= 0 or rule <= 0:
        return False
    return abs(int(actual) - int(rule)) * 100 > int(rule) * 15


def _window(today: date, drink_by_year: int | None, best_by: date | None) -> str:
    horizon = today + timedelta(days=90)
    reasons = []
    if best_by is not None and best_by <= horizon:
        if best_by < today:
            reasons.append(f"best by {best_by.isoformat()} has passed")
        else:
            reasons.append(f"best by {best_by.isoformat()} is within 90 days")
    if drink_by_year is not None:
        end = date(int(drink_by_year), 12, 31)
        if end <= horizon:
            if end < today:
                reasons.append(f"the drink window closed in {int(drink_by_year)}")
            else:
                reasons.append(f"the drink window closes in {int(drink_by_year)}")
    return "; ".join(reasons)


def list_health(session: Session, beverage_list: BeverageList, *, today: date | None = None) -> dict:
    venue_id = beverage_list.venue_id
    rules = load_rules(session, venue_id)
    notes = _notes(session, venue_id)
    stock = _on_hand(session, venue_id)
    depletion = depletion_by_sku(session, venue_id)
    dishes = confirmed_dishes(session, venue_id)
    dish_profiles = [(dish, dish_profile(dish)) for dish in dishes]
    items = list(beverage_list.items)
    flags: list[dict] = []
    paired_dishes: set[uuid.UUID] = set()
    item_scores: dict[uuid.UUID, int] = {}

    for item in items:
        product = item.sku.variant.product
        profile = derive_profile(product, notes.get(product.id))
        best = 0
        for dish, dish_view in dish_profiles:
            points = score(dish_view, profile)
            if points > best:
                best = points
            if points >= PAIR_FLOOR:
                paired_dishes.add(dish.id)
        item_scores[item.id] = best

    for dish, _profile in dish_profiles:
        if dish.id not in paired_dishes:
            flags.append(
                {
                    "code": "dish_unpaired",
                    "message": f"{dish.name} has no bottle on this list that pairs with it.",
                    "dish_id": dish.id,
                    "item_id": None,
                    "sku_id": None,
                    "section": "",
                }
            )

    if dish_profiles:
        for item in items:
            if item_scores.get(item.id, 0) >= PAIR_FLOOR:
                continue
            name = item.sku.variant.product.name
            flags.append(
                {
                    "code": "item_unpaired",
                    "message": f"{name} does not pair with a dish on the confirmed menu.",
                    "dish_id": None,
                    "item_id": item.id,
                    "sku_id": item.sku_id,
                    "section": item.section or "",
                }
            )

    seen_slow: set[uuid.UUID] = set()
    for item in items:
        if item.sku_id in seen_slow:
            continue
        on_hand = stock.get(item.sku_id, 0)
        moved = depletion.get(item.sku_id, 0)
        if on_hand > 0 and moved <= 0:
            seen_slow.add(item.sku_id)
            name = item.sku.variant.product.name
            flags.append(
                {
                    "code": "slow_mover",
                    "message": f"{name} has {on_hand} on hand and no sales in 30 days.",
                    "dish_id": None,
                    "item_id": item.id,
                    "sku_id": item.sku_id,
                    "section": item.section or "",
                }
            )

    for item in items:
        category = normalize_category(item.sku.variant.product.category)
        quote = price_for(int(item.cost or 0), category, rules)
        off = []
        if _outlier(int(item.bottle_price or 0), quote["bottle_price"]):
            off.append("bottle")
        if _outlier(int(item.pour_price or 0), quote["glass_price"]):
            off.append("glass")
        if off:
            shown = economics(int(item.cost or 0), int(item.bottle_price or 0), int(item.pour_price or 0))
            name = item.sku.variant.product.name
            flags.append(
                {
                    "code": "price_outlier",
                    "message": (
                        f"{name} {', '.join(off)} price is more than 15% from the rule price. "
                        f"Beverage cost is {shown['beverage_cost_pct']}%."
                    ),
                    "dish_id": None,
                    "item_id": item.id,
                    "sku_id": item.sku_id,
                    "section": item.section or "",
                }
            )

    budget = int(beverage_list.budget or 0)
    if budget > 0:
        sections = section_rows(session, beverage_list)
        for section in sections:
            if section.budget_share_pct is None:
                continue
            share = int(section.budget_share_pct)
            allocated = budget * share // 100
            spend = sum(int(item.cost or 0) for item in items if item.section_id == section.id or item.section == section.name)
            if spend > allocated:
                flags.append(
                    {
                        "code": "section_over",
                        "message": f"{section.name} spends {spend} cents against a {share}% share of {allocated} cents.",
                        "dish_id": None,
                        "item_id": None,
                        "sku_id": None,
                        "section": section.name,
                    }
                )
            elif allocated > 0 and spend * 100 < allocated * _UNDER:
                flags.append(
                    {
                        "code": "section_under",
                        "message": f"{section.name} spends {spend} cents, under its {share}% share of {allocated} cents.",
                        "dish_id": None,
                        "item_id": None,
                        "sku_id": None,
                        "section": section.name,
                    }
                )

    clock = today or date.today()
    seen_window: set[uuid.UUID] = set()
    for item in items:
        if item.sku_id in seen_window:
            continue
        variant = item.sku.variant
        reason = _window(clock, variant.drink_by_year, item.sku.best_by)
        if not reason:
            continue
        seen_window.add(item.sku_id)
        name = variant.product.name
        flags.append(
            {
                "code": "drink_window",
                "message": f"{name}: {reason}.",
                "dish_id": None,
                "item_id": item.id,
                "sku_id": item.sku_id,
                "section": item.section or "",
            }
        )

    flags.sort(key=lambda flag: (flag["code"], flag["message"], str(flag["item_id"] or ""), str(flag["dish_id"] or "")))
    return {"list_id": beverage_list.id, "flags": flags}


def section_rows(session: Session, beverage_list: BeverageList) -> list[ListSection]:
    return list(
        session.scalars(
            select(ListSection)
            .where(ListSection.list_id == beverage_list.id, ListSection.venue_id == beverage_list.venue_id)
            .order_by(ListSection.position, ListSection.name, ListSection.id)
        )
    )
