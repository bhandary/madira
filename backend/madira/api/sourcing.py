"""Sourcing briefs and tasting history. Decisions stay on the tasting routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from madira.agents.presenters.procurement import with_brief, with_history
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.sourcing.service import build_brief, get_brief, link_want_item, list_briefs, tasting_history
from madira.domain.tastings.service import TastingError
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter()


class WantLink(BaseModel):
    sample_id: str | None = None
    offer_id: str | None = None
    clear_sample: bool = False
    clear_offer: bool = False


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, DraftFailed):
        return HTTPException(exc.status, exc.message)
    if isinstance(exc, TastingError):
        return HTTPException(exc.status, exc.message)
    return HTTPException(400, str(exc))


@router.get("/sourcing/briefs", dependencies=[require(Capability.RECORDS)])
def sourcing_briefs() -> dict[str, Any]:
    try:
        payload = list_briefs(active_venue_id())
        if not payload["briefs"]:
            return payload
        return with_brief({"brief": payload["briefs"][0], "briefs": payload["briefs"]})
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc


@router.post("/sourcing/briefs", dependencies=[require(Capability.TASTINGS_MANAGE)])
def sourcing_briefs_create() -> dict[str, Any]:
    try:
        return with_brief(build_brief(active_venue_id()))
    except (NotFound, TastingError, DraftFailed) as exc:
        raise _fail(exc) from exc


@router.get("/sourcing/briefs/{brief_id}", dependencies=[require(Capability.RECORDS)])
def sourcing_brief(brief_id: uuid.UUID) -> dict[str, Any]:
    try:
        return with_brief(get_brief(active_venue_id(), brief_id))
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc


@router.patch("/sourcing/items/{item_id}", dependencies=[require(Capability.TASTINGS_MANAGE)])
def sourcing_item(item_id: uuid.UUID, body: WantLink) -> dict[str, Any]:
    try:
        return with_brief(
            link_want_item(
                active_venue_id(),
                item_id,
                sample_id=body.sample_id,
                offer_id=body.offer_id,
                clear_sample=body.clear_sample,
                clear_offer=body.clear_offer,
            )
        )
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc


@router.get("/sourcing/history", dependencies=[require(Capability.RECORDS)])
def sourcing_history(supplier_id: uuid.UUID | None = None, product_id: uuid.UUID | None = None) -> dict[str, Any]:
    try:
        return with_history(tasting_history(active_venue_id(), supplier_id=supplier_id, product_id=product_id))
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc
