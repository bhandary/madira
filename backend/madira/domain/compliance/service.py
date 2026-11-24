"""Append-only audit ledger, document vault, and retention.

``record_audit_event`` is the only write for ``audit_events``. There is no
update or delete. ``event_hash`` is SHA-256 over the canonical JSON of the
event fields, including ``prev_hash``. The first event in a venue uses
``GENESIS``. ``verify_audit_chain`` recomputes that hash and walks ``seq``,
so a row edit or a gap fails the check.

Vault files go through the disk storage layer under ``{venue_id}/vault/``.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.errors import NotFound
from madira.models import DOC_TYPES, AuditEvent, Document, Organization, Venue
from madira.storage import StorageError, get_storage, normalize_content_type
from madira.tenancy import current_request

GENESIS = "GENESIS"
DEFAULT_RETENTION_YEARS = 7
MIN_RETENTION_YEARS = 1
MAX_RETENTION_YEARS = 25

ACTION_BASELINE = "compliance.baseline"
ACTION_DOCUMENT = "document.store"
ACTION_RETENTION = "retention.update"
ACTION_INVENTORY = "inventory.adjust"

DEMO_LICENSE_FILENAME = "maison-madira-liquor-license.txt"
DEMO_LICENSE_BODY = (
    "Maison Madira\nOn-premises liquor license\nDemo record. Not a legal document.\n"
).encode("utf-8")

ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/webp",
        "text/csv",
        "text/plain",
    }
)
_TEXT_TYPES = frozenset({"text/csv", "text/plain"})
_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".csv": "text/csv",
    ".txt": "text/plain",
}
_HASH_FIELDS = (
    "id",
    "org_id",
    "venue_id",
    "seq",
    "actor_user_id",
    "actor_email",
    "action",
    "entity_type",
    "entity_id",
    "before_json",
    "after_json",
    "prev_hash",
    "created_at",
)


class Rejected(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    # Microseconds are kept so a stored timestamptz hashes back to the same text.
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _load_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _json_ready(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return _stamp(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    raise Rejected("Audit values must be JSON.")


def _material(row: AuditEvent) -> dict:
    created = row.created_at
    return {
        "id": str(row.id),
        "org_id": str(row.org_id),
        "venue_id": str(row.venue_id),
        "seq": int(row.seq),
        "actor_user_id": None if row.actor_user_id is None else str(row.actor_user_id),
        "actor_email": row.actor_email or "",
        "action": row.action,
        "entity_type": row.entity_type or "",
        "entity_id": None if row.entity_id is None else str(row.entity_id),
        "before_json": _json_ready(_load_json(row.before_json)),
        "after_json": _json_ready(_load_json(row.after_json)),
        "prev_hash": row.prev_hash,
        "created_at": _stamp(created),
    }


def event_digest(row: AuditEvent) -> str:
    body = {key: _material(row)[key] for key in _HASH_FIELDS}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _actors(venue_id: uuid.UUID, actor_user_id: uuid.UUID | None, actor_email: str | None) -> tuple[uuid.UUID | None, str]:
    if actor_user_id is None and actor_email is None:
        ctx = current_request()
        if ctx is not None and ctx.venue_id == venue_id:
            actor_user_id = ctx.user_id
            actor_email = ctx.email
    return actor_user_id, (actor_email or "")


def _next_link(session: Session, venue_id: uuid.UUID) -> tuple[int, str]:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        locked = session.scalar(select(Venue.id).where(Venue.id == venue_id).with_for_update())
        if locked is None:
            raise NotFound("venue not found")
    last = session.scalar(
        select(AuditEvent).where(AuditEvent.venue_id == venue_id).order_by(AuditEvent.seq.desc()).limit(1)
    )
    if last is None:
        return 1, GENESIS
    return int(last.seq) + 1, last.event_hash


def record_audit_event(
    session: Session,
    *,
    org_id: uuid.UUID,
    venue_id: uuid.UUID,
    action: str,
    entity_type: str = "",
    entity_id: uuid.UUID | None = None,
    before: dict | list | None = None,
    after: dict | list | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_email: str | None = None,
) -> AuditEvent:
    """Append one hash-chained event in the caller's transaction."""

    label = (action or "").strip()
    if not label or len(label) > 80:
        raise Rejected("Audit action is required.")
    kind = (entity_type or "").strip()
    if len(kind) > 80:
        raise Rejected("Audit entity type is too long.")
    actor_id, email = _actors(venue_id, actor_user_id, actor_email)
    if len(email) > 320:
        email = email[:320]
    seq, prev_hash = _next_link(session, venue_id)
    row = AuditEvent(
        id=uuid.uuid4(),
        org_id=org_id,
        venue_id=venue_id,
        seq=seq,
        actor_user_id=actor_id,
        actor_email=email,
        action=label,
        entity_type=kind,
        entity_id=entity_id,
        before_json=_json_ready(before) if before is not None else None,
        after_json=_json_ready(after) if after is not None else None,
        prev_hash=prev_hash,
        event_hash="",
        created_at=datetime.now(timezone.utc),
    )
    row.event_hash = event_digest(row)
    session.add(row)
    session.flush()
    return row


def _broken(checked: int, row: AuditEvent, reason: str) -> dict:
    return {
        "valid": False,
        "checked_count": checked,
        "head_hash": None,
        "broken_event_id": str(row.id),
        "reason": reason,
    }


def verify_audit_chain(session: Session, venue_id: uuid.UUID) -> dict:
    rows = session.scalars(
        select(AuditEvent).where(AuditEvent.venue_id == venue_id).order_by(AuditEvent.seq.asc(), AuditEvent.id.asc())
    ).all()
    if not rows:
        return {
            "valid": True,
            "checked_count": 0,
            "head_hash": None,
            "broken_event_id": None,
            "reason": None,
        }
    previous = None
    expected = 1
    for index, row in enumerate(rows, start=1):
        if int(row.seq) != expected:
            reason = "sequence does not start at 1" if expected == 1 else "sequence gap"
            return _broken(index, row, reason)
        expected_prev = GENESIS if expected == 1 else previous
        if row.prev_hash != expected_prev:
            return _broken(index, row, "prev_hash does not match the previous event")
        if row.event_hash != event_digest(row):
            return _broken(index, row, "hash mismatch")
        previous = row.event_hash
        expected += 1
    return {
        "valid": True,
        "checked_count": len(rows),
        "head_hash": previous,
        "broken_event_id": None,
        "reason": None,
    }


def _summary(before, after) -> str:
    before = _load_json(before)
    after = _load_json(after)
    if isinstance(before, dict) and isinstance(after, dict):
        parts = []
        for key in list(dict.fromkeys([*before.keys(), *after.keys()])):
            if key in before and key in after and before[key] != after[key]:
                parts.append(f"{key} {before[key]} → {after[key]}")
            elif key in after and key not in before:
                parts.append(f"{key} {after[key]}")
        if parts:
            return "; ".join(parts)
    if isinstance(after, dict) and after:
        parts = [f"{key} {after[key]}" for key in after]
        return "; ".join(parts)
    if after is not None:
        return json.dumps(_json_ready(after), sort_keys=True, ensure_ascii=False)[:180]
    return ""


def event_public(row: AuditEvent) -> dict:
    return {
        "id": str(row.id),
        "seq": int(row.seq),
        "actor_email": row.actor_email or "",
        "action": row.action,
        "entity_type": row.entity_type or "",
        "entity_id": None if row.entity_id is None else str(row.entity_id),
        "before_json": _load_json(row.before_json),
        "after_json": _load_json(row.after_json),
        "prev_hash": row.prev_hash,
        "event_hash": row.event_hash,
        "created_at": _stamp(row.created_at),
        "summary": _summary(row.before_json, row.after_json),
    }


def list_audit_events(
    session: Session,
    venue_id: uuid.UUID,
    entity_type: str | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
) -> list[dict]:
    stmt = select(AuditEvent).where(AuditEvent.venue_id == venue_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if since is not None:
        stmt = stmt.where(AuditEvent.created_at >= since)
    if until is not None:
        stmt = stmt.where(AuditEvent.created_at <= until)
    bounded = min(max(int(limit or 100), 1), 500)
    stmt = stmt.order_by(AuditEvent.seq.desc()).limit(bounded)
    return [event_public(row) for row in session.scalars(stmt).all()]


def _filename(value: str) -> str:
    name = Path(value or "").name.replace("\x00", "").strip()
    name = re.sub(r'[\r\n"]+', "", name)
    if not name or name in {".", ".."}:
        return "upload"
    return name[:200]


def _doc_type(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if cleaned not in DOC_TYPES:
        raise Rejected(
            "doc_type must be invoice, po_pdf, purchase_order, delivery_note, license, certificate, or other."
        )
    return cleaned


def _optional_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise Rejected("linked_entity_id must be a UUID.", 400) from exc


def _media(content_type: str | None, filename: str) -> str:
    media = normalize_content_type(content_type)
    if media in ALLOWED_CONTENT_TYPES:
        return media
    if media in {"", "application/octet-stream"}:
        guessed = _EXTENSIONS.get(Path(filename).suffix.lower())
        if guessed in ALLOWED_CONTENT_TYPES:
            return guessed
    raise Rejected("This file type is not accepted.", 415)


def document_public(row: Document) -> dict:
    return {
        "id": str(row.id),
        "doc_type": row.doc_type,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": int(row.size_bytes),
        "sha256": row.sha256,
        "linked_entity_type": row.linked_entity_type or "",
        "linked_entity_id": None if row.linked_entity_id is None else str(row.linked_entity_id),
        "uploaded_by_user_id": None if row.uploaded_by_user_id is None else str(row.uploaded_by_user_id),
        "created_at": _stamp(row.created_at),
    }


def store_document(
    session: Session,
    *,
    org_id: uuid.UUID,
    venue_id: uuid.UUID,
    doc_type: str,
    filename: str,
    content_type: str | None,
    body: bytes,
    linked_entity_type: str = "",
    linked_entity_id: str | uuid.UUID | None = None,
    uploaded_by_user_id: uuid.UUID | None = None,
    actor_email: str | None = None,
) -> Document:
    kind = _doc_type(doc_type)
    safe_name = _filename(filename)
    media = _media(content_type, safe_name)
    link_type = (linked_entity_type or "").strip()[:80]
    link_id = _optional_uuid(linked_entity_id)
    actor_id, email = _actors(venue_id, uploaded_by_user_id, actor_email)
    storage = get_storage()
    stored = storage.put(
        venue_id,
        kind="vault",
        body=body,
        content_type=media,
        filename=safe_name,
        allowed_types=ALLOWED_CONTENT_TYPES,
        binary=media not in _TEXT_TYPES,
    )
    if not stored.key.startswith(f"{venue_id}/vault/"):
        storage.delete(stored.key)
        raise StorageError("This file could not be stored.", 400)
    digest = hashlib.sha256(body).hexdigest()
    row = Document(
        org_id=org_id,
        venue_id=venue_id,
        doc_type=kind,
        filename=safe_name,
        content_type=stored.content_type or media,
        size_bytes=len(body),
        storage_key=stored.key,
        sha256=digest,
        linked_entity_type=link_type,
        linked_entity_id=link_id,
        uploaded_by_user_id=actor_id,
    )
    session.add(row)
    try:
        session.flush()
        record_audit_event(
            session,
            org_id=org_id,
            venue_id=venue_id,
            action=ACTION_DOCUMENT,
            entity_type="document",
            entity_id=row.id,
            after={
                "doc_type": kind,
                "filename": safe_name,
                "sha256": digest,
                "size_bytes": len(body),
            },
            actor_user_id=actor_id,
            actor_email=email,
        )
    except Exception:
        storage.delete(stored.key)
        raise
    return row


def list_documents(session: Session, venue_id: uuid.UUID) -> list[dict]:
    rows = session.scalars(
        select(Document).where(Document.venue_id == venue_id).order_by(Document.created_at.desc(), Document.id.desc())
    ).all()
    return [document_public(row) for row in rows]


def get_document(session: Session, venue_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    row = session.get(Document, document_id)
    if row is None or row.venue_id != venue_id or row.org_id is None:
        raise NotFound("document not found")
    if not (row.storage_key or "").startswith(f"{venue_id}/vault/"):
        raise NotFound("document not found")
    return row


def get_document_bytes(session: Session, venue_id: uuid.UUID, document_id: uuid.UUID) -> tuple[Document, bytes]:
    row = get_document(session, venue_id, document_id)
    try:
        payload = get_storage().read(row.storage_key)
    except StorageError as exc:
        raise NotFound("document not found") from exc
    return row, payload


def get_retention_policy(session: Session, org_id: uuid.UUID) -> int:
    org = session.get(Organization, org_id)
    if org is None:
        raise NotFound("organization not found")
    years = org.document_retention_years
    if years is None:
        return DEFAULT_RETENTION_YEARS
    return int(years)


def update_retention_policy(session: Session, org_id: uuid.UUID, years: int, *, venue_id: uuid.UUID) -> int:
    if isinstance(years, bool) or not isinstance(years, int) or years < MIN_RETENTION_YEARS or years > MAX_RETENTION_YEARS:
        raise Rejected("Retention must be a whole number of years from 1 to 25.")
    org = session.get(Organization, org_id)
    if org is None:
        raise NotFound("organization not found")
    venue = session.get(Venue, venue_id)
    if venue is None or venue.organization_id != org_id:
        raise NotFound("venue not found")
    previous = int(org.document_retention_years or DEFAULT_RETENTION_YEARS)
    if previous == years:
        return years
    org.document_retention_years = years
    record_audit_event(
        session,
        org_id=org_id,
        venue_id=venue_id,
        action=ACTION_RETENTION,
        entity_type="organization",
        entity_id=org.id,
        before={"document_retention_years": previous},
        after={"document_retention_years": years},
    )
    session.flush()
    return years


def ensure_demo_records(session: Session, ctx) -> None:
    """One baseline ledger event and one liquor-license file for the demo venue.

    Safe to call on every seed. It does not touch SKUs, menus, or lists.
    """

    existing_events = session.scalar(
        select(AuditEvent.id).where(AuditEvent.venue_id == ctx.venue_id).limit(1)
    )
    if existing_events is None:
        record_audit_event(
            session,
            org_id=ctx.organization_id,
            venue_id=ctx.venue_id,
            action=ACTION_BASELINE,
            entity_type="organization",
            entity_id=ctx.organization_id,
            after={"note": "Demo compliance ledger opened."},
            actor_user_id=ctx.user_id,
            actor_email=ctx.email,
        )
    existing_doc = session.scalar(
        select(Document.id).where(
            Document.venue_id == ctx.venue_id,
            Document.filename == DEMO_LICENSE_FILENAME,
            Document.doc_type == "license",
        )
    )
    if existing_doc is None:
        store_document(
            session,
            org_id=ctx.organization_id,
            venue_id=ctx.venue_id,
            doc_type="license",
            filename=DEMO_LICENSE_FILENAME,
            content_type="text/plain",
            body=DEMO_LICENSE_BODY,
            uploaded_by_user_id=ctx.user_id,
            actor_email=ctx.email,
        )
