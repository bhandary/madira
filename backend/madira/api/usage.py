"""Organization usage. Editing the cap is Owner only. Nothing is billed."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from madira.domain.errors import NotFound
from madira.domain.usage.service import UsageError, update_limits, usage_report
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter(tags=["usage"])


class LimitsBody(BaseModel):
    monthly_spend_cap_cents: int | None = None
    requests_per_minute: int | None = None


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, UsageError):
        return HTTPException(exc.status, exc.message)
    return HTTPException(400, "Usage could not be updated.")


@router.get("/usage", dependencies=[require(Capability.RECORDS)])
def get_usage() -> dict[str, Any]:
    try:
        return usage_report(active_venue_id())
    except NotFound as exc:
        raise _fail(exc) from exc


@router.put("/usage/limits", dependencies=[require(Capability.USAGE_MANAGE)])
def put_limits(body: LimitsBody) -> dict[str, Any]:
    try:
        return update_limits(
            active_venue_id(),
            monthly_spend_cap_cents=body.monthly_spend_cap_cents,
            requests_per_minute=body.requests_per_minute,
        )
    except (NotFound, UsageError) as exc:
        raise _fail(exc) from exc
