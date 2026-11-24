from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from madira.agents.presenters.compliance import with_audit
from madira.domain.compliance.service import (
    Rejected,
    document_public,
    get_document_bytes,
    get_retention_policy,
    list_audit_events,
    list_documents,
    store_document,
    update_retention_policy,
    verify_audit_chain,
)
from madira.domain.errors import NotFound
from madira.domain.session import session_scope
from madira.rbac import Capability, require
from madira.storage import StorageError, upload_max_bytes
from madira.tenancy import OWNER, RequestContext, active_venue_id, current_organization_id

router = APIRouter()


class RetentionBody(BaseModel):
    document_retention_years: int = Field(ge=1, le=25)


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, Rejected):
        return HTTPException(exc.status, exc.message)
    if isinstance(exc, StorageError):
        return HTTPException(exc.status, exc.message)
    raise exc


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _optional_id(value: str) -> uuid.UUID | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return uuid.UUID(text)
    except ValueError as exc:
        raise Rejected("linked_entity_id must be a UUID.", 400) from exc


@router.get("/compliance/audit-events", dependencies=[require(Capability.RECORDS)])
def audit_events(
    entity_type: str | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    venue_id = active_venue_id()
    with session_scope() as session:
        events = list_audit_events(
            session,
            venue_id,
            entity_type=_blank(entity_type),
            action=_blank(action),
            since=since,
            until=until,
            limit=limit,
        )
        chain = verify_audit_chain(session, venue_id)
    return with_audit(events, chain)


@router.get("/compliance/audit-events/verify", dependencies=[require(Capability.RECORDS)])
def audit_verify() -> dict:
    with session_scope() as session:
        return verify_audit_chain(session, active_venue_id())


@router.get("/compliance/documents", dependencies=[require(Capability.RECORDS)])
def documents() -> dict:
    with session_scope() as session:
        return {"documents": list_documents(session, active_venue_id())}


@router.post("/compliance/documents", dependencies=[require(Capability.RECORDS_WRITE)])
async def documents_upload(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    linked_entity_type: str = Form(""),
    linked_entity_id: str = Form(""),
) -> dict:
    body = await file.read(upload_max_bytes() + 1)
    try:
        link_id = _optional_id(linked_entity_id)
        with session_scope() as session:
            row = store_document(
                session,
                org_id=current_organization_id(),
                venue_id=active_venue_id(),
                doc_type=doc_type,
                filename=file.filename or "",
                content_type=file.content_type,
                body=body,
                linked_entity_type=linked_entity_type,
                linked_entity_id=link_id,
            )
            payload = document_public(row)
            session.commit()
    except (NotFound, Rejected, StorageError) as exc:
        raise _fail(exc) from exc
    return {"document": payload}


@router.get("/compliance/documents/{document_id}/download", dependencies=[require(Capability.RECORDS)])
def documents_download(document_id: uuid.UUID) -> Response:
    try:
        with session_scope() as session:
            row, payload = get_document_bytes(session, active_venue_id(), document_id)
            filename = row.filename
            media = row.content_type or "application/octet-stream"
    except (NotFound, StorageError) as exc:
        raise _fail(exc) from exc
    quoted = filename.replace("\\", "").replace('"', "")
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{quoted}"'},
    )


@router.get("/compliance/retention")
def retention_get(ctx: RequestContext = require(Capability.RECORDS)) -> dict:
    with session_scope() as session:
        years = get_retention_policy(session, ctx.organization_id)
    return {"document_retention_years": years, "can_edit": ctx.role == OWNER}


@router.patch("/compliance/retention")
def retention_patch(body: RetentionBody, ctx: RequestContext = require(Capability.SETTINGS)) -> dict:
    try:
        with session_scope() as session:
            years = update_retention_policy(
                session,
                ctx.organization_id,
                body.document_retention_years,
                venue_id=ctx.venue_id,
            )
            session.commit()
    except (NotFound, Rejected) as exc:
        raise _fail(exc) from exc
    return {"document_retention_years": years, "can_edit": True}
