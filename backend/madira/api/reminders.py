"""In-app reminders. Acknowledgement does not send email."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from madira.domain.errors import NotFound
from madira.domain.reminders.service import ReminderError, decide, list_reminders, record_license
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter(tags=["reminders"])


class LicenseBody(BaseModel):
    label: str
    expires_on: date
    rule_code: str = "abc_license"
    document_id: uuid.UUID | None = None


class DecideBody(BaseModel):
    source_type: str
    source_id: uuid.UUID
    action: str
    snooze_days: int = 7


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, ReminderError):
        return HTTPException(exc.status, exc.message)
    return HTTPException(400, "Reminder request failed.")


@router.get("/reminders", dependencies=[require(Capability.RECORDS)])
def reminders() -> dict[str, Any]:
    try:
        return list_reminders(active_venue_id())
    except (NotFound, ReminderError) as exc:
        raise _fail(exc) from exc


@router.post("/licenses", dependencies=[require(Capability.REMINDERS_ACK)])
def add_license(body: LicenseBody) -> dict[str, Any]:
    try:
        return record_license(
            active_venue_id(),
            label=body.label,
            expires_on=body.expires_on,
            rule_code=body.rule_code,
            document_id=body.document_id,
        )
    except (NotFound, ReminderError) as exc:
        raise _fail(exc) from exc


@router.post("/reminders/decide", dependencies=[require(Capability.REMINDERS_ACK)])
def decide_reminder(body: DecideBody) -> dict[str, Any]:
    try:
        return decide(
            active_venue_id(),
            body.source_type,
            body.source_id,
            body.action,
            body.snooze_days,
        )
    except (NotFound, ReminderError) as exc:
        raise _fail(exc) from exc
