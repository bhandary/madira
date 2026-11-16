"""List curation surfaces. Budget, spend, and margins come from the list service."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

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


def list_surface(payload: dict) -> list[dict[str, Any]]:
    return surface(
        "beverage-list",
        LIST_SCHEMA,
        {
            "title": payload.get("name", "House list"),
            "budget": payload.get("budget"),
            "spent": payload.get("spent"),
            "remaining": payload.get("remaining"),
            "currency": payload.get("currency") or "USD",
            "target_margin": payload.get("target_margin"),
            "coverage": payload.get("coverage"),
            "gaps": payload.get("gaps"),
            "items": payload.get("items"),
        },
    )


def with_list(payload: dict) -> dict:
    body = dict(payload)
    body["a2ui_operations"] = list_surface(body)
    return body
