"""Tasting sessions and samples. A decision opens a draft order, a draft list, or a pass."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from madira.agents.presenters.procurement import (
    with_followup,
    with_invite,
    with_sample,
    with_scheduled,
    with_session,
    with_tasting_list,
)
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.sourcing.service import draft_followup, get_followup
from madira.domain.tastings.invites import approve as approve_invite
from madira.domain.tastings.invites import desk as invite_desk
from madira.domain.tastings.invites import ics_text as invite_ics_text
from madira.domain.tastings.invites import propose as propose_invite
from madira.domain.tastings.invites import reject as reject_invite
from madira.domain.tastings.service import (
    TastingError,
    add_sample,
    create_session,
    delete_session,
    get_session,
    ics_text,
    list_sessions,
    remove_sample,
    scan_label,
    score_sample,
    set_decision,
    update_sample,
    update_session,
)
from madira.rbac import Capability, require
from madira.storage import StorageError
from madira.tenancy import active_venue_id

router = APIRouter()


class SessionBody(BaseModel):
    supplier_id: str | None = None
    supplier_name: str = ""
    title: str = ""
    starts_at: str = ""
    ends_at: str = ""
    when: str = ""
    location: str = "Maison Madira cellar"
    notes: str = "Draft hold — export .ics, do not send invites."
    status: str = "planned"


class SessionPatch(BaseModel):
    supplier_id: str | None = None
    title: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    when: str | None = None
    location: str | None = None
    notes: str | None = None
    status: str | None = None


class SampleBody(BaseModel):
    product_id: str | None = None
    sku_id: str | None = None
    supplier_id: str | None = None
    offer_id: str | None = None
    note: str = ""
    quoted_price_cents: int | None = None
    currency: str | None = None


class SamplePatch(BaseModel):
    product_id: str | None = None
    sku_id: str | None = None
    supplier_id: str | None = None
    offer_id: str | None = None
    note: str | None = None
    quoted_price_cents: int | None = None
    currency: str | None = None
    score: int | None = None
    decision: str | None = None


class ScoreBody(BaseModel):
    score: int | None = None
    note: str | None = None


class DecisionBody(BaseModel):
    decision: str
    reason: str = ""


class InviteSlotBody(BaseModel):
    starts_at: str
    ends_at: str = ""
    source: str = "entered"


class InviteProposeBody(BaseModel):
    slots: list[InviteSlotBody] | None = None
    staff_user_ids: list[str] | None = None


class InviteDecisionBody(BaseModel):
    comment: str = ""
    slot_index: int | None = None


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, DraftFailed):
        return HTTPException(exc.status, exc.message)
    if isinstance(exc, TastingError):
        return HTTPException(exc.status, exc.message)
    if isinstance(exc, StorageError):
        return HTTPException(exc.status, exc.message)
    return HTTPException(400, str(exc))


@router.get("/tastings", dependencies=[require(Capability.RECORDS)])
def tastings() -> dict[str, Any]:
    try:
        return with_tasting_list(list_sessions(active_venue_id()))
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc


@router.post("/tastings", dependencies=[require(Capability.TASTINGS_MANAGE)])
def tastings_create(body: SessionBody) -> dict[str, Any]:
    try:
        payload = create_session(
            active_venue_id(),
            supplier_name=body.supplier_name,
            supplier_id=body.supplier_id,
            title=body.title,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            when=body.when,
            location=body.location,
            notes=body.notes,
            status=body.status,
        )
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc
    return with_scheduled(payload)


@router.get("/tastings/{session_id}.ics", dependencies=[require(Capability.RECORDS)])
def tasting_ics(session_id: uuid.UUID) -> PlainTextResponse:
    try:
        body = ics_text(active_venue_id(), session_id)
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc
    return PlainTextResponse(body, media_type="text/calendar; charset=utf-8")


@router.get("/tastings/{session_id}", dependencies=[require(Capability.RECORDS)])
def tasting_get(session_id: uuid.UUID) -> dict[str, Any]:
    try:
        return with_session(get_session(active_venue_id(), session_id))
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc


@router.patch("/tastings/{session_id}", dependencies=[require(Capability.TASTINGS_MANAGE)])
def tasting_patch(session_id: uuid.UUID, body: SessionPatch) -> dict[str, Any]:
    try:
        return with_session(update_session(active_venue_id(), session_id, body.model_dump(exclude_unset=True)))
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc


@router.delete("/tastings/{session_id}", dependencies=[require(Capability.TASTINGS_MANAGE)])
def tasting_delete(session_id: uuid.UUID) -> dict[str, Any]:
    try:
        return delete_session(active_venue_id(), session_id)
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc


@router.post("/tastings/{session_id}/samples", dependencies=[require(Capability.TASTINGS_MANAGE)])
def samples_create(session_id: uuid.UUID, body: SampleBody) -> dict[str, Any]:
    try:
        return with_sample(
            add_sample(
                active_venue_id(),
                session_id,
                product_id=body.product_id,
                sku_id=body.sku_id,
                supplier_id=body.supplier_id,
                offer_id=body.offer_id,
                note=body.note,
                quoted_price_cents=body.quoted_price_cents,
                currency=body.currency,
            )
        )
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc


@router.post("/tastings/{session_id}/samples/label", dependencies=[require(Capability.TASTINGS_MANAGE)])
async def samples_label(session_id: uuid.UUID, file: UploadFile = File()) -> dict[str, Any]:
    data = await file.read()
    try:
        return with_sample(
            scan_label(
                active_venue_id(),
                session_id,
                filename=file.filename or "label",
                content_type=file.content_type,
                body=data,
            )
        )
    except (NotFound, TastingError, DraftFailed, StorageError) as exc:
        raise _fail(exc) from exc


@router.post("/tastings/{session_id}/samples/{sample_id}/label", dependencies=[require(Capability.TASTINGS_MANAGE)])
async def sample_label(session_id: uuid.UUID, sample_id: uuid.UUID, file: UploadFile = File()) -> dict[str, Any]:
    data = await file.read()
    try:
        return with_sample(
            scan_label(
                active_venue_id(),
                session_id,
                filename=file.filename or "label",
                content_type=file.content_type,
                body=data,
                sample_id=sample_id,
            )
        )
    except (NotFound, TastingError, DraftFailed, StorageError) as exc:
        raise _fail(exc) from exc


@router.patch("/tastings/{session_id}/samples/{sample_id}", dependencies=[require(Capability.TASTINGS_MANAGE)])
def samples_patch(session_id: uuid.UUID, sample_id: uuid.UUID, body: SamplePatch) -> dict[str, Any]:
    fields = body.model_dump(exclude_unset=True)
    decision = fields.pop("decision", None)
    try:
        payload = (
            update_sample(active_venue_id(), session_id, sample_id, fields)
            if fields
            else {"sample": next(row for row in get_session(active_venue_id(), session_id)["samples"] if row["id"] == str(sample_id))}
        )
        if decision is not None:
            payload = set_decision(active_venue_id(), session_id, sample_id, str(decision))
        return with_sample(payload if "sample" in payload else {"sample": payload})
    except (NotFound, TastingError, DraftFailed, StopIteration) as exc:
        if isinstance(exc, StopIteration):
            raise HTTPException(404, "sample not found") from exc
        raise _fail(exc) from exc


@router.delete("/tastings/{session_id}/samples/{sample_id}", dependencies=[require(Capability.TASTINGS_MANAGE)])
def samples_delete(session_id: uuid.UUID, sample_id: uuid.UUID) -> dict[str, Any]:
    try:
        return remove_sample(active_venue_id(), session_id, sample_id)
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc


@router.post("/tastings/{session_id}/samples/{sample_id}/score", dependencies=[require(Capability.TASTINGS_MANAGE)])
def samples_score(session_id: uuid.UUID, sample_id: uuid.UUID, body: ScoreBody) -> dict[str, Any]:
    try:
        owned = get_session(active_venue_id(), session_id)
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc
    if all(row["id"] != str(sample_id) for row in owned["samples"]):
        raise HTTPException(404, "sample not found")
    try:
        return with_sample(score_sample(active_venue_id(), sample_id, body.score, body.note))
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc


@router.post("/tastings/{session_id}/samples/{sample_id}/decision", dependencies=[require(Capability.TASTINGS_MANAGE)])
def samples_decision(session_id: uuid.UUID, sample_id: uuid.UUID, body: DecisionBody) -> dict[str, Any]:
    try:
        return with_sample(set_decision(active_venue_id(), session_id, sample_id, body.decision, body.reason))
    except (NotFound, TastingError, DraftFailed) as exc:
        raise _fail(exc) from exc


@router.get("/tastings/{session_id}/follow-up", dependencies=[require(Capability.RECORDS)])
def tasting_followup(session_id: uuid.UUID) -> dict[str, Any]:
    try:
        payload = get_followup(active_venue_id(), session_id)
        if payload.get("followup") is None:
            return payload
        return with_followup(payload)
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc


@router.post("/tastings/{session_id}/follow-up", dependencies=[require(Capability.TASTINGS_MANAGE)])
def tasting_followup_draft(session_id: uuid.UUID) -> dict[str, Any]:
    try:
        return with_followup(draft_followup(active_venue_id(), session_id))
    except (NotFound, TastingError, DraftFailed) as exc:
        raise _fail(exc) from exc


@router.get("/tastings/{session_id}/invite", dependencies=[require(Capability.RECORDS)])
def tasting_invite(session_id: uuid.UUID) -> dict[str, Any]:
    try:
        return invite_desk(active_venue_id(), session_id)
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc


@router.post("/tastings/{session_id}/invite", dependencies=[require(Capability.TASTINGS_MANAGE)])
def tasting_invite_propose(session_id: uuid.UUID, body: InviteProposeBody) -> dict[str, Any]:
    slots = None if body.slots is None else [slot.model_dump() for slot in body.slots]
    try:
        return with_invite(
            propose_invite(
                active_venue_id(),
                session_id,
                slots=slots,
                staff_user_ids=body.staff_user_ids,
            )
        )
    except (NotFound, TastingError, DraftFailed) as exc:
        raise _fail(exc) from exc


@router.post("/tastings/{session_id}/invite/approve", dependencies=[require(Capability.INVITE_DECIDE)])
def tasting_invite_approve(session_id: uuid.UUID, body: InviteDecisionBody) -> dict[str, Any]:
    try:
        return with_invite(
            approve_invite(active_venue_id(), session_id, slot_index=body.slot_index, comment=body.comment)
        )
    except (NotFound, TastingError, DraftFailed) as exc:
        raise _fail(exc) from exc


@router.post("/tastings/{session_id}/invite/reject", dependencies=[require(Capability.INVITE_DECIDE)])
def tasting_invite_reject(session_id: uuid.UUID, body: InviteDecisionBody) -> dict[str, Any]:
    try:
        return with_invite(reject_invite(active_venue_id(), session_id, comment=body.comment))
    except (NotFound, TastingError, DraftFailed) as exc:
        raise _fail(exc) from exc


@router.get("/tastings/{session_id}/invite.ics", dependencies=[require(Capability.RECORDS)])
def tasting_invite_ics(session_id: uuid.UUID) -> PlainTextResponse:
    try:
        body = invite_ics_text(active_venue_id(), session_id)
    except (NotFound, TastingError) as exc:
        raise _fail(exc) from exc
    return PlainTextResponse(body, media_type="text/calendar; charset=utf-8")
