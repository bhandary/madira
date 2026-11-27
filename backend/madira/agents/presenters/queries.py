"""Auditor tables. Totals and rows come from the query service."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

TABLE_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "table"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "table", "component": "AuditorTable", "table": {"path": "/table"}},
]


def with_table(payload: dict) -> dict:
    table = payload.get("audit_table") or {}
    body = {"audit_table": table}
    body["a2ui_operations"] = surface(
        f"audit-query-{(table.get('title') or 'table').lower().replace(' ', '-')}",
        TABLE_SCHEMA,
        {"title": table.get("title") or "Audit", "table": table},
    )
    return body
