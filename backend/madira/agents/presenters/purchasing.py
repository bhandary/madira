"""Purchase-order surfaces. Line totals come from the purchasing service."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

PO_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "table"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "table", "component": "PurchaseOrderTable", "orders": {"path": "/orders"}},
]


def po_surface(title: str, orders: list[dict]) -> list[dict[str, Any]]:
    return surface("purchase-orders", PO_SCHEMA, {"title": title, "orders": orders})


def with_orders(payload: dict) -> dict:
    body = {"orders": payload["orders"]}
    body["a2ui_operations"] = po_surface("Draft purchase orders", payload["orders"])
    return body
