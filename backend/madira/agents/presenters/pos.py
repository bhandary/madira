"""POS status and unmapped-item surfaces. Numbers come from the POS service."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

STATUS_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "card"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "card", "component": "PosStatus", "status": {"path": "/status"}},
]

UNMAPPED_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "card"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "card", "component": "UnmappedPos", "items": {"path": "/items"}},
]


def with_status(payload: dict) -> dict:
    body = dict(payload)
    body["a2ui_operations"] = surface("pos-status", STATUS_SCHEMA, {"title": "POS", "status": payload})
    return body


def with_unmapped(payload: dict) -> dict:
    items = payload.get("items") or []
    body = {"items": items}
    body["a2ui_operations"] = surface(
        "pos-unmapped",
        UNMAPPED_SCHEMA,
        {"title": "Unmapped POS items", "items": items},
    )
    return body
