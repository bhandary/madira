"""Cellar surfaces. On-hand, par, and reorder quantities come from the inventory service."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

INVENTORY_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "alerts", "table"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "alerts", "component": "StockAlerts", "alerts": {"path": "/alerts"}},
    {"id": "table", "component": "InventoryTable", "items": {"path": "/items"}},
]


def inventory_surface(title: str, items: list[dict], alerts: list[dict]) -> list[dict[str, Any]]:
    return surface("inventory", INVENTORY_SCHEMA, {"title": title, "items": items, "alerts": alerts})


def with_inventory(payload: dict) -> dict:
    body = {"items": payload["items"], "alerts": payload["alerts"]}
    body["a2ui_operations"] = inventory_surface("Cellar inventory", payload["items"], payload["alerts"])
    return body
