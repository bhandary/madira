"""Domain tools used by specialist subagents. Each returns JSON; A2UI is attached via tracker."""

from __future__ import annotations

import json
import uuid

from madira.agents import tracker
from madira.agents.presenters.inventory import with_inventory
from madira.agents.presenters.lists import with_list
from madira.agents.presenters.menu import with_dishes, with_pairings
from madira.agents.presenters.procurement import with_scheduled, with_tasting_list
from madira.agents.presenters.purchasing import with_orders
from madira.agents.presenters.training import with_briefing, with_quiz
from madira.domain.errors import NotFound
from madira.domain.inventory import service as inventory_service
from madira.domain.lists import service as lists_service
from madira.domain.menu import service as menu_service
from madira.domain.procurement import service as procurement_service
from madira.domain.purchasing import service as purchasing_service
from madira.domain.training import service as training_service
from madira.tenancy import active_venue_id


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
    body = with_briefing(training_service.briefing(_vid()))
    tracker.record_operations(body["a2ui_operations"])
    tracker.complete_delegation("staff-trainer")
    return _dumps(body)


def grade_quiz(answers: str, staff_name: str = "Floor") -> str:
    """Grade a training quiz. `answers` is a comma-separated list of choice indexes (0-based), e.g. '1,2,2,1'."""
    payload = training_service.grade(_vid(), answers, staff_name=staff_name)
    if "error" in payload:
        return _dumps({"error": payload["error"]})
    body = with_quiz(payload)
    tracker.record_operations(body["a2ui_operations"])
    tracker.complete_delegation("staff-trainer")
    return _dumps(body)


def start_roleplay() -> str:
    """Start diner roleplay: the agent plays a skeptical guest at Maison Madira."""
    tracker.complete_delegation("staff-trainer")
    return _dumps(training_service.roleplay())


def list_tastings() -> str:
    """List scheduled supplier tastings (drafts only; nothing is sent)."""
    body = with_tasting_list(procurement_service.list_tastings(_vid()))
    tracker.record_operations(body["a2ui_operations"])
    tracker.complete_delegation("supplier-scheduler")
    return _dumps(body)


def schedule_tasting(
    supplier_name: str = "Kermit Lynch Wine Merchant",
    title: str = "New Loire releases tasting",
    starts_at: str = "",
    ends_at: str = "",
    location: str = "Maison Madira cellar",
    notes: str = "Draft hold — export .ics, do not send invites.",
) -> str:
    """Schedule a tasting with an importer or distributor. Produces a draft .ics only — never sends email or calendar invites."""
    payload = procurement_service.schedule(
        _vid(),
        supplier_name=supplier_name,
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
        location=location,
        notes=notes,
    )
    if "error" in payload:
        return _dumps({"error": payload["error"]})
    body = with_scheduled(payload)
    tracker.record_operations(body["a2ui_operations"])
    tracker.complete_delegation("supplier-scheduler")
    return _dumps(body)


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
