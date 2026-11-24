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


APPROVAL_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "card"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {
        "id": "card",
        "component": "ApprovalCard",
        "purchaseOrder": {"path": "/purchaseOrder"},
        "approval": {"path": "/approval"},
    },
]


def _card_order(order: dict) -> dict:
    return {
        "id": str(order.get("id") or ""),
        "po_number": order.get("po_number") or "",
        "supplier": order.get("supplier") or "",
        "status": order.get("status") or "draft",
        "subtotal_cents": int(order.get("subtotal_cents") or order.get("total") or 0),
        "order_minimum_cents": int(order.get("order_minimum_cents") or 0),
        "minimum_met": bool(order.get("minimum_met", True)),
        "shortfall_cents": int(order.get("shortfall_cents") or 0),
        "expected_delivery_date": order.get("expected_delivery_date") or "",
        "currency": order.get("currency") or "USD",
    }


def _card_approval(order: dict) -> dict:
    approval = order.get("approval") or {}
    return {
        "id": str(approval.get("id") or ""),
        "decision": approval.get("decision") or "pending",
        "required_role": approval.get("required_role") or "owner",
        "comment": approval.get("comment") or "",
        "decided_at": approval.get("decided_at") or "",
    }


def approval_surface(order: dict, surface_id: str = "purchase-order-approval") -> list[dict[str, Any]]:
    number = order.get("po_number") or "Purchase order"
    return surface(
        surface_id,
        APPROVAL_SCHEMA,
        {
            "title": str(number),
            "purchaseOrder": _card_order(order),
            "approval": _card_approval(order),
        },
    )


def with_orders(payload: dict) -> dict:
    orders = payload["orders"]
    operations = po_surface("Draft purchase orders", orders)
    for order in orders:
        if order.get("id"):
            operations.extend(approval_surface(order, surface_id=f"purchase-order-approval-{order['id']}"))
    return {"orders": orders, "a2ui_operations": operations}


def with_purchase_order(order: dict) -> dict:
    body = dict(order)
    body["a2ui_operations"] = approval_surface(order)
    return body


def with_drafted(payload: dict) -> dict:
    orders = payload["orders"]
    operations = po_surface("Draft purchase orders", orders)
    for order in orders:
        operations.extend(approval_surface(order, surface_id=f"purchase-order-approval-{order['id']}"))
    return {"orders": orders, "a2ui_operations": operations}


RECEIVING_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "checklist"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {
        "id": "checklist",
        "component": "ReceivingChecklist",
        "purchaseOrder": {"path": "/purchaseOrder"},
        "receipt": {"path": "/receipt"},
        "lines": {"path": "/lines"},
    },
]


def receiving_checklist_surface(receipt: dict, surface_id: str = "receiving-checklist") -> list[dict[str, Any]]:
    number = receipt.get("po_number") or "Delivery"
    summary = receipt.get("discrepancy_summary") or {}
    return surface(
        surface_id,
        RECEIVING_SCHEMA,
        {
            "title": f"Receiving {number}",
            "purchaseOrder": {
                "id": str(receipt.get("purchase_order_id") or ""),
                "po_number": receipt.get("po_number") or "",
                "supplier": receipt.get("supplier") or "",
                "status": receipt.get("purchase_order_status") or "",
            },
            "receipt": {
                "id": str(receipt.get("id") or ""),
                "status": receipt.get("status") or "draft",
                "invoice_id": receipt.get("invoice_id") or "",
                "notes": receipt.get("notes") or "",
                "discrepancy_summary": summary,
            },
            "lines": list(receipt.get("lines") or []),
        },
    )


def with_receipt(receipt: dict) -> dict:
    body = dict(receipt)
    surface_id = "receiving-checklist"
    if receipt.get("id"):
        surface_id = f"receiving-checklist-{receipt['id']}"
    body["a2ui_operations"] = receiving_checklist_surface(receipt, surface_id=surface_id)
    return body
