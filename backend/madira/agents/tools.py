"""Domain tools used by specialist subagents. Each returns JSON; A2UI is attached via tracker."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from madira import a2ui_ops
from madira.agents import tracker
from madira.db import SessionLocal
from madira.fixtures_data import (
    QUIZ,
    ROLEPLAY_OPENER,
    build_ics,
    curate_list as curate_list_fixture,
    pairings_for_dishes,
    parse_menu_text,
)
from madira.models import (
    BeverageList,
    Dish,
    InventoryItem,
    Lesson,
    ListItem,
    Menu,
    POLine,
    Pairing,
    PurchaseOrder,
    Quiz,
    QuizAttempt,
    Supplier,
    Tasting,
)


def _session():
    return SessionLocal()


def _dumps(payload: dict) -> str:
    return json.dumps(payload, default=str)


def parse_menu(text: str, source_name: str = "pasted") -> str:
    """Parse a restaurant menu into dishes, flavor profiles, cuisine, and price tier. Persist the menu."""
    parsed = parse_menu_text(text, source_name=source_name)
    session = _session()
    try:
        menu = Menu(
            name=parsed["name"],
            source_type=parsed["source_type"],
            raw_text=parsed["raw_text"],
            cuisine=parsed["cuisine"],
            price_tier=parsed["price_tier"],
        )
        session.add(menu)
        session.flush()
        dishes_out = []
        for row in parsed["dishes"]:
            dish = Dish(menu_id=menu.id, **row)
            session.add(dish)
            session.flush()
            dishes_out.append(
                {
                    "id": dish.id,
                    "name": dish.name,
                    "course": dish.course,
                    "description": dish.description,
                    "flavor_profile": dish.flavor_profile,
                    "price": dish.price,
                }
            )
        session.commit()
        ops = a2ui_ops.dishes_surface(
            f"Parsed · {menu.name}",
            dishes_out,
            menu.cuisine,
            menu.price_tier,
        )
        tracker.record_operations(ops)
        tracker.complete_delegation("menu-analyst")
        return _dumps(
            {
                "menu_id": menu.id,
                "name": menu.name,
                "cuisine": menu.cuisine,
                "price_tier": menu.price_tier,
                "dishes": dishes_out,
                "a2ui_operations": ops,
            }
        )
    finally:
        session.close()


def recommend_pairings(menu_id: int = 0) -> str:
    """Recommend wine, beer, spirit, and sake pairings for each dish on a menu, with rationale and price-tier fit."""
    session = _session()
    try:
        menu = session.get(Menu, menu_id) if menu_id else session.scalar(select(Menu).order_by(Menu.id.desc()))
        if menu is None:
            parse_menu("", "demo")
            session.expire_all()
            menu = session.scalar(select(Menu).order_by(Menu.id.desc()))
        dishes = list(menu.dishes)
        dish_payload = [
            {"name": d.name, "flavor_profile": d.flavor_profile, "price": d.price, "course": d.course}
            for d in dishes
        ]
        planned = pairings_for_dishes(dish_payload)
        for dish, block in zip(dishes, planned):
            session.execute(delete(Pairing).where(Pairing.dish_id == dish.id))
            for p in block["pairings"]:
                session.add(Pairing(dish_id=dish.id, **p))
        session.commit()
        cards = []
        for dish, block in zip(dishes, planned):
            cards.append(
                {
                    "dish": dish.name,
                    "course": dish.course,
                    "flavor_profile": dish.flavor_profile,
                    "price": dish.price,
                    "pairings": block["pairings"],
                }
            )
        ops = a2ui_ops.pairings_surface(f"Pairings · {menu.name}", cards)
        tracker.record_operations(ops)
        tracker.complete_delegation("pairing-sommelier")
        return _dumps({"menu_id": menu.id, "dishes": cards, "a2ui_operations": ops})
    finally:
        session.close()


def curate_beverage_list(budget: float = 12000, target_margin: float = 3.2, name: str = "Maison Madira autumn list") -> str:
    """Build a balanced wine/beer/spirit/sake list within a buying budget and target pour/bottle margin. Show coverage and gaps."""
    payload = curate_list_fixture(budget=budget, target_margin=target_margin)
    payload["name"] = name
    session = _session()
    try:
        bl = BeverageList(name=name, budget=budget, target_margin=target_margin, notes=payload["notes"])
        session.add(bl)
        session.flush()
        for item in payload["items"]:
            session.add(
                ListItem(
                    list_id=bl.id,
                    category=item["category"],
                    name=item["name"],
                    producer=item["producer"],
                    region=item["region"],
                    style=item["style"],
                    vintage=item["vintage"],
                    cost=item["cost"],
                    pour_price=item["pour_price"],
                    bottle_price=item["bottle_price"],
                    margin_pct=item["margin_pct"],
                )
            )
        session.commit()
        payload["list_id"] = bl.id
        ops = a2ui_ops.list_surface(payload)
        tracker.record_operations(ops)
        tracker.complete_delegation("list-curator")
        payload["a2ui_operations"] = ops
        return _dumps(payload)
    finally:
        session.close()


def _inventory_rows(session) -> list[dict]:
    rows = session.scalars(select(InventoryItem).order_by(InventoryItem.sku)).all()
    out = []
    for item in rows:
        supplier = item.supplier.name if item.supplier else ""
        low = item.on_hand < item.par
        out.append(
            {
                "id": item.id,
                "sku": item.sku,
                "name": item.name,
                "category": item.category,
                "supplier": supplier,
                "supplier_id": item.supplier_id,
                "on_hand": item.on_hand,
                "par": item.par,
                "unit_cost": item.unit_cost,
                "depletion_30d": item.depletion_30d,
                "unit": item.unit,
                "low": low,
                "reorder_qty": max(item.par - item.on_hand, 0),
            }
        )
    return out


def get_inventory() -> str:
    """Return current stock, par levels, 30-day depletion, and low-stock alerts."""
    session = _session()
    try:
        items = _inventory_rows(session)
        alerts = [
            {
                "sku": i["sku"],
                "name": i["name"],
                "on_hand": i["on_hand"],
                "par": i["par"],
                "message": f"{i['name']} is at {i['on_hand']} {i['unit']} (par {i['par']})",
            }
            for i in items
            if i["low"]
        ]
        ops = a2ui_ops.inventory_surface("Cellar inventory", items, alerts)
        tracker.record_operations(ops)
        tracker.complete_delegation("inventory-purchasing")
        return _dumps({"items": items, "alerts": alerts, "a2ui_operations": ops})
    finally:
        session.close()


def update_stock(sku: str, on_hand: int) -> str:
    """Set on-hand quantity for an inventory SKU (for example W-MUS-01)."""
    session = _session()
    try:
        item = session.scalar(select(InventoryItem).where(InventoryItem.sku == sku.strip().upper()))
        if item is None:
            return _dumps({"error": f"unknown sku {sku}"})
        item.on_hand = int(on_hand)
        session.commit()
        return get_inventory()
    finally:
        session.close()


def draft_purchase_orders() -> str:
    """Draft reorder purchase orders grouped by supplier for every SKU below par."""
    session = _session()
    try:
        items = _inventory_rows(session)
        lows = [i for i in items if i["low"] and i["reorder_qty"] > 0]
        grouped: dict[int, list[dict]] = {}
        for i in lows:
            grouped.setdefault(i["supplier_id"], []).append(i)
        orders = []
        for supplier_id, lines in grouped.items():
            supplier = session.get(Supplier, supplier_id)
            po = PurchaseOrder(
                supplier_id=supplier_id,
                status="draft",
                notes="Draft only — not transmitted to the supplier.",
            )
            session.add(po)
            session.flush()
            po_lines = []
            total = 0.0
            for line in lines:
                qty = line["reorder_qty"]
                session.add(
                    POLine(
                        po_id=po.id,
                        sku=line["sku"],
                        name=line["name"],
                        qty=qty,
                        unit_cost=line["unit_cost"],
                    )
                )
                po_lines.append({**line, "qty": qty, "line_cost": round(qty * line["unit_cost"], 2)})
                total += qty * line["unit_cost"]
            orders.append(
                {
                    "id": po.id,
                    "status": "draft",
                    "supplier": supplier.name if supplier else "",
                    "total": round(total, 2),
                    "lines": po_lines,
                    "notes": po.notes,
                }
            )
        session.commit()
        ops = a2ui_ops.po_surface("Draft purchase orders", orders)
        tracker.record_operations(ops)
        tracker.complete_delegation("inventory-purchasing")
        return _dumps({"orders": orders, "a2ui_operations": ops})
    finally:
        session.close()


def get_training_briefing() -> str:
    """Daily menu pairing briefing and wine/service lessons for waitstaff and bartenders."""
    session = _session()
    try:
        lessons = [
            {"id": lesson.id, "slug": lesson.slug, "title": lesson.title, "role": lesson.role, "category": lesson.category, "body": lesson.body}
            for lesson in session.scalars(select(Lesson)).all()
        ]
        quiz = session.scalar(select(Quiz).limit(1))
        quiz_payload = None
        if quiz:
            quiz_payload = {
                "id": quiz.id,
                "title": quiz.title,
                "questions": [
                    {k: v for k, v in q.items() if k != "answer"}
                    for q in quiz.questions
                ],
            }
        ops = a2ui_ops.briefing_surface("Staff briefing", lessons)
        if quiz_payload:
            ops.extend(a2ui_ops.quiz_surface(quiz_payload["title"], quiz_payload))
        tracker.record_operations(ops)
        tracker.complete_delegation("staff-trainer")
        return _dumps({"lessons": lessons, "quiz": quiz_payload, "roleplay": ROLEPLAY_OPENER, "a2ui_operations": ops})
    finally:
        session.close()


def grade_quiz(answers: str, staff_name: str = "Floor") -> str:
    """Grade a training quiz. `answers` is a comma-separated list of choice indexes (0-based), e.g. '1,2,2,1'."""
    session = _session()
    try:
        quiz = session.scalar(select(Quiz).limit(1))
        if quiz is None:
            return _dumps({"error": "no quiz seeded"})
        parsed = [int(x.strip()) for x in re.split(r"[,\s]+", answers.strip()) if x.strip() != ""]
        correct = 0
        review = []
        for idx, question in enumerate(quiz.questions):
            choice = parsed[idx] if idx < len(parsed) else -1
            ok = choice == question["answer"]
            correct += int(ok)
            review.append(
                {
                    "id": question["id"],
                    "prompt": question["prompt"],
                    "selected": choice,
                    "correct": question["answer"],
                    "ok": ok,
                    "explain": question["explain"],
                }
            )
        score = round(100 * correct / max(len(quiz.questions), 1), 1)
        attempt = QuizAttempt(quiz_id=quiz.id, staff_name=staff_name, answers=parsed, score=score)
        session.add(attempt)
        session.commit()
        payload = {
            "id": quiz.id,
            "title": quiz.title,
            "questions": [{k: v for k, v in q.items() if k != "answer"} for q in quiz.questions],
            "score": score,
            "correct": correct,
            "total": len(quiz.questions),
            "review": review,
            "staff_name": staff_name,
        }
        quiz_view = dict(payload)
        ops = a2ui_ops.quiz_surface(f"Quiz result · {score}%", quiz_view)
        tracker.record_operations(ops)
        tracker.complete_delegation("staff-trainer")
        payload["a2ui_operations"] = ops
        return _dumps(payload)
    finally:
        session.close()


def start_roleplay() -> str:
    """Start diner roleplay: the agent plays a skeptical guest at Maison Madira."""
    payload = {
        "mode": "roleplay",
        "persona": "Skeptical diner, ordered the dry-aged ribeye",
        "opener": ROLEPLAY_OPENER,
        "first_line": "Hi — I ordered the ribeye. I don't really do wine lists. What are you going to try to sell me?",
    }
    tracker.complete_delegation("staff-trainer")
    return _dumps(payload)


def list_tastings() -> str:
    """List scheduled supplier tastings (drafts only; nothing is sent)."""
    session = _session()
    try:
        rows = session.scalars(select(Tasting).order_by(Tasting.starts_at)).all()
        tastings = [
            {
                "id": t.id,
                "title": t.title,
                "starts_at": t.starts_at,
                "ends_at": t.ends_at,
                "location": t.location,
                "notes": t.notes,
                "supplier": t.supplier.name if t.supplier else "",
                "ics": t.ics,
            }
            for t in rows
        ]
        ops = a2ui_ops.tasting_surface("Supplier calendar", {}, tastings)
        tracker.record_operations(ops)
        tracker.complete_delegation("supplier-scheduler")
        return _dumps({"tastings": tastings, "a2ui_operations": ops})
    finally:
        session.close()


def schedule_tasting(
    supplier_name: str = "Kermit Lynch Wine Merchant",
    title: str = "New Loire releases tasting",
    starts_at: str = "",
    ends_at: str = "",
    location: str = "Maison Madira cellar",
    notes: str = "Draft hold — export .ics, do not send invites.",
) -> str:
    """Schedule a tasting with an importer or distributor. Produces a draft .ics only — never sends email or calendar invites."""
    session = _session()
    try:
        supplier = session.scalar(select(Supplier).where(Supplier.name == supplier_name))
        if supplier is None:
            supplier = session.scalar(select(Supplier).limit(1))
        if not starts_at:
            start = datetime.now().replace(hour=15, minute=0, second=0, microsecond=0) + timedelta(days=7)
            starts_at = start.strftime("%Y-%m-%dT%H:%M")
            ends_at = (start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        if not ends_at:
            ends_at = starts_at
        ics = build_ics(title, starts_at, ends_at, location, notes)
        tasting = session.scalar(
            select(Tasting).where(Tasting.title == title, Tasting.supplier_id == supplier.id)
        )
        if tasting is None:
            tasting = Tasting(
                supplier_id=supplier.id,
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
                location=location,
                notes=notes,
                ics=ics,
            )
            session.add(tasting)
        else:
            tasting.starts_at = starts_at
            tasting.ends_at = ends_at
            tasting.location = location
            tasting.notes = notes
            tasting.ics = ics
        session.commit()
        draft = {
            "id": tasting.id,
            "title": title,
            "supplier": supplier.name,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "location": location,
            "notes": notes,
            "ics": ics,
            "sent": False,
        }
        rows = session.scalars(select(Tasting).order_by(Tasting.starts_at)).all()
        tastings = [
            {
                "id": t.id,
                "title": t.title,
                "starts_at": t.starts_at,
                "ends_at": t.ends_at,
                "location": t.location,
                "notes": t.notes,
                "supplier": t.supplier.name if t.supplier else "",
            }
            for t in rows
        ]
        ops = a2ui_ops.tasting_surface("Tasting scheduled (draft)", draft, tastings)
        tracker.record_operations(ops)
        tracker.complete_delegation("supplier-scheduler")
        return _dumps({"draft": draft, "tastings": tastings, "a2ui_operations": ops})
    finally:
        session.close()


MENU_ANALYST_TOOLS = [parse_menu]
PAIRING_TOOLS = [recommend_pairings]
LIST_TOOLS = [curate_beverage_list]
INVENTORY_TOOLS = [get_inventory, update_stock, draft_purchase_orders]
TRAINING_TOOLS = [get_training_briefing, grade_quiz, start_roleplay]
SUPPLIER_TOOLS = [list_tastings, schedule_tasting]

ALL_TOOLS = (
    MENU_ANALYST_TOOLS
    + PAIRING_TOOLS
    + LIST_TOOLS
    + INVENTORY_TOOLS
    + TRAINING_TOOLS
    + SUPPLIER_TOOLS
)
