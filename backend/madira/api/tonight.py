"""Tonight's briefing, floor lookup, and the 86 toggle."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from madira.agents.presenters.training import with_lookup, with_tonight_briefing
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.inventory.eighty_six import set_eighty_six
from madira.domain.training.briefing import (
    acknowledge,
    completion_report,
    get_or_build_today,
    publish,
    rebuild,
    tonight,
)
from madira.domain.training.lookup import lookup
from madira.rbac import Capability, require

router = APIRouter()


class AckBody(BaseModel):
    seconds_to_ack: int = Field(ge=0, le=86400)


def _raise(exc: Exception) -> None:
    if isinstance(exc, NotFound):
        raise HTTPException(404, exc.message) from exc
    if isinstance(exc, DraftFailed):
        raise HTTPException(exc.status, exc.message) from exc
    raise exc


@router.get("/tonight", dependencies=[require(Capability.FLOOR)])
def tonight_board() -> dict[str, Any]:
    try:
        return tonight()
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.get("/tonight/briefing", dependencies=[require(Capability.FLOOR)])
def tonight_briefing() -> dict[str, Any]:
    try:
        return with_tonight_briefing(get_or_build_today())
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/tonight/briefing/rebuild", dependencies=[require(Capability.COUNT)])
def tonight_rebuild() -> dict[str, Any]:
    try:
        return rebuild()
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/tonight/briefing/publish", dependencies=[require(Capability.COUNT)])
def tonight_publish() -> dict[str, Any]:
    try:
        return publish()
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.get("/tonight/briefing/report", dependencies=[require(Capability.RECORDS)])
def tonight_report(start: date, end: date) -> dict[str, Any]:
    try:
        return completion_report(start, end)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/tonight/briefing/{briefing_id}/ack", dependencies=[require(Capability.FLOOR)])
def tonight_ack(briefing_id: uuid.UUID, body: AckBody) -> dict[str, Any]:
    try:
        return acknowledge(briefing_id, body.seconds_to_ack)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.get("/lookup", dependencies=[require(Capability.FLOOR)])
def floor_lookup(q: str = "") -> dict[str, Any]:
    try:
        return with_lookup(lookup(q))
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/cellar/skus/{sku_id}/86", dependencies=[require(Capability.COUNT)])
def cellar_eighty_six(sku_id: uuid.UUID) -> dict[str, Any]:
    try:
        return set_eighty_six(sku_id, True)
    except NotFound as exc:
        _raise(exc)


@router.delete("/cellar/skus/{sku_id}/86", dependencies=[require(Capability.COUNT)])
def cellar_clear_eighty_six(sku_id: uuid.UUID) -> dict[str, Any]:
    try:
        return set_eighty_six(sku_id, False)
    except NotFound as exc:
        _raise(exc)
