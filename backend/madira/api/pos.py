"""POS connect, mapping, and on-demand sync. The access token is never returned."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from madira.agents.presenters.pos import with_status, with_unmapped
from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import Rejected
from madira.domain.pos.adapter import PosError
from madira.domain.pos.service import (
    catalog,
    connect_demo,
    connect_square,
    list_mappings,
    list_runs,
    remove_mapping,
    save_mapping,
    set_location,
    status,
    unmapped_items,
)
from madira.jobs.handlers import SCHEDULED_ATTEMPTS
from madira.jobs.runner import accept
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter(tags=["pos"])


class SquareConnectBody(BaseModel):
    access_token: str = ""
    location_id: str = ""


class LocationBody(BaseModel):
    location_id: str


class MappingBody(BaseModel):
    variation_id: str
    item_id: str = ""
    sku: str
    pour_ml: int | None = None
    units_per_sale: str = "1"


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, PosError):
        return HTTPException(exc.status, exc.message)
    if isinstance(exc, Rejected):
        return HTTPException(exc.status, exc.message)
    return HTTPException(400, "POS request failed.")


@router.get("/pos/status", dependencies=[require(Capability.RECORDS)])
def pos_status() -> dict[str, Any]:
    try:
        return with_status(status(active_venue_id()))
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc


@router.get("/pos/catalog", dependencies=[require(Capability.RECORDS)])
def pos_catalog() -> dict[str, Any]:
    try:
        return catalog(active_venue_id())
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc


@router.get("/pos/mappings", dependencies=[require(Capability.RECORDS)])
def pos_mappings() -> dict[str, Any]:
    try:
        return list_mappings(active_venue_id())
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/pos/mappings", dependencies=[require(Capability.POS_MANAGE)])
def pos_save_mapping(body: MappingBody) -> dict[str, Any]:
    try:
        return save_mapping(
            active_venue_id(),
            variation_id=body.variation_id,
            item_id=body.item_id,
            sku=body.sku,
            pour_ml=body.pour_ml,
            units_per_sale=body.units_per_sale,
        )
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc


@router.delete("/pos/mappings/{mapping_id}", dependencies=[require(Capability.POS_MANAGE)])
def pos_remove_mapping(mapping_id: uuid.UUID) -> dict[str, Any]:
    try:
        return remove_mapping(active_venue_id(), mapping_id)
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc


@router.get("/pos/runs", dependencies=[require(Capability.RECORDS)])
def pos_runs() -> dict[str, Any]:
    try:
        return list_runs(active_venue_id())
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc


@router.get("/pos/gaps", dependencies=[require(Capability.RECORDS)])
def pos_gaps() -> dict[str, Any]:
    try:
        return with_unmapped(unmapped_items(active_venue_id()))
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/pos/connect/demo", dependencies=[require(Capability.POS_MANAGE)])
def pos_connect_demo() -> dict[str, Any]:
    try:
        return with_status(connect_demo(active_venue_id()))
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/pos/connect/square", dependencies=[require(Capability.POS_MANAGE)])
def pos_connect_square(body: SquareConnectBody) -> dict[str, Any]:
    try:
        return with_status(connect_square(active_venue_id(), body.access_token, body.location_id))
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/pos/location", dependencies=[require(Capability.POS_MANAGE)])
def pos_location(body: LocationBody) -> dict[str, Any]:
    try:
        return with_status(set_location(active_venue_id(), body.location_id))
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/pos/sync", dependencies=[require(Capability.POS_MANAGE)])
def pos_sync() -> dict[str, Any]:
    try:
        return accept("pos.sync", {}, max_attempts=SCHEDULED_ATTEMPTS)
    except (NotFound, PosError, Rejected) as exc:
        raise _fail(exc) from exc
