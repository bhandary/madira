"""Supplier profiles, allocations, offers, and price sheets."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from madira.domain.errors import DraftFailed, NotFound
from madira.domain.procurement import offers
from madira.domain.procurement.offers import OfferError
from madira.jobs.handlers import REQUEST_ATTEMPTS, file_args
from madira.jobs.runner import accept
from madira.rbac import Capability, require
from madira.storage import StorageError, upload_max_bytes
from madira.tenancy import active_venue_id

router = APIRouter()


class ProfileBody(BaseModel):
    rep_name: str | None = None
    rep_email: str | None = None
    rep_phone: str | None = None
    delivery_days: list[str] | None = None
    order_minimum_cents: int | None = None
    order_minimum_currency: str | None = None
    payment_terms: str | None = None
    notes: str | None = None


class AllocationBody(BaseModel):
    product_id: str | None = None
    quantity: int | None = None
    period_label: str | None = None
    period_start: str | None = None
    period_end: str | None = None


class OfferBody(BaseModel):
    supplier_id: str | None = None
    product_id: str | None = None
    sku_id: str | None = None
    unit: str | None = None
    case_size: int | None = None
    price_cents: int | None = None
    currency: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, DraftFailed):
        return HTTPException(exc.status, exc.message)
    if isinstance(exc, (OfferError, StorageError)):
        return HTTPException(exc.status, exc.message)
    return HTTPException(400, str(exc))


def _present(payload: dict) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "a2ui_operations"}


@router.get("/procurement/suppliers/{supplier_id}/desk", dependencies=[require(Capability.RECORDS)])
def supplier_desk(supplier_id: uuid.UUID) -> dict[str, Any]:
    try:
        return offers.supplier_desk(active_venue_id(), supplier_id)
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.patch("/procurement/suppliers/{supplier_id}/profile", dependencies=[require(Capability.SUPPLIERS_MANAGE)])
def update_profile(supplier_id: uuid.UUID, body: ProfileBody) -> dict[str, Any]:
    fields = body.model_dump(exclude_unset=True)
    try:
        return offers.update_profile(active_venue_id(), supplier_id, fields)
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.post("/procurement/suppliers/{supplier_id}/allocations", dependencies=[require(Capability.SUPPLIERS_MANAGE)])
def create_allocation(supplier_id: uuid.UUID, body: AllocationBody) -> dict[str, Any]:
    try:
        return offers.create_allocation(active_venue_id(), supplier_id, body.model_dump(exclude_unset=True))
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.patch("/procurement/allocations/{allocation_id}", dependencies=[require(Capability.SUPPLIERS_MANAGE)])
def update_allocation(allocation_id: uuid.UUID, body: AllocationBody) -> dict[str, Any]:
    try:
        return offers.update_allocation(active_venue_id(), allocation_id, body.model_dump(exclude_unset=True))
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.delete("/procurement/allocations/{allocation_id}", dependencies=[require(Capability.SUPPLIERS_MANAGE)])
def delete_allocation(allocation_id: uuid.UUID) -> dict[str, Any]:
    try:
        return offers.delete_allocation(active_venue_id(), allocation_id)
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.get("/procurement/offers", dependencies=[require(Capability.RECORDS)])
def list_offers(product_id: uuid.UUID | None = None, supplier_id: uuid.UUID | None = None, current: bool = False) -> dict[str, Any]:
    venue_id = active_venue_id()
    try:
        if current:
            return offers.list_current_offers(venue_id, product_id=product_id, supplier_id=supplier_id)
        return offers.list_offers(venue_id, product_id=product_id, supplier_id=supplier_id)
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.post("/procurement/offers", dependencies=[require(Capability.SUPPLIERS_MANAGE)])
def create_offer(body: OfferBody) -> dict[str, Any]:
    try:
        return offers.create_offer(active_venue_id(), body.model_dump(exclude_unset=True))
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.patch("/procurement/offers/{offer_id}", dependencies=[require(Capability.SUPPLIERS_MANAGE)])
def update_offer(offer_id: uuid.UUID, body: OfferBody) -> dict[str, Any]:
    try:
        return offers.update_offer(active_venue_id(), offer_id, body.model_dump(exclude_unset=True))
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.delete("/procurement/offers/{offer_id}", dependencies=[require(Capability.SUPPLIERS_MANAGE)])
def delete_offer(offer_id: uuid.UUID) -> dict[str, Any]:
    try:
        return offers.delete_offer(active_venue_id(), offer_id)
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.get("/procurement/products/{product_id}/price-history", dependencies=[require(Capability.RECORDS)])
def price_history(product_id: uuid.UUID) -> dict[str, Any]:
    try:
        return offers.price_history(active_venue_id(), product_id)
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.post("/procurement/price-sheets", dependencies=[require(Capability.SUPPLIERS_MANAGE)])
def upload_price_sheet(supplier_id: uuid.UUID = Form(), file: UploadFile = File()) -> dict[str, Any]:
    body = file.file.read(upload_max_bytes() + 1)
    try:
        return accept(
            "price_sheet.ingest",
            file_args(body, file.filename or "", file.content_type, supplier_id=str(supplier_id)),
            max_attempts=REQUEST_ATTEMPTS,
        )
    except (NotFound, OfferError, DraftFailed, StorageError) as exc:
        raise _fail(exc) from exc


@router.get("/procurement/price-sheets/{sheet_id}", dependencies=[require(Capability.RECORDS)])
def get_price_sheet(sheet_id: uuid.UUID) -> dict[str, Any]:
    try:
        return offers.get_price_sheet(active_venue_id(), sheet_id)
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.post("/procurement/price-sheets/{sheet_id}/apply", dependencies=[require(Capability.SUPPLIERS_MANAGE)])
def apply_price_sheet(sheet_id: uuid.UUID) -> dict[str, Any]:
    try:
        return offers.apply_price_sheet(active_venue_id(), sheet_id)
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc


@router.post("/procurement/price-sheets/{sheet_id}/reject", dependencies=[require(Capability.SUPPLIERS_MANAGE)])
def reject_price_sheet(sheet_id: uuid.UUID) -> dict[str, Any]:
    try:
        return _present(offers.reject_price_sheet(active_venue_id(), sheet_id))
    except (NotFound, OfferError) as exc:
        raise _fail(exc) from exc
