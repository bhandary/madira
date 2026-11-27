"""List curation surfaces. Budget, spend, margins, and health come from the list service."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from madira.agents.presenters.ops import surface

LIST_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "summary", "editor", "grid", "table"]},
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
    {
        "id": "editor",
        "component": "ListEditor",
        "listId": {"path": "/list_id"},
        "currency": {"path": "/currency"},
        "sections": {"path": "/sections"},
        "items": {"path": "/items"},
        "candidates": {"path": "/candidates"},
    },
    {"id": "grid", "component": "CoverageGrid", "cells": {"path": "/cells"}},
    {"id": "table", "component": "BeverageListTable", "items": {"path": "/items"}},
]


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def list_surface(payload: dict) -> list[dict[str, Any]]:
    data = _plain(
        {
            "title": payload.get("name", "House list"),
            "list_id": payload.get("list_id") or payload.get("id") or "",
            "budget": payload.get("budget"),
            "spent": payload.get("spent"),
            "remaining": payload.get("remaining"),
            "currency": payload.get("currency") or "USD",
            "target_margin": payload.get("target_margin"),
            "target_beverage_cost_pct": payload.get("target_beverage_cost_pct"),
            "coverage": payload.get("coverage"),
            "gaps": payload.get("gaps"),
            "items": payload.get("items") or [],
            "sections": payload.get("sections") or [],
            "cells": payload.get("cells") or [],
            "candidates": payload.get("candidates") or [],
            "health": payload.get("health") or {"flags": []},
        }
    )
    return surface("beverage-list", LIST_SCHEMA, data)


def with_list(payload: dict) -> dict:
    body = dict(payload)
    body["a2ui_operations"] = list_surface(body)
    return body


LIST_APPROVAL_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "card"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {
        "id": "card",
        "component": "ApprovalCard",
        "purchaseOrder": {"path": "/purchaseOrder"},
        "approval": {"path": "/approval"},
        "listVersion": {"path": "/listVersion"},
    },
]


def with_list_approval(version: dict) -> dict:
    """An ApprovalCard for a list version. Publishing stays on the REST approve route."""

    number = int(version.get("number") or 0)
    name = version.get("list_name") or "List"
    approval = version.get("approval") or {}
    body = {
        "version": version,
        "a2ui_operations": surface(
            "list-publish-approval",
            LIST_APPROVAL_SCHEMA,
            {
                "title": f"{name} v{number}",
                "purchaseOrder": {
                    "id": str(version.get("id") or ""),
                    "po_number": f"{name} v{number}",
                    "status": version.get("status") or "pending_approval",
                    "currency": version.get("currency") or "USD",
                    "minimum_met": True,
                },
                "approval": {
                    "id": str(approval.get("id") or ""),
                    "decision": approval.get("decision") or "pending",
                    "required_role": approval.get("required_role") or "owner",
                    "comment": approval.get("comment") or "",
                    "decided_at": approval.get("decided_at") or "",
                },
                "listVersion": {
                    "id": str(version.get("id") or ""),
                    "list_id": str(version.get("list_id") or ""),
                    "list_name": name,
                    "number": number,
                    "status": version.get("status") or "pending_approval",
                },
            },
        ),
    }
    return body
