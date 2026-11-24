from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from madira.agents.presenters.purchasing import with_drafted, with_orders, with_purchase_order
from madira.domain.compliance.service import Rejected as VaultRejected
from madira.domain.errors import NotFound
from madira.domain.procurement import orders as lifecycle
from madira.domain.procurement.orders import OrderError
from madira.domain.purchasing.service import draft, list_orders
from madira.rbac import Capability, require
from madira.storage import StorageError
from madira.tenancy import active_venue_id, current_request

router = APIRouter()


class SupplierBody(BaseModel):
    name: str
    kind: str = "distributor"
    contact_email: str = ""
    account_number: str | None = None
    order_minimum_cents: int = 0
    default_case_size: int = 12
    delivery_days: list[str] = Field(default_factory=list)
    lead_time_days: int = 7
    payment_terms: str | None = None
    notes: str | None = None


class ContactBody(BaseModel):
    name: str
    role: str | None = None
    email: str
    phone: str | None = None
    is_primary: bool = False


class LineBody(BaseModel):
    sku: str
    product_name: str = ""
    sku_id: uuid.UUID | None = None
    case_size: int | None = None
    cases_ordered: int | None = None
    bottles: int | None = None
    quantity_ordered: str | None = None
    unit_cost_cents: int | None = None
    vintage: str | None = None
    notes: str | None = None


class OrderBody(BaseModel):
    supplier_id: uuid.UUID
    lines: list[LineBody]
    notes: str | None = None


class DecisionBody(BaseModel):
    comment: str | None = None


def _actor():
    return current_request()


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, (OrderError, VaultRejected)):
        return HTTPException(exc.status, exc.message)
    if isinstance(exc, StorageError):
        return HTTPException(exc.status, exc.message)
    raise exc


def _call(fn):
    try:
        return fn()
    except (NotFound, OrderError, VaultRejected, StorageError) as exc:
        raise _fail(exc) from exc


@router.post("/purchase-orders/draft", dependencies=[require(Capability.APPROVE)])
def po_draft() -> dict[str, Any]:
    return with_orders(draft(active_venue_id()))


@router.get("/purchase-orders", dependencies=[require(Capability.RECORDS)])
def po_list() -> dict[str, Any]:
    return list_orders(active_venue_id())


@router.get("/procurement/suppliers", dependencies=[require(Capability.PO_READ)])
def procurement_suppliers() -> dict[str, Any]:
    return _call(lambda: lifecycle.list_supplier_directory(active_venue_id()))


@router.post("/procurement/suppliers", dependencies=[require(Capability.PO_WRITE)])
def procurement_supplier_create(body: SupplierBody) -> dict[str, Any]:
    return _call(lambda: lifecycle.create_supplier(active_venue_id(), body.model_dump()))


@router.post("/procurement/suppliers/{supplier_id}/contacts", dependencies=[require(Capability.PO_WRITE)])
def procurement_contact_create(supplier_id: uuid.UUID, body: ContactBody) -> dict[str, Any]:
    return _call(lambda: lifecycle.add_supplier_contact(active_venue_id(), supplier_id, body.model_dump()))


@router.get("/procurement/orders", dependencies=[require(Capability.PO_READ)])
def procurement_orders() -> dict[str, Any]:
    return _call(lambda: lifecycle.list_purchase_orders(active_venue_id()))


@router.post("/procurement/orders", dependencies=[require(Capability.PO_WRITE)])
def procurement_order_create(body: OrderBody) -> dict[str, Any]:
    lines = [line.model_dump() for line in body.lines]

    def create():
        order = lifecycle.create_purchase_order(active_venue_id(), body.supplier_id, lines, _actor(), body.notes)
        return with_purchase_order(order)

    return _call(create)


@router.post("/procurement/orders/draft-from-reorder", dependencies=[require(Capability.PO_WRITE)])
def procurement_draft_reorder() -> dict[str, Any]:
    return _call(lambda: with_drafted(lifecycle.draft_orders_from_reorder(active_venue_id(), _actor())))


@router.get("/procurement/orders/{po_id}", dependencies=[require(Capability.PO_READ)])
def procurement_order_get(po_id: uuid.UUID) -> dict[str, Any]:
    return _call(lambda: with_purchase_order(lifecycle.get_purchase_order(active_venue_id(), po_id)))


@router.post("/procurement/orders/{po_id}/approve", dependencies=[require(Capability.PO_DECIDE)])
def procurement_order_approve(po_id: uuid.UUID, body: DecisionBody | None = None) -> dict[str, Any]:
    comment = None if body is None else body.comment
    return _call(
        lambda: with_purchase_order(lifecycle.approve_purchase_order(active_venue_id(), po_id, _actor(), comment))
    )


@router.post("/procurement/orders/{po_id}/reject", dependencies=[require(Capability.PO_DECIDE)])
def procurement_order_reject(po_id: uuid.UUID, body: DecisionBody | None = None) -> dict[str, Any]:
    comment = None if body is None else body.comment
    return _call(
        lambda: with_purchase_order(lifecycle.reject_purchase_order(active_venue_id(), po_id, _actor(), comment))
    )


@router.post("/procurement/orders/{po_id}/send", dependencies=[require(Capability.PO_WRITE)])
def procurement_order_send(po_id: uuid.UUID) -> dict[str, Any]:
    return _call(lambda: with_purchase_order(lifecycle.send_purchase_order(active_venue_id(), po_id, _actor())))


@router.post("/procurement/orders/{po_id}/close", dependencies=[require(Capability.PO_WRITE)])
def procurement_order_close(po_id: uuid.UUID) -> dict[str, Any]:
    return _call(lambda: with_purchase_order(lifecycle.close_purchase_order(active_venue_id(), po_id, _actor())))


@router.post("/procurement/orders/{po_id}/cancel", dependencies=[require(Capability.PO_WRITE)])
def procurement_order_cancel(po_id: uuid.UUID) -> dict[str, Any]:
    return _call(lambda: with_purchase_order(lifecycle.cancel_purchase_order(active_venue_id(), po_id, _actor())))


@router.get("/procurement/orders/{po_id}/pdf", dependencies=[require(Capability.PO_READ)])
def procurement_order_pdf(po_id: uuid.UUID) -> Response:
    try:
        filename, payload = lifecycle.purchase_order_pdf(active_venue_id(), po_id)
    except (NotFound, OrderError, StorageError) as exc:
        raise _fail(exc) from exc
    quoted = filename.replace("\\", "").replace('"', "")
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{quoted}"'},
    )
