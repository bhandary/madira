"""Staff certificates. The reminder window is 30 days, including past expiry."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.compliance.service import record_audit_event, store_document
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.session import session_scope
from madira.domain.training.access import actor
from madira.models import CERTIFICATE_KINDS, Certificate, Document, Membership, User, Venue
from madira.rbac import MATRIX, Capability
from madira.tenancy import RequestContext, active_venue_id

REMINDER_DAYS = 30

_DEFAULT_LABELS = {
    "responsible_service": "Responsible service",
    "food_handler": "Food handler",
}


def venue_today(session: Session, venue_id: uuid.UUID) -> date:
    venue = session.get(Venue, venue_id)
    name = venue.timezone if venue is not None and venue.timezone else "America/Los_Angeles"
    try:
        zone = ZoneInfo(name)
    except Exception:
        zone = ZoneInfo("America/Los_Angeles")
    return datetime.now(zone).date()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _manage(ctx: RequestContext) -> None:
    if ctx.role not in MATRIX[Capability.TEAM_MANAGE]:
        raise DraftFailed("This role cannot do that.", 403)


def _kind(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if cleaned not in CERTIFICATE_KINDS:
        raise DraftFailed("Certificate kind must be responsible_service, food_handler, or other.", 422)
    return cleaned


def _label(kind: str, value: str) -> str:
    cleaned = " ".join((value or "").split())
    if not cleaned:
        cleaned = _DEFAULT_LABELS.get(kind, "")
    if not cleaned:
        raise DraftFailed("A label is required.", 422)
    if len(cleaned) > 200:
        raise DraftFailed("Label is too long.", 422)
    return cleaned


def _dates(issued_on: date, expires_on: date) -> tuple[date, date]:
    if not isinstance(issued_on, date) or not isinstance(expires_on, date):
        raise DraftFailed("Issued and expiry dates are required.", 422)
    if expires_on < issued_on:
        raise DraftFailed("The expiry date is before the issued date.", 422)
    return issued_on, expires_on


def _status(expires_on: date, today: date) -> dict:
    days_left = (expires_on - today).days
    expired = expires_on < today
    expiring = today <= expires_on <= today + timedelta(days=REMINDER_DAYS)
    if expired:
        gap_type = "certificate_expired"
        status_label = f"Expired {expires_on.isoformat()}"
    elif expiring:
        gap_type = "certificate_expiring"
        status_label = f"Expires {expires_on.isoformat()}"
    else:
        gap_type = ""
        status_label = f"Valid until {expires_on.isoformat()}"
    return {
        "days_left": days_left,
        "expired": expired,
        "expiring": expiring,
        "due": expired or expiring,
        "gap_type": gap_type,
        "status_label": status_label,
    }


def _names(session: Session, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not user_ids:
        return {}
    return {row.id: row for row in session.scalars(select(User).where(User.id.in_(user_ids))).all()}


def _public(row: Certificate, today: date, user: User | None, document: Document | None) -> dict:
    status = _status(row.expires_on, today)
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "name": "" if user is None else (user.name or ""),
        "kind": row.kind,
        "label": row.label,
        "issued_on": row.issued_on.isoformat(),
        "expires_on": row.expires_on.isoformat(),
        "document_id": None if row.document_id is None else str(row.document_id),
        "document_filename": "" if document is None else document.filename,
        "created_by_user_id": str(row.created_by_user_id),
        "created_at": _iso(row.created_at),
        **status,
    }


def _gap(row: Certificate, today: date, user: User | None) -> dict:
    status = _status(row.expires_on, today)
    return {
        "gap_type": status["gap_type"],
        "id": str(row.id),
        "user_id": str(row.user_id),
        "name": "" if user is None else (user.name or ""),
        "kind": row.kind,
        "label": row.label,
        "issued_on": row.issued_on.isoformat(),
        "expires_on": row.expires_on.isoformat(),
        "days_left": status["days_left"],
        "status_label": status["status_label"],
    }


def due_certificates(session: Session, venue_id: uuid.UUID) -> list[dict]:
    """Certificates already expired or expiring within 30 days. Read only."""

    today = venue_today(session, venue_id)
    horizon = today + timedelta(days=REMINDER_DAYS)
    rows = session.scalars(
        select(Certificate)
        .where(Certificate.venue_id == venue_id, Certificate.expires_on <= horizon)
        .order_by(Certificate.expires_on.asc(), Certificate.id.asc())
    ).all()
    users = _names(session, {row.user_id for row in rows})
    return [_gap(row, today, users.get(row.user_id)) for row in rows]


def _member(session: Session, venue_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    row = session.scalar(
        select(Membership).where(Membership.venue_id == venue_id, Membership.user_id == user_id)
    )
    if row is None:
        raise NotFound("member not found")
    return row


def _load(session: Session, venue_id: uuid.UUID, certificate_id: uuid.UUID) -> Certificate:
    row = session.get(Certificate, certificate_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("certificate not found")
    return row


def _documents(session: Session, rows: list[Certificate]) -> dict[uuid.UUID, Document]:
    ids = [row.document_id for row in rows if row.document_id is not None]
    if not ids:
        return {}
    return {row.id: row for row in session.scalars(select(Document).where(Document.id.in_(ids))).all()}


def list_certificates(*, only_self: bool) -> dict:
    ctx = actor()
    if not only_self and ctx.role not in MATRIX[Capability.RECORDS]:
        raise DraftFailed("This role cannot do that.", 403)
    if only_self and ctx.role not in MATRIX[Capability.TRAINING_LEARN]:
        raise DraftFailed("This role cannot do that.", 403)
    with session_scope() as session:
        venue_id = active_venue_id()
        today = venue_today(session, venue_id)
        query = select(Certificate).where(Certificate.venue_id == venue_id)
        if only_self:
            query = query.where(Certificate.user_id == ctx.user_id)
        rows = session.scalars(query.order_by(Certificate.expires_on.asc(), Certificate.id.asc())).all()
        users = _names(session, {row.user_id for row in rows})
        documents = _documents(session, list(rows))
        return {
            "certificates": [
                _public(row, today, users.get(row.user_id), documents.get(row.document_id) if row.document_id else None)
                for row in rows
            ]
        }


def get_certificate(certificate_id: uuid.UUID, *, only_self: bool) -> dict:
    ctx = actor()
    if not only_self and ctx.role not in MATRIX[Capability.RECORDS]:
        raise DraftFailed("This role cannot do that.", 403)
    if only_self and ctx.role not in MATRIX[Capability.TRAINING_LEARN]:
        raise DraftFailed("This role cannot do that.", 403)
    with session_scope() as session:
        venue_id = active_venue_id()
        row = _load(session, venue_id, certificate_id)
        if only_self and row.user_id != ctx.user_id:
            raise NotFound("certificate not found")
        today = venue_today(session, venue_id)
        user = session.get(User, row.user_id)
        document = session.get(Document, row.document_id) if row.document_id else None
        return _public(row, today, user, document)


def _store_file(
    session: Session,
    venue: Venue,
    certificate_id: uuid.UUID,
    file: tuple[str, str | None, bytes],
) -> Document:
    filename, content_type, body = file
    if not body:
        raise DraftFailed("The file is empty.", 422)
    ctx = actor()
    return store_document(
        session,
        org_id=venue.organization_id,
        venue_id=venue.id,
        doc_type="certificate",
        filename=filename or "certificate",
        content_type=content_type,
        body=body,
        linked_entity_type="certificate",
        linked_entity_id=certificate_id,
        uploaded_by_user_id=ctx.user_id,
        actor_email=ctx.email,
    )


def create_certificate(
    user_id: uuid.UUID,
    kind: str,
    label: str,
    issued_on: date,
    expires_on: date,
    file: tuple[str, str | None, bytes] | None = None,
) -> dict:
    ctx = actor()
    _manage(ctx)
    assigned = _kind(kind)
    title = _label(assigned, label)
    issued, expires = _dates(issued_on, expires_on)
    with session_scope() as session:
        venue_id = active_venue_id()
        venue = session.get(Venue, venue_id)
        if venue is None:
            raise NotFound("venue not found")
        _member(session, venue_id, user_id)
        row = Certificate(
            venue_id=venue_id,
            user_id=user_id,
            kind=assigned,
            label=title,
            issued_on=issued,
            expires_on=expires,
            document_id=None,
            created_by_user_id=ctx.user_id,
            created_at=_now(),
        )
        session.add(row)
        session.flush()
        document = None
        if file is not None:
            document = _store_file(session, venue, row.id, file)
            row.document_id = document.id
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="certificate.create",
            entity_type="certificate",
            entity_id=row.id,
            after={
                "user_id": str(user_id),
                "kind": assigned,
                "label": title,
                "issued_on": issued.isoformat(),
                "expires_on": expires.isoformat(),
                "document_id": None if row.document_id is None else str(row.document_id),
            },
        )
        today = venue_today(session, venue_id)
        user = session.get(User, user_id)
        payload = _public(row, today, user, document)
        session.commit()
        return payload


def update_certificate(
    certificate_id: uuid.UUID,
    *,
    kind: str | None = None,
    label: str | None = None,
    issued_on: date | None = None,
    expires_on: date | None = None,
    file: tuple[str, str | None, bytes] | None = None,
) -> dict:
    ctx = actor()
    _manage(ctx)
    with session_scope() as session:
        venue_id = active_venue_id()
        venue = session.get(Venue, venue_id)
        if venue is None:
            raise NotFound("venue not found")
        row = _load(session, venue_id, certificate_id)
        before = {
            "kind": row.kind,
            "label": row.label,
            "issued_on": row.issued_on.isoformat(),
            "expires_on": row.expires_on.isoformat(),
            "document_id": None if row.document_id is None else str(row.document_id),
        }
        assigned = row.kind if kind is None else _kind(kind)
        title = row.label if label is None else _label(assigned, label)
        issued = row.issued_on if issued_on is None else issued_on
        expires = row.expires_on if expires_on is None else expires_on
        issued, expires = _dates(issued, expires)
        row.kind = assigned
        row.label = title
        row.issued_on = issued
        row.expires_on = expires
        document = session.get(Document, row.document_id) if row.document_id else None
        if file is not None:
            document = _store_file(session, venue, row.id, file)
            row.document_id = document.id
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="certificate.update",
            entity_type="certificate",
            entity_id=row.id,
            before=before,
            after={
                "kind": row.kind,
                "label": row.label,
                "issued_on": row.issued_on.isoformat(),
                "expires_on": row.expires_on.isoformat(),
                "document_id": None if row.document_id is None else str(row.document_id),
            },
        )
        today = venue_today(session, venue_id)
        user = session.get(User, row.user_id)
        payload = _public(row, today, user, document)
        session.commit()
        return payload


def delete_certificate(certificate_id: uuid.UUID) -> dict:
    ctx = actor()
    _manage(ctx)
    with session_scope() as session:
        venue_id = active_venue_id()
        venue = session.get(Venue, venue_id)
        if venue is None:
            raise NotFound("venue not found")
        row = _load(session, venue_id, certificate_id)
        before = {
            "user_id": str(row.user_id),
            "kind": row.kind,
            "label": row.label,
            "issued_on": row.issued_on.isoformat(),
            "expires_on": row.expires_on.isoformat(),
            "document_id": None if row.document_id is None else str(row.document_id),
        }
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="certificate.delete",
            entity_type="certificate",
            entity_id=row.id,
            before=before,
            after=None,
        )
        session.delete(row)
        session.commit()
        return {"deleted": True, "id": str(certificate_id)}
