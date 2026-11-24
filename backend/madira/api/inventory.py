from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from madira.agents.presenters.inventory import with_inventory
from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import (
    Rejected,
    bin_label_svg,
    bin_public,
    create_bin,
    create_location,
    list_bins,
    list_locations,
    list_movements,
    location_public,
    movement_public,
    post_movement,
    transfer_stock,
)
from madira.domain.inventory.service import set_on_hand, snapshot
from madira.domain.session import session_scope
from madira.models import MOVEMENT_TYPES, Bin, Location, Sku
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id
from sqlalchemy.orm import Session

router = APIRouter()


class StockBody(BaseModel):
    on_hand: Decimal

    @field_validator("on_hand", mode="before")
    @classmethod
    def parse_on_hand(cls, value):
        if isinstance(value, bool) or value is None:
            raise ValueError("on_hand must be a number")
        try:
            qty = Decimal(str(value))
        except Exception as exc:
            raise ValueError("on_hand must be a number") from exc
        if qty < 0:
            raise ValueError("on_hand must be zero or positive")
        return qty


class LocationBody(BaseModel):
    name: str
    kind: str = "cellar"
    notes: str = ""


class BinBody(BaseModel):
    location_id: uuid.UUID
    code: str
    label: str = ""


class MovementBody(BaseModel):
    sku: str
    location_id: uuid.UUID
    quantity: Decimal
    movement_type: str
    bin_id: uuid.UUID | None = None
    unit_cost_cents: int | None = Field(default=None, ge=0)
    source_type: str | None = None
    source_id: str | None = None
    reason: str | None = None


class TransferBody(BaseModel):
    sku: str
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    quantity: Decimal
    from_bin_id: uuid.UUID | None = None
    to_bin_id: uuid.UUID | None = None
    reason: str | None = None


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, Rejected):
        return HTTPException(exc.status, exc.message)
    raise exc


def _run(fn):
    try:
        with session_scope() as session:
            result = fn(session)
            session.commit()
            return result
    except (NotFound, Rejected) as exc:
        raise _fail(exc) from exc


def _movement_dict(session: Session, row) -> dict:
    stock = session.get(Sku, row.sku_id)
    product = stock.variant.product if stock is not None else None
    place = session.get(Location, row.location_id)
    spot = session.get(Bin, row.bin_id) if row.bin_id is not None else None
    return movement_public(
        row,
        stock.barcode if stock is not None else "",
        product.name if product is not None else "",
        place.name if place is not None else "",
        None if spot is None else spot.code,
    )


@router.get("/inventory", dependencies=[require(Capability.INVENTORY_READ)])
def inventory() -> dict[str, Any]:
    return with_inventory(snapshot(active_venue_id()))


@router.patch("/inventory/{sku}", dependencies=[require(Capability.COUNT)])
def inventory_patch(sku: str, body: StockBody) -> dict[str, Any]:
    try:
        set_on_hand(active_venue_id(), sku, body.on_hand)
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc
    except Rejected as exc:
        raise HTTPException(exc.status, exc.message) from exc
    return with_inventory(snapshot(active_venue_id()))


@router.get("/inventory/locations", dependencies=[require(Capability.INVENTORY_READ)])
def inventory_locations() -> dict[str, Any]:
    venue_id = active_venue_id()

    def read(session: Session):
        return {"locations": list_locations(session, venue_id)}

    return _run(read)


@router.post("/inventory/locations", dependencies=[require(Capability.COUNT)])
def inventory_location_create(body: LocationBody) -> dict[str, Any]:
    venue_id = active_venue_id()

    def write(session: Session):
        row = create_location(session, venue_id, body.name, body.kind, body.notes)
        return {"location": location_public(row)}

    return _run(write)


@router.get("/inventory/bins", dependencies=[require(Capability.INVENTORY_READ)])
def inventory_bins(location_id: uuid.UUID | None = None) -> dict[str, Any]:
    venue_id = active_venue_id()

    def read(session: Session):
        return {"bins": list_bins(session, venue_id, location_id)}

    return _run(read)


@router.post("/inventory/bins", dependencies=[require(Capability.COUNT)])
def inventory_bin_create(body: BinBody) -> dict[str, Any]:
    venue_id = active_venue_id()

    def write(session: Session):
        row = create_bin(session, venue_id, body.location_id, body.code, body.label)
        place = session.get(Location, row.location_id)
        return {"bin": bin_public(row, place.name if place is not None else "")}

    return _run(write)


@router.get("/inventory/bins/{bin_id}/qr", dependencies=[require(Capability.INVENTORY_READ)])
def inventory_bin_qr(bin_id: uuid.UUID, request: Request, format: str | None = None):
    venue_id = active_venue_id()
    try:
        with session_scope() as session:
            label = bin_label_svg(session, venue_id, bin_id)
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc
    accept = request.headers.get("accept", "")
    wants_json = (format or "").lower() == "json" or (
        "application/json" in accept and "image/svg+xml" not in accept
    )
    if wants_json:
        return label
    return Response(content=label["svg"], media_type="image/svg+xml")


@router.get("/inventory/movements", dependencies=[require(Capability.INVENTORY_READ)])
def inventory_movements(
    sku: str | None = None,
    location_id: uuid.UUID | None = None,
    movement_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    venue_id = active_venue_id()

    def read(session: Session):
        return {
            "movements": list_movements(
                session,
                venue_id,
                sku=sku,
                location_id=location_id,
                movement_type=movement_type,
                since=since,
                until=until,
                limit=limit,
            )
        }

    return _run(read)


@router.post("/inventory/movements", dependencies=[require(Capability.COUNT)])
def inventory_movement_create(body: MovementBody) -> dict[str, Any]:
    if body.movement_type not in MOVEMENT_TYPES:
        raise HTTPException(422, "movement_type is not recognized")
    venue_id = active_venue_id()

    def write(session: Session):
        row = post_movement(
            session,
            venue_id,
            sku=body.sku,
            location_id=body.location_id,
            bin_id=body.bin_id,
            quantity=body.quantity,
            movement_type=body.movement_type,
            unit_cost_cents=body.unit_cost_cents,
            source_type=body.source_type,
            source_id=body.source_id,
            reason=body.reason,
        )
        return {"movement": _movement_dict(session, row)}

    return _run(write)


@router.post("/inventory/transfers", dependencies=[require(Capability.COUNT)])
def inventory_transfer(body: TransferBody) -> dict[str, Any]:
    venue_id = active_venue_id()

    def write(session: Session):
        outgoing, incoming = transfer_stock(
            session,
            venue_id,
            sku=body.sku,
            from_location_id=body.from_location_id,
            to_location_id=body.to_location_id,
            from_bin_id=body.from_bin_id,
            to_bin_id=body.to_bin_id,
            quantity=body.quantity,
            reason=body.reason,
        )
        return {
            "movements": [_movement_dict(session, outgoing), _movement_dict(session, incoming)],
        }

    return _run(write)
