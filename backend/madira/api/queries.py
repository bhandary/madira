"""Read-only auditor queries. Venue scope is the session."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from madira.domain.compliance.queries import (
    QueryError,
    audit_events,
    compliance_status,
    conditions,
    list_versions,
    pos_gaps,
    purchases,
    stock_movements,
)
from madira.domain.errors import NotFound
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter(tags=["compliance-queries"])


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, QueryError):
        return HTTPException(exc.status, exc.message)
    return HTTPException(400, "The query could not be run.")


def _run(fn, **kwargs) -> dict[str, Any]:
    try:
        return fn(active_venue_id(), **kwargs)
    except (NotFound, QueryError) as exc:
        raise _fail(exc) from exc


@router.get("/compliance/queries/stock", dependencies=[require(Capability.RECORDS)])
def query_stock(
    sku: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    return _run(stock_movements, sku=sku, start_date=start_date, end_date=end_date, limit=limit, offset=offset)


@router.get("/compliance/queries/conditions", dependencies=[require(Capability.RECORDS)])
def query_conditions(limit: int = 25, offset: int = 0) -> dict[str, Any]:
    return _run(conditions, limit=limit, offset=offset)


@router.get("/compliance/queries/compliance", dependencies=[require(Capability.RECORDS)])
def query_compliance(limit: int = 25, offset: int = 0) -> dict[str, Any]:
    return _run(compliance_status, limit=limit, offset=offset)


@router.get("/compliance/queries/pos", dependencies=[require(Capability.RECORDS)])
def query_pos(limit: int = 25, offset: int = 0) -> dict[str, Any]:
    return _run(pos_gaps, limit=limit, offset=offset)


@router.get("/compliance/queries/lists", dependencies=[require(Capability.RECORDS)])
def query_lists(limit: int = 25, offset: int = 0) -> dict[str, Any]:
    return _run(list_versions, limit=limit, offset=offset)


@router.get("/compliance/queries/purchases", dependencies=[require(Capability.RECORDS)])
def query_purchases(limit: int = 25, offset: int = 0) -> dict[str, Any]:
    return _run(purchases, limit=limit, offset=offset)


@router.get("/compliance/queries/events", dependencies=[require(Capability.RECORDS)])
def query_events(action: str = "", actor: str = "", limit: int = 25, offset: int = 0) -> dict[str, Any]:
    return _run(audit_events, action=action, actor=actor, limit=limit, offset=offset)
