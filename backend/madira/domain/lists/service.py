"""List curation. Prices, coverage, and health come from these services.

The list curator writes section notes and nothing else. A live model that
fails raises DraftFailed. Demo mode uses the deterministic list-curator model.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from madira.domain.catalog.identity import clean
from madira.domain.catalog.service import beverage_fields
from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.lists.copy import draft_section_notes, join_notes
from madira.domain.lists.coverage import Cell, confirmed_dishes, matrix
from madira.domain.lists.health import list_health
from madira.domain.lists.pricing import (
    SECTION_SHARES,
    blended,
    default_rules,
    economics,
    ensure_default_rules,
    load_rules,
    normalize_category,
    price_for,
    public_rule,
    replace_rules,
    section_name,
)
from madira.domain.lists.selector import Pick, choose, covers
from madira.domain.pairing.profiles import derive_profile
from madira.domain.pairing.service import _tier
from madira.domain.session import session_scope
from madira.models import BeverageList, InventoryItem, ListItem, ListSection, Menu, PricingRule, Sku, StorageZone, TastingNote, Venue
from madira.money import DEFAULT_CURRENCY, to_minor

ACTION_CURATED = "list.curated"
ACTION_RULES = "list.pricing_rules_updated"
ACTION_ADDED = "list.item_added"
ACTION_UPDATED = "list.item_updated"
ACTION_REMOVED = "list.item_removed"
ACTION_SECTIONS = "list.sections_updated"

_SECTION_ORDER = ("wine", "beer", "spirits", "sake", "other")
_TENTH = Decimal("0.1")


def curate(
    venue_id: uuid.UUID,
    budget: float = 12000,
    target_margin: float = 3.2,
    name: str = "Maison Madira autumn list",
    target_beverage_cost_pct: float | None = None,
    concept: str = "",
    price_tier: str = "",
    menu_id: uuid.UUID | None = None,
) -> dict:
    budget_minor = to_minor(budget)
    if budget_minor < 0:
        raise DraftFailed("Budget cannot be negative.", 422)
    title = _label(name, "List name", 200) or "House list"
    idea = _label(concept, "Concept", 400, required=False)
    tier = _label(price_tier, "Price tier", 32, required=False)
    cost_pct = _cost_pct(target_beverage_cost_pct, target_margin)
    with session_scope() as session:
        venue = _venue(session, venue_id)
        if menu_id is not None:
            menu = session.get(Menu, menu_id)
            if menu is None or menu.venue_id != venue_id:
                raise NotFound("menu not found")
            if not confirmed_dishes(session, venue_id, menu_id):
                raise DraftFailed("This menu is not confirmed.", 409)
        ensure_default_rules(session, venue_id)
        rules = load_rules(session, venue_id)
        cells = matrix(session, venue_id, menu_id)
        picks = _candidates(session, venue_id, rules)
        capacity = _capacity(session, venue_id)
        shares = {category: share for category, share in SECTION_SHARES.items()}
        selected, open_cells = choose(picks, cells, budget_minor, capacity, shares)
        spent = sum(pick.cost for pick in selected)
        if spent > budget_minor or (capacity is not None and len(selected) > capacity):
            raise DraftFailed("The selector exceeded the budget or the cellar capacity.", 500)
        names = _section_names(selected, open_cells)
        notes = draft_section_notes(names)
        beverage_list = BeverageList(
            venue_id=venue_id,
            name=title,
            budget=budget_minor,
            currency=venue.currency or DEFAULT_CURRENCY,
            target_margin=float(target_margin),
            target_beverage_cost_pct=cost_pct,
            concept=idea,
            price_tier=tier,
            notes=join_notes(notes, names),
        )
        session.add(beverage_list)
        session.flush()
        sections = _create_sections(session, venue_id, beverage_list, names)
        currency = venue.currency or DEFAULT_CURRENCY
        for index, pick in enumerate(selected, start=1):
            quote = price_for(pick.cost, pick.category, rules)
            section = sections[section_name(pick.category)]
            session.add(
                ListItem(
                    venue_id=venue_id,
                    list_id=beverage_list.id,
                    sku_id=pick.sku_id,
                    section=section.name,
                    section_id=section.id,
                    position=index,
                    cost=pick.cost,
                    pour_price=quote["glass_price"],
                    bottle_price=quote["bottle_price"],
                    currency=currency,
                    margin_pct=0,
                )
            )
        session.flush()
        _reload(session, beverage_list)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_CURATED,
            entity_type="beverage_list",
            entity_id=beverage_list.id,
            after={
                "name": title,
                "budget": budget_minor,
                "spent": spent,
                "bottles": len(selected),
                "capacity_bottles": capacity,
                "target_beverage_cost_pct": float(cost_pct),
                "concept": idea,
                "price_tier": tier,
                "menu_id": None if menu_id is None else str(menu_id),
            },
        )
        payload = _detail(session, beverage_list)
        session.commit()
        return payload


def item_view(item: ListItem, rules: list[dict] | None = None) -> dict:
    """Prices on the row, margin from the pricing service. The stored margin is ignored."""

    fields = beverage_fields(item.sku)
    category = normalize_category(fields["category"])
    if rules is None:
        bound = object_session(item)
        rules = load_rules(bound, item.venue_id) if bound is not None else default_rules()
    cost = int(item.cost or 0)
    quote = price_for(cost, category, rules)
    bottle = int(item.bottle_price or 0)
    glass = int(item.pour_price or 0)
    econ = economics(cost, bottle, glass)
    band = _tier(bottle, glass) or _tier(quote["bottle_price"], quote["glass_price"]) or ""
    return {
        "id": item.id,
        "sku_id": item.sku_id,
        "product_id": item.sku.variant.product_id,
        "list_id": item.list_id,
        "section": item.section or "",
        "section_id": item.section_id,
        "position": int(item.position or 0),
        "category": fields["category"],
        "name": fields["name"],
        "producer": fields["producer"],
        "region": fields["region"],
        "style": fields["style"],
        "vintage": fields["vintage"],
        "bottle_size": item.sku.variant.bottle_size,
        "cost": cost,
        "pour_price": glass,
        "bottle_price": bottle,
        "currency": item.currency,
        "margin_pct": econ["margin_pct"],
        "beverage_cost_pct": econ["beverage_cost_pct"],
        "rule_bottle_price": quote["bottle_price"],
        "rule_glass_price": quote["glass_price"],
        "line_cost": cost,
        "band": band,
    }


def list_lists(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        rows = session.scalars(
            select(BeverageList)
            .where(BeverageList.venue_id == venue_id)
            .order_by(BeverageList.created_at.desc(), BeverageList.id.desc())
        ).all()
        return {"lists": [_summary(session, row) for row in rows]}


def get_list(venue_id: uuid.UUID, list_id: uuid.UUID) -> dict:
    with session_scope() as session:
        return _detail(session, _owned(session, venue_id, list_id))


def coverage_for(venue_id: uuid.UUID, list_id: uuid.UUID) -> dict:
    with session_scope() as session:
        row = _owned(session, venue_id, list_id)
        body = _coverage(session, row)
        body["list_id"] = row.id
        return body


def health_for(venue_id: uuid.UUID, list_id: uuid.UUID) -> dict:
    with session_scope() as session:
        row = _owned(session, venue_id, list_id)
        return list_health(session, row)


def pricing_rules(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        _venue(session, venue_id)
        stored = session.scalars(
            select(PricingRule)
            .where(PricingRule.venue_id == venue_id)
            .order_by(PricingRule.category, PricingRule.cost_min_cents, PricingRule.id)
        ).all()
        if stored:
            rules = [
                public_rule(
                    {
                        "id": row.id,
                        "category": row.category,
                        "cost_min_cents": row.cost_min_cents,
                        "cost_max_cents": row.cost_max_cents,
                        "bottle_multiple": row.bottle_multiple,
                        "glass_pours_per_bottle": row.glass_pours_per_bottle,
                        "glass_multiple": row.glass_multiple,
                        "round_to_cents": row.round_to_cents,
                    }
                )
                for row in stored
            ]
            return {"source": "stored", "rules": rules}
        return {"source": "default", "rules": [public_rule(rule) for rule in default_rules()]}


def save_pricing_rules(venue_id: uuid.UUID, raw: list[dict]) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        before = [
            public_rule(
                {
                    "id": row.id,
                    "category": row.category,
                    "cost_min_cents": row.cost_min_cents,
                    "cost_max_cents": row.cost_max_cents,
                    "bottle_multiple": row.bottle_multiple,
                    "glass_pours_per_bottle": row.glass_pours_per_bottle,
                    "glass_multiple": row.glass_multiple,
                    "round_to_cents": row.round_to_cents,
                }
            )
            for row in session.scalars(select(PricingRule).where(PricingRule.venue_id == venue_id)).all()
        ]
        saved = replace_rules(session, venue_id, raw)
        after = [public_rule(rule) for rule in saved]
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_RULES,
            entity_type="pricing_rules",
            entity_id=venue_id,
            before={"rules": before},
            after={"rules": after},
        )
        session.commit()
        return {"source": "stored", "rules": after}


def add_item(venue_id: uuid.UUID, list_id: uuid.UUID, sku_id: uuid.UUID, section: str = "") -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        row = _owned(session, venue_id, list_id)
        sku = session.get(Sku, sku_id)
        if sku is None or sku.venue_id != venue_id or sku.variant.product is None:
            raise NotFound("sku not found")
        if any(item.sku_id == sku.id for item in row.items):
            raise DraftFailed("That bottle is already on the list.", 409)
        rules = load_rules(session, venue_id)
        cost = int(sku.cost or 0)
        if cost <= 0:
            raise DraftFailed("That bottle has no cost.", 422)
        category = normalize_category(sku.variant.product.category)
        _guard_limits(session, row, cost, category)
        label = _label(section, "Section", 200, required=False) or section_name(category)
        group = _ensure_section(session, venue_id, row, label)
        position = 1 + max((int(item.position or 0) for item in row.items), default=0)
        quote = price_for(cost, category, rules)
        item = ListItem(
            venue_id=venue_id,
            list_id=row.id,
            sku_id=sku.id,
            section=group.name,
            section_id=group.id,
            position=position,
            cost=cost,
            pour_price=quote["glass_price"],
            bottle_price=quote["bottle_price"],
            currency=row.currency or DEFAULT_CURRENCY,
            margin_pct=0,
        )
        session.add(item)
        session.flush()
        _reload(session, row)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_ADDED,
            entity_type="list_item",
            entity_id=item.id,
            after={"list_id": str(row.id), "sku_id": str(sku.id), "product_id": str(sku.variant.product_id), "cost": cost},
        )
        payload = _detail(session, row)
        session.commit()
        return payload


def update_item(venue_id: uuid.UUID, list_id: uuid.UUID, item_id: uuid.UUID, patch: dict) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        row = _owned(session, venue_id, list_id)
        item = _owned_item(row, item_id)
        before = {
            "pour_price": int(item.pour_price or 0),
            "bottle_price": int(item.bottle_price or 0),
            "position": int(item.position or 0),
            "section": item.section or "",
        }
        rules = load_rules(session, venue_id)
        if patch.get("reprice"):
            category = normalize_category(item.sku.variant.product.category)
            quote = price_for(int(item.cost or 0), category, rules)
            item.bottle_price = quote["bottle_price"]
            item.pour_price = quote["glass_price"]
        if patch.get("bottle_price") is not None:
            item.bottle_price = _money(patch["bottle_price"], "Bottle price")
        if patch.get("pour_price") is not None:
            item.pour_price = _money(patch["pour_price"], "Glass price")
        if patch.get("section") is not None:
            label = _label(str(patch["section"]), "Section", 200) or section_name(
                normalize_category(item.sku.variant.product.category)
            )
            group = _ensure_section(session, venue_id, row, label)
            item.section = group.name
            item.section_id = group.id
        if patch.get("position") is not None:
            _place(row, item, int(patch["position"]))
        item.margin_pct = 0
        session.flush()
        _reload(session, row)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_UPDATED,
            entity_type="list_item",
            entity_id=item.id,
            before=before,
            after={
                "pour_price": int(item.pour_price or 0),
                "bottle_price": int(item.bottle_price or 0),
                "position": int(item.position or 0),
                "section": item.section or "",
                "reprice": bool(patch.get("reprice")),
            },
        )
        payload = _detail(session, row)
        session.commit()
        return payload


def remove_item(venue_id: uuid.UUID, list_id: uuid.UUID, item_id: uuid.UUID) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        row = _owned(session, venue_id, list_id)
        item = _owned_item(row, item_id)
        before = {"sku_id": str(item.sku_id), "product_id": str(item.sku.variant.product_id), "section": item.section or ""}
        session.delete(item)
        session.flush()
        _reload(session, row)
        _renumber(row)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_REMOVED,
            entity_type="list_item",
            entity_id=item_id,
            before=before,
            after={"list_id": str(row.id)},
        )
        payload = _detail(session, row)
        session.commit()
        return payload


def save_sections(venue_id: uuid.UUID, list_id: uuid.UUID, raw: list[dict]) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        row = _owned(session, venue_id, list_id)
        before = [
            {
                "name": section.name,
                "position": int(section.position or 0),
                "budget_share_pct": None if section.budget_share_pct is None else float(section.budget_share_pct),
            }
            for section in row.sections
        ]
        cleaned = _clean_sections(raw)
        by_name = {section.name: section for section in row.sections}
        seen = set()
        for entry in cleaned:
            current = by_name.get(entry["name"])
            share = entry["budget_share_pct"]
            stored = None if share is None else Decimal(str(share))
            if current is None:
                current = ListSection(
                    venue_id=venue_id,
                    list_id=row.id,
                    name=entry["name"],
                    position=entry["position"],
                    budget_share_pct=stored,
                )
                current.beverage_list = row
                session.add(current)
                by_name[entry["name"]] = current
            else:
                current.position = entry["position"]
                current.budget_share_pct = stored
            seen.add(entry["name"])
        for section in list(row.sections):
            if section.name in seen:
                continue
            if any(item.section == section.name or item.section_id == section.id for item in row.items):
                raise DraftFailed(f"Move the bottles out of {section.name} before removing that section.", 409)
            session.delete(section)
        session.flush()
        _reload(session, row)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_SECTIONS,
            entity_type="beverage_list",
            entity_id=row.id,
            before={"sections": before},
            after={"sections": cleaned},
        )
        payload = _detail(session, row)
        session.commit()
        return payload


def _summary(session: Session, row: BeverageList) -> dict:
    body = _detail(session, row)
    return body


def _detail(session: Session, row: BeverageList) -> dict:
    rules = load_rules(session, row.venue_id)
    items = _ordered_items(row)
    views = [item_view(item, rules) for item in items]
    sections = [_section_view(section, items) for section in _ordered_sections(row)]
    coverage = _coverage(session, row)
    health = list_health(session, row)
    spent = sum(int(item.cost or 0) for item in items)
    budget = int(row.budget or 0)
    chosen = {item.sku_id for item in items}
    candidates = [
        _candidate_public(pick) for pick in _candidates(session, row.venue_id, rules) if pick.sku_id not in chosen
    ]
    rollup: dict[str, dict] = {}
    for view in views:
        bucket = rollup.setdefault(
            normalize_category(view["category"]),
            {"count": 0, "regions": set(), "styles": set(), "spend": 0},
        )
        bucket["count"] += 1
        if view["region"]:
            bucket["regions"].add(view["region"])
        if view["style"]:
            bucket["styles"].add(view["style"])
        bucket["spend"] += int(view["cost"])
    coverage_out = {
        key: {
            "count": value["count"],
            "regions": sorted(value["regions"]),
            "styles": sorted(value["styles"]),
            "spend": value["spend"],
        }
        for key, value in rollup.items()
    }
    gaps = [cell["name"] for cell in coverage["suggestions"]] or ["none — categories covered"]
    pct = row.target_beverage_cost_pct
    return {
        "id": row.id,
        "list_id": row.id,
        "name": row.name,
        "budget": budget,
        "spent": spent,
        "remaining": budget - spent,
        "currency": row.currency,
        "target_margin": row.target_margin,
        "target_beverage_cost_pct": None if pct is None else float(pct),
        "concept": row.concept or "",
        "price_tier": row.price_tier or "",
        "notes": row.notes or "",
        "source_filename": row.source_filename or "",
        "item_count": len(views),
        "items": views,
        "sections": sections,
        "coverage": coverage_out,
        "cells": coverage["cells"],
        "suggestions": coverage["suggestions"],
        "gaps": gaps,
        "health": health,
        "candidates": candidates,
        "bottles": len(views),
        "capacity_bottles": _capacity(session, row.venue_id),
    }


def _coverage(session: Session, row: BeverageList) -> dict:
    rules = load_rules(session, row.venue_id)
    notes = _approved(session, row.venue_id)
    cells = matrix(session, row.venue_id)
    picks = []
    for item in _ordered_items(row):
        built = _pick_from_item(item, rules, notes.get(item.sku.variant.product_id))
        if built is not None:
            picks.append((item, built))
    shown = []
    suggestions = []
    filled = 0
    for cell in cells:
        match = next((item for item, pick in picks if covers(pick, cell)), None)
        if match is None:
            suggestion = {
                "category": cell.category,
                "style": cell.style,
                "band": cell.band,
                "status": "suggestion",
                "product_id": None,
                "sku_id": None,
                "name": f"Buy {cell.style}",
                "dish_id": None if cell.dish_id is None else cell.dish_id,
                "dish_name": cell.dish_name,
            }
            suggestions.append(suggestion)
            shown.append(suggestion)
            continue
        filled += 1
        product = match.sku.variant.product
        shown.append(
            {
                "category": cell.category,
                "style": cell.style,
                "band": cell.band,
                "status": "filled",
                "product_id": product.id,
                "sku_id": match.sku_id,
                "name": product.name,
                "dish_id": None if cell.dish_id is None else cell.dish_id,
                "dish_name": cell.dish_name,
            }
        )
    return {"filled": filled, "open": len(suggestions), "cells": shown, "suggestions": suggestions}


def _section_view(section: ListSection, items: list[ListItem]) -> dict:
    rows = [item for item in items if item.section_id == section.id or item.section == section.name]
    costs = [int(item.cost or 0) for item in rows]
    prices = [int(item.bottle_price or 0) or int(item.pour_price or 0) for item in rows]
    mix = blended(costs, prices)
    share = section.budget_share_pct
    return {
        "id": section.id,
        "name": section.name,
        "position": int(section.position or 0),
        "budget_share_pct": None if share is None else float(share),
        "spend": sum(costs),
        "item_count": len(rows),
        "margin_pct": mix["margin_pct"],
        "beverage_cost_pct": mix["beverage_cost_pct"],
    }


def _candidate_public(pick: Pick) -> dict:
    return {
        "sku_id": pick.sku_id,
        "product_id": pick.product_id,
        "name": pick.name,
        "category": pick.category,
        "style": pick.style,
        "band": pick.band,
        "cost": pick.cost,
    }


def _candidates(session: Session, venue_id: uuid.UUID, rules: list[dict]) -> list[Pick]:
    from madira.domain.procurement.offers import candidate_offer_costs

    stock = _on_hand(session, venue_id)
    notes = _approved(session, venue_id)
    offer_costs = candidate_offer_costs(session, venue_id)
    found = []
    rows = session.scalars(select(Sku).where(Sku.venue_id == venue_id).order_by(Sku.id)).all()
    for sku in rows:
        product = sku.variant.product if sku.variant is not None else None
        if product is None:
            continue
        stock_cost = int(sku.cost or 0)
        offer_cost = offer_costs.get(sku.id)
        if offer_cost is not None and offer_cost > 0:
            cost = offer_cost
        else:
            cost = stock_cost
            if cost <= 0:
                continue
            if sku.id in stock and stock[sku.id] <= 0:
                continue
        if cost <= 0:
            continue
        category = normalize_category(product.category)
        profile = derive_profile(product, notes.get(product.id))
        quote = price_for(cost, category, rules)
        band = _tier(quote["bottle_price"], quote["glass_price"]) or "value"
        found.append(
            Pick(
                sku_id=sku.id,
                product_id=product.id,
                category=category,
                style=profile.label,
                band=band,
                name=product.name,
                cost=cost,
            )
        )
    return found


def _pick_from_item(item: ListItem, rules: list[dict], note=None) -> Pick | None:
    product = item.sku.variant.product
    if product is None:
        return None
    category = normalize_category(product.category)
    profile = derive_profile(product, note)
    quote = price_for(int(item.cost or 0), category, rules)
    bottle = int(item.bottle_price or 0) or quote["bottle_price"]
    glass = int(item.pour_price or 0) or quote["glass_price"]
    return Pick(
        sku_id=item.sku_id,
        product_id=product.id,
        category=category,
        style=profile.label,
        band=_tier(bottle, glass) or "value",
        name=product.name,
        cost=int(item.cost or 0),
    )


def _section_names(selected: list[Pick], open_cells: list[Cell]) -> list[str]:
    present = {pick.category for pick in selected} | {cell.category for cell in open_cells}
    return [section_name(category) for category in _SECTION_ORDER if category in present]


def _create_sections(session: Session, venue_id: uuid.UUID, row: BeverageList, names: list[str]) -> dict[str, ListSection]:
    created = {}
    for index, name in enumerate(names):
        category = normalize_category(name)
        share = SECTION_SHARES.get(category)
        section = ListSection(
            venue_id=venue_id,
            list_id=row.id,
            name=name,
            position=index,
            budget_share_pct=None if share is None else Decimal(share),
        )
        section.beverage_list = row
        session.add(section)
        created[name] = section
    session.flush()
    return created


def _ensure_section(session: Session, venue_id: uuid.UUID, row: BeverageList, name: str) -> ListSection:
    current = next((section for section in row.sections if section.name == name), None)
    if current is not None:
        return current
    position = 1 + max((int(section.position or 0) for section in row.sections), default=-1)
    category = normalize_category(name)
    share = SECTION_SHARES.get(category)
    section = ListSection(
        venue_id=venue_id,
        list_id=row.id,
        name=name,
        position=position,
        budget_share_pct=None if share is None else Decimal(share),
    )
    section.beverage_list = row
    session.add(section)
    session.flush()
    return section


def _guard_limits(session: Session, row: BeverageList, cost: int, category: str) -> None:
    items = list(row.items)
    budget = int(row.budget or 0)
    spent = sum(int(item.cost or 0) for item in items)
    if budget > 0 and spent + cost > budget:
        raise DraftFailed("That bottle would exceed the list budget.", 409)
    capacity = _capacity(session, row.venue_id)
    if capacity is not None and len(items) + 1 > capacity:
        raise DraftFailed("That bottle would exceed storage capacity.", 409)
    share = SECTION_SHARES.get(category)
    section = next((item for item in row.sections if normalize_category(item.name) == category), None)
    if section is not None and section.budget_share_pct is not None:
        share = int(section.budget_share_pct)
    if share is not None and budget > 0:
        allocated = budget * int(share) // 100
        section_spend = sum(int(item.cost or 0) for item in items if normalize_category(item.section) == category)
        if section_spend + cost > allocated:
            raise DraftFailed("That bottle would exceed the section budget.", 409)


def _place(row: BeverageList, item: ListItem, position: int) -> None:
    if position < 0:
        raise DraftFailed("Position cannot be negative.", 422)
    item.position = position
    _renumber(row, prefer=item.id)


def _renumber(row: BeverageList, prefer: uuid.UUID | None = None) -> None:
    items = list(row.items)
    items.sort(key=lambda current: (int(current.position or 0), 0 if current.id == prefer else 1, str(current.id)))
    for index, current in enumerate(items, start=1):
        current.position = index


def _clean_sections(raw: list[dict]) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise DraftFailed("Add at least one section.", 422)
    cleaned = []
    seen = set()
    total = Decimal(0)
    for row in raw:
        name = _label(str(row.get("name") or ""), "Section", 200)
        if not name:
            raise DraftFailed("A section needs a name.", 422)
        key = name.casefold()
        if key in seen:
            raise DraftFailed("Section names must be unique.", 422)
        seen.add(key)
        try:
            position = int(row.get("position") or 0)
        except (TypeError, ValueError) as exc:
            raise DraftFailed("Section position must be a number.", 422) from exc
        if position < 0:
            raise DraftFailed("Section position cannot be negative.", 422)
        share_raw = row.get("budget_share_pct")
        share = None
        if share_raw is not None and share_raw != "":
            try:
                share = Decimal(str(share_raw)).quantize(_TENTH, rounding=ROUND_HALF_UP)
            except (ArithmeticError, ValueError) as exc:
                raise DraftFailed("Budget share must be a number.", 422) from exc
            if share < 0 or share > 100:
                raise DraftFailed("Budget share must be between 0 and 100.", 422)
            total += share
        cleaned.append({"name": name, "position": position, "budget_share_pct": None if share is None else float(share)})
    if total > 100:
        raise DraftFailed("Section budget shares cannot add up to more than 100.", 422)
    cleaned.sort(key=lambda row: (row["position"], row["name"]))
    return cleaned


def _ordered_items(row: BeverageList) -> list[ListItem]:
    items = list(row.items)
    items.sort(key=lambda item: (int(item.position or 0), str(item.id)))
    return items


def _ordered_sections(row: BeverageList) -> list[ListSection]:
    sections = list(row.sections)
    sections.sort(key=lambda section: (int(section.position or 0), section.name, str(section.id)))
    return sections


def _owned(session: Session, venue_id: uuid.UUID, list_id: uuid.UUID) -> BeverageList:
    row = session.get(BeverageList, list_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("list not found")
    return row


def _owned_item(row: BeverageList, item_id: uuid.UUID) -> ListItem:
    item = next((current for current in row.items if current.id == item_id), None)
    if item is None or item.venue_id != row.venue_id:
        raise NotFound("list item not found")
    return item


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _capacity(session: Session, venue_id: uuid.UUID) -> int | None:
    zones = session.scalars(select(StorageZone).where(StorageZone.venue_id == venue_id)).all()
    values = [int(zone.capacity_bottles) for zone in zones if zone.capacity_bottles is not None]
    if not values:
        return None
    return sum(values)


def _on_hand(session: Session, venue_id: uuid.UUID) -> dict[uuid.UUID, int]:
    found: dict[uuid.UUID, int] = {}
    rows = session.scalars(select(InventoryItem).where(InventoryItem.venue_id == venue_id)).all()
    for row in rows:
        found[row.sku_id] = found.get(row.sku_id, 0) + int(row.on_hand or 0)
    return found


def _approved(session: Session, venue_id: uuid.UUID) -> dict:
    rows = session.scalars(
        select(TastingNote)
        .where(TastingNote.venue_id == venue_id, TastingNote.status == "approved")
        .order_by(TastingNote.approved_at.desc(), TastingNote.id.desc())
    ).all()
    found = {}
    for row in rows:
        found.setdefault(row.product_id, row)
    return found


def _label(value: str, label: str, limit: int, *, required: bool = True) -> str:
    text = clean(value)
    if not text:
        if required:
            raise DraftFailed(f"{label} is required.", 422)
        return ""
    if len(text) > limit:
        raise DraftFailed(f"{label} is too long.", 422)
    return text


def _money(value, label: str) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError) as exc:
        raise DraftFailed(f"{label} must be a whole number of cents.", 422) from exc
    if amount < 0:
        raise DraftFailed(f"{label} cannot be negative.", 422)
    return amount


def _reload(session: Session, row: BeverageList) -> None:
    session.expire(row, ["items", "sections"])


def _cost_pct(given: float | None, target_margin: float) -> Decimal:
    if given is None:
        multiple = Decimal(str(target_margin or 0))
        if multiple <= 0:
            raise DraftFailed("Target margin must be greater than zero.", 422)
        pct = (Decimal(100) / multiple).quantize(_TENTH, rounding=ROUND_HALF_UP)
    else:
        try:
            pct = Decimal(str(given)).quantize(_TENTH, rounding=ROUND_HALF_UP)
        except (ArithmeticError, ValueError) as exc:
            raise DraftFailed("Target beverage cost must be a number.", 422) from exc
    if pct < 0 or pct > 100:
        raise DraftFailed("Target beverage cost must be between 0 and 100.", 422)
    return pct
