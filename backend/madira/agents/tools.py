"""Domain tools used by specialist subagents. Each returns JSON; A2UI is attached via tracker."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from madira import a2ui_ops
from madira.agents import tracker
from madira.agents.presenters.inventory import with_inventory
from madira.agents.presenters.lists import with_list
from madira.agents.presenters.menu import with_dishes, with_pairings
from madira.agents.presenters.purchasing import with_orders
from madira.db import SessionLocal
from madira.domain.errors import NotFound
from madira.domain.inventory import service as inventory_service
from madira.domain.lists import service as lists_service
from madira.domain.menu import service as menu_service
from madira.domain.purchasing import service as purchasing_service
from madira.fixtures_data import ROLEPLAY_OPENER, build_ics
from madira.models import Lesson, Quiz, QuizAttempt, Supplier, Tasting
from madira.tenancy import active_venue_id
from madira.timestamps import format_wall, parse_stamp


def _session():
    return SessionLocal()


def _dumps(payload: dict) -> str:
    return json.dumps(payload, default=str)


def _vid() -> uuid.UUID:
    return active_venue_id()


def parse_menu(text: str, source_name: str = "pasted") -> str:
    """Parse a restaurant menu into dishes, flavor profiles, cuisine, and price tier. Persist the menu."""
    body = with_dishes(menu_service.parse_menu(_vid(), text, source_name))
    tracker.record_operations(body["a2ui_operations"])
    tracker.complete_delegation("menu-analyst")
    return _dumps(body)


def recommend_pairings(menu_id: str = "") -> str:
    """Recommend wine, beer, spirit, and sake pairings for each dish on a menu, with rationale and price-tier fit."""
    payload = menu_service.recommend_pairings(_vid(), menu_id)
    if "error" in payload:
        return _dumps({"error": payload["error"]})
    created = payload.get("created_menu")
    if created:
        tracker.record_operations(with_dishes(created)["a2ui_operations"])
        tracker.complete_delegation("menu-analyst")
    body = with_pairings(payload)
    tracker.record_operations(body["a2ui_operations"])
    tracker.complete_delegation("pairing-sommelier")
    return _dumps(body)


def curate_beverage_list(budget: float = 12000, target_margin: float = 3.2, name: str = "Maison Madira autumn list") -> str:
    """Build a balanced wine/beer/spirit/sake list within a buying budget and target pour/bottle margin. Show coverage and gaps."""
    body = with_list(lists_service.curate(_vid(), budget=budget, target_margin=target_margin, name=name))
    tracker.record_operations(body["a2ui_operations"])
    tracker.complete_delegation("list-curator")
    return _dumps(body)


def get_inventory() -> str:
    """Return current stock, par levels, 30-day depletion, and low-stock alerts."""
    body = with_inventory(inventory_service.snapshot(_vid()))
    tracker.record_operations(body["a2ui_operations"])
    tracker.complete_delegation("inventory-purchasing")
    return _dumps(body)


def update_stock(sku: str, on_hand: int) -> str:
    """Set on-hand quantity for an inventory SKU (for example W-MUS-01)."""
    try:
        inventory_service.set_on_hand(_vid(), sku, on_hand)
    except NotFound as exc:
        return _dumps({"error": exc.message})
    return get_inventory()


def draft_purchase_orders() -> str:
    """Draft reorder purchase orders grouped by supplier for every SKU below par."""
    body = with_orders(purchasing_service.draft(_vid()))
    tracker.record_operations(body["a2ui_operations"])
    tracker.complete_delegation("inventory-purchasing")
    return _dumps(body)


def get_training_briefing() -> str:
    """Daily menu pairing briefing and wine/service lessons for waitstaff and bartenders."""
    session = _session()
    vid = _vid()
    try:
        lessons = [
            {"id": lesson.id, "slug": lesson.slug, "title": lesson.title, "role": lesson.role, "category": lesson.category, "body": lesson.body}
            for lesson in session.scalars(select(Lesson).where(Lesson.venue_id == vid)).all()
        ]
        quiz = session.scalar(select(Quiz).where(Quiz.venue_id == vid).limit(1))
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
    vid = _vid()
    try:
        quiz = session.scalar(select(Quiz).where(Quiz.venue_id == vid).limit(1))
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
        attempt = QuizAttempt(venue_id=vid, quiz_id=quiz.id, staff_name=staff_name, answers=parsed, score=score)
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
    vid = _vid()
    try:
        rows = session.scalars(select(Tasting).where(Tasting.venue_id == vid).order_by(Tasting.starts_at)).all()
        tastings = [
            {
                "id": t.id,
                "title": t.title,
                "starts_at": format_wall(t.starts_at),
                "ends_at": format_wall(t.ends_at),
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
    vid = _vid()
    try:
        supplier = session.scalar(select(Supplier).where(Supplier.venue_id == vid, Supplier.name == supplier_name))
        if supplier is None:
            supplier = session.scalar(select(Supplier).where(Supplier.venue_id == vid).limit(1))
        if supplier is None:
            return _dumps({"error": "no supplier"})
        if not starts_at:
            start = datetime.now().replace(hour=15, minute=0, second=0, microsecond=0) + timedelta(days=7)
            starts_at = start.strftime("%Y-%m-%dT%H:%M")
            ends_at = (start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        if not ends_at:
            ends_at = starts_at
        ics = build_ics(title, starts_at, ends_at, location, notes)
        start_at = parse_stamp(starts_at)
        end_at = parse_stamp(ends_at)
        tasting = session.scalar(
            select(Tasting).where(
                Tasting.venue_id == vid,
                Tasting.title == title,
                Tasting.supplier_id == supplier.id,
            )
        )
        if tasting is None:
            tasting = Tasting(
                venue_id=vid,
                supplier_id=supplier.id,
                title=title,
                starts_at=start_at,
                ends_at=end_at,
                location=location,
                notes=notes,
                ics=ics,
            )
            session.add(tasting)
        else:
            tasting.starts_at = start_at
            tasting.ends_at = end_at
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
        rows = session.scalars(select(Tasting).where(Tasting.venue_id == vid).order_by(Tasting.starts_at)).all()
        tastings = [
            {
                "id": t.id,
                "title": t.title,
                "starts_at": format_wall(t.starts_at),
                "ends_at": format_wall(t.ends_at),
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
