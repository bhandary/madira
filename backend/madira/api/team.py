from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from madira.domain.compliance.service import Rejected
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.team import certificates as certificate_service
from madira.domain.team import service as team_service
from madira.domain.training import manager as manager_service
from madira.rbac import Capability, require
from madira.storage import StorageError, upload_max_bytes

router = APIRouter()


class InviteBody(BaseModel):
    email: str
    role: str
    position: str | None = None


class MembershipBody(BaseModel):
    role: str
    position: str | None = None


class CertificatePatch(BaseModel):
    kind: str | None = None
    label: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None


def _raise(exc: Exception) -> None:
    if isinstance(exc, NotFound):
        raise HTTPException(404, exc.message) from exc
    if isinstance(exc, DraftFailed):
        raise HTTPException(exc.status, exc.message) from exc
    if isinstance(exc, Rejected):
        raise HTTPException(exc.status, exc.message) from exc
    if isinstance(exc, StorageError):
        raise HTTPException(exc.status, exc.message) from exc
    raise exc


async def _file(upload: UploadFile | None) -> tuple[str, str | None, bytes] | None:
    if upload is None:
        return None
    body = await upload.read(upload_max_bytes() + 1)
    if len(body) > upload_max_bytes():
        raise HTTPException(413, "This file is too large.")
    if not body:
        raise HTTPException(422, "The file is empty.")
    return upload.filename or "certificate", upload.content_type, body


@router.get("/team", dependencies=[require(Capability.TEAM_VIEW)])
def team_roster() -> dict[str, Any]:
    try:
        return team_service.roster()
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.get("/team/progress", dependencies=[require(Capability.TEAM_VIEW)])
def team_progress() -> dict[str, Any]:
    try:
        return manager_service.progress()
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/team/invites", dependencies=[require(Capability.TEAM_MANAGE)])
def team_invite(body: InviteBody) -> dict[str, Any]:
    try:
        return team_service.invite(body.email, body.role, body.position)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/team/invites/{invite_id}/revoke", dependencies=[require(Capability.TEAM_MANAGE)])
def team_revoke(invite_id: uuid.UUID) -> dict[str, Any]:
    try:
        return team_service.revoke_invite(invite_id)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.patch("/team/members/{user_id}", dependencies=[require(Capability.TEAM_MANAGE)])
def team_update_member(user_id: uuid.UUID, body: MembershipBody) -> dict[str, Any]:
    try:
        return team_service.update_membership(user_id, body.role, body.position)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.delete("/team/members/{user_id}", dependencies=[require(Capability.TEAM_MANAGE)])
def team_remove_member(user_id: uuid.UUID) -> dict[str, Any]:
    try:
        return team_service.remove_membership(user_id)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.get("/team/certificates", dependencies=[require(Capability.RECORDS)])
def team_certificates() -> dict[str, Any]:
    try:
        return certificate_service.list_certificates(only_self=False)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.get("/team/certificates/{certificate_id}", dependencies=[require(Capability.RECORDS)])
def team_certificate(certificate_id: uuid.UUID) -> dict[str, Any]:
    try:
        return certificate_service.get_certificate(certificate_id, only_self=False)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/team/certificates", dependencies=[require(Capability.TEAM_MANAGE)])
async def team_certificate_create(
    user_id: uuid.UUID = Form(...),
    kind: str = Form(...),
    label: str = Form(""),
    issued_on: date = Form(...),
    expires_on: date = Form(...),
    file: UploadFile | None = File(None),
) -> dict[str, Any]:
    try:
        payload = certificate_service.create_certificate(
            user_id,
            kind,
            label,
            issued_on,
            expires_on,
            file=await _file(file),
        )
    except (NotFound, DraftFailed, Rejected, StorageError) as exc:
        _raise(exc)
    return {"certificate": payload}


@router.patch("/team/certificates/{certificate_id}", dependencies=[require(Capability.TEAM_MANAGE)])
def team_certificate_update(certificate_id: uuid.UUID, body: CertificatePatch) -> dict[str, Any]:
    try:
        payload = certificate_service.update_certificate(
            certificate_id,
            kind=body.kind,
            label=body.label,
            issued_on=body.issued_on,
            expires_on=body.expires_on,
        )
    except (NotFound, DraftFailed, Rejected, StorageError) as exc:
        _raise(exc)
    return {"certificate": payload}


@router.post("/team/certificates/{certificate_id}/document", dependencies=[require(Capability.TEAM_MANAGE)])
async def team_certificate_document(
    certificate_id: uuid.UUID,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        payload = certificate_service.update_certificate(certificate_id, file=await _file(file))
    except (NotFound, DraftFailed, Rejected, StorageError) as exc:
        _raise(exc)
    return {"certificate": payload}


@router.delete("/team/certificates/{certificate_id}", dependencies=[require(Capability.TEAM_MANAGE)])
def team_certificate_delete(certificate_id: uuid.UUID) -> dict[str, Any]:
    try:
        return certificate_service.delete_certificate(certificate_id)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)
