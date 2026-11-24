"""Storage zones, readings, and excursion acknowledgements."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from madira.domain.errors import NotFound
from madira.domain.inventory import storage
from madira.domain.session import session_scope
from madira.rbac import Capability, require
from madira.tenancy import RequestContext, active_venue_id
from sqlalchemy.orm import Session

router = APIRouter()


class ZoneBody(BaseModel):
    name: str
    location_id: uuid.UUID | None = None
    target_temp_min_c: Any
    target_temp_max_c: Any
    target_humidity_min_pct: Any
    target_humidity_max_pct: Any
    notes: str | None = None


class ReadingBody(BaseModel):
    temp_c: Any
    humidity_pct: Any
    notes: str | None = None
    source: str = "manual"


class AcknowledgeBody(BaseModel):
    resolution_note: str | None = None


def _fail(exc: Exception):
    from fastapi import HTTPException

    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, storage.Rejected):
        return HTTPException(exc.status, exc.message)
    raise exc


def _run(fn):
    try:
        with session_scope() as session:
            result = fn(session)
            session.commit()
            return result
    except (NotFound, storage.Rejected) as exc:
        raise _fail(exc) from exc


@router.get("/inventory/storage-zones", dependencies=[require(Capability.INVENTORY_READ)])
def storage_zones() -> dict[str, Any]:
    venue_id = active_venue_id()

    def read(session: Session):
        return {"zones": storage.list_storage_zones(session, venue_id)}

    return _run(read)


@router.post("/inventory/storage-zones")
def storage_zone_create(body: ZoneBody, ctx: RequestContext = require(Capability.COUNT)) -> dict[str, Any]:
    def write(session: Session):
        row = storage.create_storage_zone(
            session,
            ctx.venue_id,
            name=body.name,
            location_id=body.location_id,
            target_temp_min_c=body.target_temp_min_c,
            target_temp_max_c=body.target_temp_max_c,
            target_humidity_min_pct=body.target_humidity_min_pct,
            target_humidity_max_pct=body.target_humidity_max_pct,
            notes=body.notes,
        )
        return {"zone": storage.zone_public(session, row)}

    return _run(write)


@router.get("/inventory/storage-zones/{zone_id}/readings", dependencies=[require(Capability.INVENTORY_READ)])
def storage_readings(zone_id: uuid.UUID) -> dict[str, Any]:
    venue_id = active_venue_id()

    def read(session: Session):
        return {"readings": storage.list_readings(session, venue_id, zone_id)}

    return _run(read)


@router.post("/inventory/storage-zones/{zone_id}/readings")
def storage_reading_create(
    zone_id: uuid.UUID,
    body: ReadingBody,
    ctx: RequestContext = require(Capability.COUNT),
) -> dict[str, Any]:
    def write(session: Session):
        return storage.record_condition_reading(
            session,
            ctx.venue_id,
            zone_id,
            body.temp_c,
            body.humidity_pct,
            ctx,
            notes=body.notes,
            source=body.source,
        )

    return _run(write)


@router.get("/inventory/excursions", dependencies=[require(Capability.INVENTORY_READ)])
def storage_excursions(status: str | None = None) -> dict[str, Any]:
    venue_id = active_venue_id()

    def read(session: Session):
        return {"excursions": storage.list_excursions(session, venue_id, status)}

    return _run(read)


@router.post("/inventory/excursions/{excursion_id}/acknowledge")
def storage_excursion_acknowledge(
    excursion_id: uuid.UUID,
    body: AcknowledgeBody | None = None,
    ctx: RequestContext = require(Capability.COUNT),
) -> dict[str, Any]:
    note = None if body is None else body.resolution_note

    def write(session: Session):
        return {"excursion": storage.acknowledge_excursion(session, ctx.venue_id, excursion_id, ctx, note)}

    return _run(write)
