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
    if "locations" in payload:
        body["locations"] = payload["locations"]
    body["a2ui_operations"] = inventory_surface("Cellar inventory", payload["items"], payload["alerts"])
    return body


COUNT_SHEET_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "sheet"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "sheet", "component": "CountSheet", "session": {"path": "/session"}, "lines": {"path": "/lines"}},
]

VARIANCE_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "report"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "report", "component": "VarianceReport", "report": {"path": "/report"}},
]


def count_sheet_surface(count_session: dict, lines: list[dict]) -> list[dict[str, Any]]:
    title = "Count sheet"
    place = count_session.get("location_name")
    if place:
        title = f"Count sheet · {place}"
    return surface("count-sheet", COUNT_SHEET_SCHEMA, {"title": title, "session": count_session, "lines": lines})


def variance_surface(report: dict) -> list[dict[str, Any]]:
    return surface("variance-report", VARIANCE_SCHEMA, {"title": "Variance report", "report": report})


def with_count_report(payload: dict) -> dict:
    """Attach CountSheet and VarianceReport operations to a count report."""

    body = dict(payload)
    session = payload.get("session") or {}
    lines = payload.get("lines") or []
    report = {
        "session": session,
        "lines": payload.get("variance_lines") or [],
        "conflicts": payload.get("conflicts") or [],
    }
    body["a2ui_operations"] = count_sheet_surface(session, lines) + variance_surface(report)
    return body
