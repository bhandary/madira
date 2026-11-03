"""A2UI v0.9 helpers. Prefer CopilotKit's a2ui module; fall back to local builders."""

from __future__ import annotations

import json
from typing import Any

from madira.config import CATALOG_ID

try:
    from copilotkit import a2ui as _ck_a2ui
except Exception:  # pragma: no cover - optional at import time
    _ck_a2ui = None


def create_surface(surface_id: str, catalog_id: str = CATALOG_ID) -> dict[str, Any]:
    if _ck_a2ui is not None:
        return _ck_a2ui.create_surface(surface_id, catalog_id=catalog_id)
    return {
        "version": "v0.9",
        "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id},
    }


def update_components(surface_id: str, components: list[dict[str, Any]]) -> dict[str, Any]:
    if _ck_a2ui is not None:
        return _ck_a2ui.update_components(surface_id, components)
    return {
        "version": "v0.9",
        "updateComponents": {"surfaceId": surface_id, "components": components},
    }


def update_data_model(surface_id: str, data: Any, path: str = "/") -> dict[str, Any]:
    if _ck_a2ui is not None:
        return _ck_a2ui.update_data_model(surface_id, data, path=path)
    return {
        "version": "v0.9",
        "updateDataModel": {"surfaceId": surface_id, "path": path, "value": data},
    }


def render(operations: list[dict[str, Any]]) -> str:
    if _ck_a2ui is not None:
        return _ck_a2ui.render(operations=operations)
    return json.dumps({"a2ui_operations": operations})


def parse_operations(payload: str | dict | list | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "a2ui_operations" in payload:
            return list(payload["a2ui_operations"])
        if any(k in payload for k in ("createSurface", "updateComponents", "updateDataModel")):
            return [payload]
        return []
    if isinstance(payload, str):
        try:
            return parse_operations(json.loads(payload))
        except json.JSONDecodeError:
            return []
    return []


def surface(surface_id: str, components: list[dict[str, Any]], data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        create_surface(surface_id),
        update_components(surface_id, components),
        update_data_model(surface_id, data),
    ]


PAIRING_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "grid"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "grid", "component": "PairingGrid", "dishes": {"path": "/dishes"}},
]

LIST_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "summary", "table"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {
        "id": "summary",
        "component": "ListSummary",
        "budget": {"path": "/budget"},
        "spent": {"path": "/spent"},
        "remaining": {"path": "/remaining"},
        "targetMargin": {"path": "/target_margin"},
        "coverage": {"path": "/coverage"},
        "gaps": {"path": "/gaps"},
    },
    {"id": "table", "component": "BeverageListTable", "items": {"path": "/items"}},
]

INVENTORY_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "alerts", "table"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "alerts", "component": "StockAlerts", "alerts": {"path": "/alerts"}},
    {"id": "table", "component": "InventoryTable", "items": {"path": "/items"}},
]

PO_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "table"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "table", "component": "PurchaseOrderTable", "orders": {"path": "/orders"}},
]

QUIZ_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "quiz"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "quiz", "component": "QuizCard", "quiz": {"path": "/quiz"}},
]

BRIEFING_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "cards"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "cards", "component": "LessonCards", "lessons": {"path": "/lessons"}},
]

TASTING_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "form", "cal"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "form", "component": "ScheduleForm", "draft": {"path": "/draft"}},
    {"id": "cal", "component": "TastingCalendar", "tastings": {"path": "/tastings"}},
]

DISH_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "dishes"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "dishes", "component": "DishList", "dishes": {"path": "/dishes"}},
]


def pairings_surface(title: str, dishes: list[dict]) -> list[dict[str, Any]]:
    return surface("pairings", PAIRING_SCHEMA, {"title": title, "dishes": dishes})


def dishes_surface(title: str, dishes: list[dict], cuisine: str, price_tier: str) -> list[dict[str, Any]]:
    return surface(
        "dishes",
        DISH_SCHEMA,
        {"title": title, "dishes": dishes, "cuisine": cuisine, "price_tier": price_tier},
    )


def list_surface(payload: dict) -> list[dict[str, Any]]:
    return surface(
        "beverage-list",
        LIST_SCHEMA,
        {
            "title": payload.get("name", "House list"),
            "budget": payload.get("budget"),
            "spent": payload.get("spent"),
            "remaining": payload.get("remaining"),
            "target_margin": payload.get("target_margin"),
            "coverage": payload.get("coverage"),
            "gaps": payload.get("gaps"),
            "items": payload.get("items"),
        },
    )


def inventory_surface(title: str, items: list[dict], alerts: list[dict]) -> list[dict[str, Any]]:
    return surface("inventory", INVENTORY_SCHEMA, {"title": title, "items": items, "alerts": alerts})


def po_surface(title: str, orders: list[dict]) -> list[dict[str, Any]]:
    return surface("purchase-orders", PO_SCHEMA, {"title": title, "orders": orders})


def quiz_surface(title: str, quiz: dict) -> list[dict[str, Any]]:
    return surface("quiz", QUIZ_SCHEMA, {"title": title, "quiz": quiz})


def briefing_surface(title: str, lessons: list[dict]) -> list[dict[str, Any]]:
    return surface("briefing", BRIEFING_SCHEMA, {"title": title, "lessons": lessons})


def tasting_surface(title: str, draft: dict, tastings: list[dict]) -> list[dict[str, Any]]:
    return surface("tasting", TASTING_SCHEMA, {"title": title, "draft": draft, "tastings": tastings})
