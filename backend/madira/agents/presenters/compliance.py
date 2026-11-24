"""Compliance surfaces. Chain status and event rows come from the compliance service."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

AUDIT_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "table"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {
        "id": "table",
        "component": "AuditTable",
        "events": {"path": "/events"},
        "chain": {"path": "/chain"},
    },
]


def audit_surface(events: list[dict], chain: dict) -> list[dict[str, Any]]:
    return surface("audit", AUDIT_SCHEMA, {"title": "Audit ledger", "events": events, "chain": chain})


def with_audit(events: list[dict], chain: dict) -> dict:
    return {"events": events, "chain": chain, "a2ui_operations": audit_surface(events, chain)}


ZONE_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "card"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "card", "component": "ZoneConditionCard", "zone": {"path": "/zone"}},
]


def zone_surface(zone: dict) -> list[dict[str, Any]]:
    return surface(
        f"zone-{zone.get('id')}",
        ZONE_SCHEMA,
        {"title": zone.get("name") or "Storage zone", "zone": zone},
    )


def with_zones(zones: list[dict]) -> dict:
    operations: list[dict[str, Any]] = []
    for zone in zones:
        operations.extend(zone_surface(zone))
    return {"zones": zones, "a2ui_operations": operations}
