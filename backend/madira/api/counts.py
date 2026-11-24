"""Count sessions and par proposals."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from madira.agents.presenters.inventory import with_count_report
from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import Rejected
from madira.domain.inventory import counts, par
from madira.rbac import Capability, require
from madira.tenancy import current_request

router = APIRouter()


class StartBody(BaseModel):
    location_id: uuid.UUID
    notes: str = ""


class SyncEntry(BaseModel):
    client_mutation_id: str
    device_id: str = "web"
    sku: str | None = None
    barcode: str | None = None
    bin_qr: str | None = None
    bin_id: uuid.UUID | None = None
    counted_quantity: Decimal
    counted_at: str | None = None
    notes: str | None = None

    @field_validator("counted_quantity", mode="before")
    @classmethod
    def parse_quantity(cls, value):
        if isinstance(value, bool) or value is None:
            raise ValueError("counted_quantity must be a number")
        try:
            qty = Decimal(str(value))
        except Exception as exc:
            raise ValueError("counted_quantity must be a number") from exc
        if qty < 0:
            raise ValueError("counted_quantity cannot be negative")
        return qty


class SyncBody(BaseModel):
    entries: list[SyncEntry] = Field(default_factory=list)


class ResolveBody(BaseModel):
    resolved_quantity: Decimal
    notes: str | None = None

    @field_validator("resolved_quantity", mode="before")
    @classmethod
    def parse_quantity(cls, value):
        if isinstance(value, bool) or value is None:
            raise ValueError("resolved_quantity must be a number")
        try:
            qty = Decimal(str(value))
        except Exception as exc:
            raise ValueError("resolved_quantity must be a number") from exc
        if qty < 0:
            raise ValueError("resolved_quantity cannot be negative")
        return qty


class GenerateBody(BaseModel):
    lead_time_days: int = 7
    safety_days: int = 4
    proposed_by: str = "cellar-manager"


def _actor():
    return current_request()


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, Rejected):
        return HTTPException(exc.status, exc.message)
    raise exc


def _call(fn):
    try:
        return fn()
    except (NotFound, Rejected) as exc:
        raise _fail(exc) from exc


@router.get("/inventory/counts", dependencies=[require(Capability.INVENTORY_READ)])
def inventory_counts() -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    return _call(lambda: counts.list_count_sessions(active_venue_id()))


@router.post("/inventory/counts", dependencies=[require(Capability.COUNT)])
def inventory_count_start(body: StartBody) -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    return _call(lambda: counts.start_count_session(active_venue_id(), body.location_id, _actor(), body.notes))


@router.get("/inventory/counts/{session_id}", dependencies=[require(Capability.INVENTORY_READ)])
def inventory_count_get(session_id: str) -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    def read():
        return with_count_report(counts.get_count_report(active_venue_id(), session_id))

    return _call(read)


@router.post("/inventory/counts/{session_id}/sync", dependencies=[require(Capability.COUNT)])
def inventory_count_sync(session_id: str, body: SyncBody) -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    entries = [entry.model_dump(mode="json") for entry in body.entries]
    return _call(lambda: counts.sync_count_lines(active_venue_id(), session_id, entries, _actor()))


@router.post("/inventory/counts/{session_id}/submit", dependencies=[require(Capability.COUNT)])
def inventory_count_submit(session_id: str) -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    def submit():
        return with_count_report(counts.submit_count_session(active_venue_id(), session_id, _actor()))

    return _call(submit)


@router.post("/inventory/counts/{session_id}/conflicts/{sku}/resolve", dependencies=[require(Capability.COUNT)])
def inventory_count_resolve(session_id: str, sku: str, body: ResolveBody) -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    def resolve():
        return with_count_report(
            counts.resolve_count_conflict(
                active_venue_id(),
                session_id,
                sku,
                body.resolved_quantity,
                _actor(),
                body.notes,
            )
        )

    return _call(resolve)


@router.post("/inventory/counts/{session_id}/approve", dependencies=[require(Capability.COUNT)])
def inventory_count_approve(session_id: str) -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    def approve():
        return with_count_report(counts.approve_count_session(active_venue_id(), session_id, _actor()))

    return _call(approve)


@router.get("/inventory/par-proposals", dependencies=[require(Capability.INVENTORY_READ)])
def inventory_par_list(status: str | None = None) -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    return _call(lambda: par.list_par_proposals(active_venue_id(), status))


@router.post("/inventory/par-proposals/generate", dependencies=[require(Capability.COUNT)])
def inventory_par_generate(body: GenerateBody | None = None) -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    payload = body or GenerateBody()
    return _call(
        lambda: par.propose_par_changes(
            active_venue_id(),
            lead_time_days=payload.lead_time_days,
            safety_days=payload.safety_days,
            proposed_by=payload.proposed_by,
        )
    )


@router.post("/inventory/par-proposals/{proposal_id}/accept", dependencies=[require(Capability.COUNT)])
def inventory_par_accept(proposal_id: str) -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    return _call(lambda: {"proposal": par.decide_par_proposal(active_venue_id(), proposal_id, "accept", _actor())})


@router.post("/inventory/par-proposals/{proposal_id}/reject", dependencies=[require(Capability.COUNT)])
def inventory_par_reject(proposal_id: str) -> dict[str, Any]:
    from madira.tenancy import active_venue_id

    return _call(lambda: {"proposal": par.decide_par_proposal(active_venue_id(), proposal_id, "reject", _actor())})
