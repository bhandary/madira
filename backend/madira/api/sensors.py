"""Sensor registry, CSV review, and the signed webhook. The secret is not logged."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from madira.domain.errors import NotFound
from madira.domain.inventory.storage import Rejected
from madira.domain.sensors.service import (
    SensorError,
    accept_webhook,
    apply_import,
    create_sensor,
    list_imports,
    list_sensors,
    preview_csv,
    reject_import,
    rotate_secret,
)
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter(tags=["sensors"])


class SensorBody(BaseModel):
    name: str
    zone_id: uuid.UUID
    metric: str
    external_id: str


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, SensorError):
        return HTTPException(exc.status, exc.message)
    if isinstance(exc, Rejected):
        return HTTPException(exc.status, exc.message)
    return HTTPException(400, "Sensor request failed.")


@router.get("/sensors", dependencies=[require(Capability.RECORDS)])
def sensors() -> dict[str, Any]:
    try:
        return list_sensors(active_venue_id())
    except (NotFound, SensorError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/sensors", dependencies=[require(Capability.SENSORS_MANAGE)])
def add_sensor(body: SensorBody) -> dict[str, Any]:
    try:
        return create_sensor(
            active_venue_id(),
            name=body.name,
            zone_id=body.zone_id,
            metric=body.metric,
            external_id=body.external_id,
        )
    except (NotFound, SensorError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/sensors/{sensor_id}/rotate", dependencies=[require(Capability.SENSORS_MANAGE)])
def rotate(sensor_id: uuid.UUID) -> dict[str, Any]:
    try:
        return rotate_secret(active_venue_id(), sensor_id)
    except (NotFound, SensorError, Rejected) as exc:
        raise _fail(exc) from exc


@router.get("/sensors/imports", dependencies=[require(Capability.RECORDS)])
def imports() -> dict[str, Any]:
    try:
        return list_imports(active_venue_id())
    except (NotFound, SensorError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/sensors/imports", dependencies=[require(Capability.SENSORS_MANAGE)])
async def upload_csv(file: UploadFile = File(...), filename: str = Form("")) -> dict[str, Any]:
    raw = await file.read()
    try:
        return preview_csv(active_venue_id(), filename or file.filename or "readings.csv", raw)
    except (NotFound, SensorError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/sensors/imports/{import_id}/apply", dependencies=[require(Capability.SENSORS_MANAGE)])
def apply_csv(import_id: uuid.UUID) -> dict[str, Any]:
    try:
        return apply_import(active_venue_id(), import_id)
    except (NotFound, SensorError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/sensors/imports/{import_id}/reject", dependencies=[require(Capability.SENSORS_MANAGE)])
def reject_csv(import_id: uuid.UUID) -> dict[str, Any]:
    try:
        return reject_import(active_venue_id(), import_id)
    except (NotFound, SensorError, Rejected) as exc:
        raise _fail(exc) from exc


@router.post("/sensors/webhook/{sensor_key}")
async def webhook(sensor_key: str, request: Request) -> dict[str, Any]:
    raw = await request.body()
    try:
        return accept_webhook(
            sensor_key,
            raw,
            request.headers.get("x-madira-timestamp", ""),
            request.headers.get("x-madira-signature", ""),
        )
    except (NotFound, SensorError, Rejected) as exc:
        raise _fail(exc) from exc
