"""List versions: snapshot, diff, Owner approval, PDF, and the guest QR list.

Sommelier and Owner can submit. Only the Owner approves, and that approval is
what publishes. The guest page reads the projection, which has names, guest
descriptions, and prices. Costs and margins stay off that page. Drafts have
no token.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from madira.domain.catalog.service import beverage_fields
from madira.domain.compliance.service import get_document, record_audit_event, store_document
from madira.domain.errors import NotFound
from madira.domain.inventory.qrcode import qr_png
from madira.domain.lists.pricing import blended
from madira.domain.procurement.pdf import render_text_pdf
from madira.domain.session import session_scope
from madira.models import (
    Approval,
    BeverageList,
    ListEntry,
    ListItem,
    ListVersion,
    PublicListSnapshot,
    Sku,
    TastingNote,
    Venue,
)
from madira.tenancy import OWNER, SOMMELIER, current_request

ENTITY = "list_version"
_SUBMIT_ROLES = {OWNER, SOMMELIER}


class ListVersionError(Exception):
    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def snapshot_draft(venue_id: uuid.UUID, list_id: uuid.UUID, actor=None) -> dict:
    """Copy the current list into the next numbered draft. Entries are not updated later."""

    with session_scope() as session:
        beverage_list = _owned_list(session, venue_id, list_id)
        version = _insert_snapshot(session, beverage_list)
        body = _payload(session, version, actor)
        session.commit()
        return body


def list_versions(venue_id: uuid.UUID, list_id: uuid.UUID, actor=None) -> dict:
    with session_scope() as session:
        beverage_list = _owned_list(session, venue_id, list_id)
        rows = session.scalars(
            select(ListVersion)
            .where(ListVersion.venue_id == venue_id, ListVersion.list_id == beverage_list.id)
            .order_by(ListVersion.number.desc(), ListVersion.id.desc())
        ).all()
        return {
            "list_id": str(beverage_list.id),
            "can_submit": _can_submit(session, beverage_list.id, actor),
            "versions": [_payload(session, row, actor) for row in rows],
        }


def get_version(venue_id: uuid.UUID, version_id: uuid.UUID, actor=None) -> dict:
    with session_scope() as session:
        return _payload(session, _owned_version(session, venue_id, version_id), actor)


def diff_version(venue_id: uuid.UUID, version_id: uuid.UUID) -> dict:
    with session_scope() as session:
        version = _owned_version(session, venue_id, version_id)
        return _diff(session, version)


def diff_live(venue_id: uuid.UUID, list_id: uuid.UUID) -> dict:
    """Compare the current list with the published version. This does not write a version."""

    with session_scope() as session:
        beverage_list = _owned_list(session, venue_id, list_id)
        current = _live_rows(session, beverage_list)
        published = _published(session, beverage_list.id)
        baseline = [] if published is None else _entry_rows(session, published.id)
        body = _changes(current, baseline)
        body["list_id"] = str(beverage_list.id)
        body["baseline_version_id"] = None if published is None else str(published.id)
        body["baseline_number"] = None if published is None else int(published.number)
        return body


def submit_version(venue_id: uuid.UUID, version_id: uuid.UUID, actor=None) -> dict:
    _require_submit(actor)
    with session_scope() as session:
        version = _owned_version(session, venue_id, version_id)
        body = _submit(session, version, actor)
        session.commit()
        return body


def submit_list(venue_id: uuid.UUID, list_id: uuid.UUID, actor=None) -> dict:
    """Snapshot the list and open an Owner approval. Publishing is a separate decision."""

    _require_submit(actor)
    with session_scope() as session:
        beverage_list = _owned_list(session, venue_id, list_id)
        waiting = _pending(session, beverage_list.id)
        if waiting is not None:
            return _payload(session, waiting, actor)
        version = _insert_snapshot(session, beverage_list)
        body = _submit(session, version, actor)
        session.commit()
        return body


def approve(venue_id: uuid.UUID, version_id: uuid.UUID, actor=None, comment: str | None = None) -> dict:
    """Owner approval publishes the version. The tool path never calls this."""

    _require_owner(actor)
    with session_scope() as session:
        version = _owned_version(session, venue_id, version_id)
        if version.status != "pending_approval":
            raise ListVersionError("Only a list waiting on the Owner can be approved.")
        approval = _approval(session, version)
        user_id, email, _role = _actor_bits(actor)
        now = datetime.now(timezone.utc)
        previous = version.status
        approval.decision = "approved"
        approval.decided_by_user_id = user_id
        approval.decided_at = now
        approval.comment = _comment(comment)
        venue = _venue(session, venue_id)
        _audit(
            session,
            venue,
            version,
            "list.approved",
            actor,
            before={"status": previous, "decision": "pending"},
            after={
                "status": "published",
                "decision": "approved",
                "number": int(version.number),
                "comment": approval.comment or "",
                "decided_by": email,
            },
        )
        body = _publish(session, venue, version, actor, now)
        session.commit()
        return body


def reject(venue_id: uuid.UUID, version_id: uuid.UUID, actor=None, comment: str | None = None) -> dict:
    _require_owner(actor)
    with session_scope() as session:
        version = _owned_version(session, venue_id, version_id)
        if version.status != "pending_approval":
            raise ListVersionError("Only a list waiting on the Owner can be rejected.")
        approval = _approval(session, version)
        user_id, email, _role = _actor_bits(actor)
        now = datetime.now(timezone.utc)
        previous = version.status
        approval.decision = "rejected"
        approval.decided_by_user_id = user_id
        approval.decided_at = now
        approval.comment = _comment(comment)
        version.status = "rejected"
        venue = _venue(session, venue_id)
        _audit(
            session,
            venue,
            version,
            "list.rejected",
            actor,
            before={"status": previous, "decision": "pending"},
            after={
                "status": "rejected",
                "decision": "rejected",
                "number": int(version.number),
                "comment": approval.comment or "",
                "decided_by": email,
            },
        )
        body = _payload(session, version, actor)
        session.commit()
        return body


def version_pdf(venue_id: uuid.UUID, version_id: uuid.UUID) -> tuple[str, str]:
    with session_scope() as session:
        version = _owned_version(session, venue_id, version_id)
        if version.document_id is None:
            raise NotFound("list pdf not found")
        document = get_document(session, venue_id, version.document_id)
        return document.filename, document.storage_key


def version_qr(venue_id: uuid.UUID, version_id: uuid.UUID) -> bytes:
    with session_scope() as session:
        version = _owned_version(session, venue_id, version_id)
        if version.status not in {"published", "superseded"} or not version.public_token or version.public_revoked_at is not None:
            raise NotFound("list qr not found")
        if _projection_revoked(session, version.public_token):
            raise NotFound("list qr not found")
        return qr_png(_public_url(version.public_token))


def revoke_public(venue_id: uuid.UUID, version_id: uuid.UUID, actor=None) -> dict:
    with session_scope() as session:
        version = _owned_version(session, venue_id, version_id)
        if not version.public_token:
            raise ListVersionError("This list version has no public page.")
        now = datetime.now(timezone.utc)
        previous = None if version.public_revoked_at is None else version.public_revoked_at.isoformat()
        if version.public_revoked_at is None:
            version.public_revoked_at = now
            projection = session.get(PublicListSnapshot, version.public_token)
            if projection is not None and projection.revoked_at is None:
                projection.revoked_at = now
            venue = _venue(session, venue_id)
            _audit(
                session,
                venue,
                version,
                "list.public_revoked",
                actor,
                before={"public_revoked_at": previous, "number": int(version.number)},
                after={"public_revoked_at": now.isoformat(), "number": int(version.number)},
            )
        body = _payload(session, version, actor)
        session.commit()
        return body


def public_list(token: str) -> dict:
    """Read the guest projection only. Drafts are not in this table."""

    key = (token or "").strip()
    if len(key) < 20:
        raise NotFound("list not found")
    with session_scope() as session:
        row = session.get(PublicListSnapshot, key)
        if row is None or row.revoked_at is not None:
            raise NotFound("list not found")
        rendered = _guest_rendered(row.rendered)
        return {
            "venue_name": row.venue_name,
            "published_at": _stamp(row.published_at),
            "list": rendered,
        }


def _submit(session: Session, version: ListVersion, actor) -> dict:
    if version.status != "draft":
        raise ListVersionError("Only a draft list can be submitted.")
    waiting = _pending(session, version.list_id)
    if waiting is not None and waiting.id != version.id:
        raise ListVersionError("This list is already waiting on the Owner.")
    user_id, email, _role = _actor_bits(actor)
    now = datetime.now(timezone.utc)
    approval = Approval(
        venue_id=version.venue_id,
        entity_type=ENTITY,
        entity_id=version.id,
        decision="pending",
        required_role="owner",
        created_at=now,
    )
    session.add(approval)
    session.flush()
    previous = version.status
    version.status = "pending_approval"
    version.approval_id = approval.id
    version.submitted_by_user_id = user_id
    venue = _venue(session, version.venue_id)
    _audit(
        session,
        venue,
        version,
        "list.submitted",
        actor,
        before={"status": previous, "number": int(version.number)},
        after={
            "status": "pending_approval",
            "number": int(version.number),
            "approval_id": str(approval.id),
            "submitted_by": email,
        },
    )
    return _payload(session, version, actor)


def _publish(session: Session, venue: Venue, version: ListVersion, actor, now: datetime) -> dict:
    user_id, email, _role = _actor_bits(actor)
    previous_published = _published(session, version.list_id)
    before_status = version.status
    if previous_published is not None and previous_published.id != version.id:
        previous_published.status = "superseded"
    entries = _entry_models(session, version.id)
    rendered = _render_guest(session, version, entries)
    pdf = _render_pdf(venue, version, rendered)
    if not pdf.startswith(b"%PDF-"):
        raise ListVersionError("The list PDF could not be rendered.", 500)
    filename = f"list-v{int(version.number)}.pdf"
    try:
        document = store_document(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            doc_type="other",
            filename=filename,
            content_type="application/pdf",
            body=pdf,
            linked_entity_type=ENTITY,
            linked_entity_id=version.id,
            uploaded_by_user_id=user_id,
            actor_email=email,
        )
    except Exception:
        raise
    token = _new_token(session)
    version.status = "published"
    version.published_at = now
    version.published_by_user_id = user_id
    version.document_id = document.id
    version.public_token = token
    version.public_revoked_at = None
    session.add(
        PublicListSnapshot(
            token=token,
            venue_name=venue.name,
            rendered=rendered,
            published_at=now,
            revoked_at=None,
        )
    )
    _audit(
        session,
        venue,
        version,
        "list.published",
        actor,
        before={"status": before_status, "public_token": None, "document_id": None, "number": int(version.number)},
        after={
            "status": "published",
            "number": int(version.number),
            "public_token": token,
            "document_id": str(document.id),
            "published_by": email,
        },
    )
    return _payload(session, version, actor)


def _insert_snapshot(session: Session, beverage_list: BeverageList) -> ListVersion:
    number = _next_number(session, beverage_list.id)
    version = ListVersion(
        venue_id=beverage_list.venue_id,
        list_id=beverage_list.id,
        number=number,
        status="draft",
        created_at=datetime.now(timezone.utc),
    )
    session.add(version)
    session.flush()
    notes = _guest_notes(session, beverage_list.venue_id)
    for row in _live_rows(session, beverage_list):
        detail = notes.get(row["product_id"]) or row["fallback_detail"]
        session.add(
            ListEntry(
                venue_id=beverage_list.venue_id,
                version_id=version.id,
                section_name=row["section"][:200],
                position=row["position"],
                sku_id=row["sku_id"],
                bottle_price_cents=row["bottle_price_cents"],
                glass_price_cents=row["glass_price_cents"],
                currency=row["currency"],
                display_name=row["name"][:200],
                display_detail=detail,
            )
        )
    session.flush()
    return version


def _live_rows(session: Session, beverage_list: BeverageList) -> list[dict]:
    items = session.scalars(
        select(ListItem)
        .where(ListItem.list_id == beverage_list.id, ListItem.venue_id == beverage_list.venue_id)
        .options(joinedload(ListItem.sku).joinedload(Sku.variant))
        .order_by(ListItem.position.asc(), ListItem.id.asc())
    ).unique().all()
    rows = []
    for item in items:
        fields = beverage_fields(item.sku)
        vintage = (fields.get("vintage") or "").strip()
        name = fields.get("name") or "Bottle"
        if vintage:
            name = f"{name} {vintage}"
        fallback = ", ".join(
            part
            for part in (fields.get("producer") or "", fields.get("region") or "", fields.get("style") or "")
            if part
        )
        rows.append(
            {
                "sku_id": item.sku_id,
                "product_id": item.sku.variant.product_id,
                "section": (item.section or "List").strip() or "List",
                "position": int(item.position or 0),
                "bottle_price_cents": max(0, int(item.bottle_price or 0)),
                "glass_price_cents": max(0, int(item.pour_price or 0)),
                "currency": item.currency or beverage_list.currency or "USD",
                "name": name.strip() or "Bottle",
                "fallback_detail": fallback,
            }
        )
    return rows


def _guest_notes(session: Session, venue_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = session.scalars(
        select(TastingNote)
        .where(TastingNote.venue_id == venue_id, TastingNote.status == "approved")
        .order_by(TastingNote.approved_at.desc(), TastingNote.id.desc())
    ).all()
    found: dict[uuid.UUID, str] = {}
    for row in rows:
        text = (row.guest_description or "").strip()
        if text and row.product_id not in found:
            found[row.product_id] = text
    return found


def _payload(session: Session, version: ListVersion, actor) -> dict:
    beverage_list = session.get(BeverageList, version.list_id)
    approval = session.get(Approval, version.approval_id) if version.approval_id else None
    entries = _entry_models(session, version.id)
    role = _role(actor)
    token = version.public_token if version.public_token and version.public_revoked_at is None else None
    if token and _projection_revoked(session, token):
        token = None
    return {
        "id": str(version.id),
        "list_id": str(version.list_id),
        "list_name": "" if beverage_list is None else beverage_list.name,
        "number": int(version.number),
        "status": version.status,
        "currency": "" if beverage_list is None else beverage_list.currency,
        "approval_id": None if version.approval_id is None else str(version.approval_id),
        "approval": None
        if approval is None
        else {
            "id": str(approval.id),
            "decision": approval.decision,
            "required_role": approval.required_role,
            "comment": approval.comment or "",
            "decided_at": _stamp(approval.decided_at),
        },
        "submitted_by_user_id": None if version.submitted_by_user_id is None else str(version.submitted_by_user_id),
        "published_by_user_id": None if version.published_by_user_id is None else str(version.published_by_user_id),
        "published_at": _stamp(version.published_at),
        "document_id": None if version.document_id is None else str(version.document_id),
        "public_token": token,
        "public_path": None if token is None else f"/l/{token}",
        "public_revoked_at": _stamp(version.public_revoked_at),
        "created_at": _stamp(version.created_at),
        "can_submit": _can_submit(session, version.list_id, actor),
        "can_decide": role == OWNER and version.status == "pending_approval",
        "entries": [_entry_public(row) for row in entries],
        "sections": _section_margins(session, entries),
        "diff": _diff(session, version),
    }


def _entry_public(row: ListEntry) -> dict:
    return {
        "id": str(row.id),
        "sku_id": str(row.sku_id),
        "section": row.section_name,
        "position": int(row.position or 0),
        "display_name": row.display_name,
        "display_detail": row.display_detail or "",
        "bottle_price_cents": int(row.bottle_price_cents or 0),
        "glass_price_cents": int(row.glass_price_cents or 0),
        "currency": row.currency,
    }


def _section_margins(session: Session, entries: list[ListEntry]) -> list[dict]:
    grouped: list[dict] = []
    index: dict[str, dict] = {}
    costs: dict[uuid.UUID, int] = {}
    if entries:
        sku_ids = [row.sku_id for row in entries]
        skus = session.scalars(select(Sku).where(Sku.id.in_(sku_ids))).all()
        costs = {sku.id: int(sku.cost or 0) for sku in skus}
    for row in entries:
        name = row.section_name or "List"
        bucket = index.get(name)
        if bucket is None:
            bucket = {"name": name, "item_count": 0, "costs": [], "prices": []}
            index[name] = bucket
            grouped.append(bucket)
        bucket["item_count"] += 1
        bucket["costs"].append(costs.get(row.sku_id, 0))
        price = int(row.bottle_price_cents or 0) or int(row.glass_price_cents or 0)
        bucket["prices"].append(price)
    sections = []
    for bucket in grouped:
        econ = blended(bucket["costs"], bucket["prices"])
        sections.append(
            {
                "name": bucket["name"],
                "item_count": bucket["item_count"],
                "margin_pct": econ["margin_pct"],
                "beverage_cost_pct": econ["beverage_cost_pct"],
            }
        )
    return sections


def _diff(session: Session, version: ListVersion) -> dict:
    current = _entry_rows(session, version.id)
    baseline_version = _baseline(session, version)
    baseline = [] if baseline_version is None else _entry_rows(session, baseline_version.id)
    body = _changes(current, baseline)
    body["version_id"] = str(version.id)
    body["baseline_version_id"] = None if baseline_version is None else str(baseline_version.id)
    body["baseline_number"] = None if baseline_version is None else int(baseline_version.number)
    return body


def _changes(current: list[dict], baseline: list[dict]) -> dict:
    before = {row["sku_id"]: row for row in baseline}
    after = {row["sku_id"]: row for row in current}
    added = []
    removed = []
    repriced = []
    moved = []
    for sku_id, row in after.items():
        prior = before.get(sku_id)
        if prior is None:
            added.append(_change_row(row))
            continue
        if prior["bottle_price_cents"] != row["bottle_price_cents"] or prior["glass_price_cents"] != row["glass_price_cents"]:
            changed = _change_row(row)
            changed["previous_bottle_price_cents"] = prior["bottle_price_cents"]
            changed["previous_glass_price_cents"] = prior["glass_price_cents"]
            repriced.append(changed)
        if prior["section"] != row["section"] or prior["position"] != row["position"]:
            changed = _change_row(row)
            changed["previous_section"] = prior["section"]
            changed["previous_position"] = prior["position"]
            moved.append(changed)
    for sku_id, row in before.items():
        if sku_id not in after:
            removed.append(_change_row(row))
    return {"added": added, "removed": removed, "repriced": repriced, "moved": moved}


def _change_row(row: dict) -> dict:
    return {
        "sku_id": str(row["sku_id"]),
        "name": row["name"],
        "section": row["section"],
        "position": int(row["position"]),
        "bottle_price_cents": int(row["bottle_price_cents"]),
        "glass_price_cents": int(row["glass_price_cents"]),
        "currency": row["currency"],
    }


def _entry_rows(session: Session, version_id: uuid.UUID) -> list[dict]:
    rows = _entry_models(session, version_id)
    return [
        {
            "sku_id": row.sku_id,
            "name": row.display_name,
            "section": row.section_name,
            "position": int(row.position or 0),
            "bottle_price_cents": int(row.bottle_price_cents or 0),
            "glass_price_cents": int(row.glass_price_cents or 0),
            "currency": row.currency,
        }
        for row in rows
    ]


def _entry_models(session: Session, version_id: uuid.UUID) -> list[ListEntry]:
    return list(
        session.scalars(
            select(ListEntry)
            .where(ListEntry.version_id == version_id)
            .order_by(ListEntry.position.asc(), ListEntry.id.asc())
        ).all()
    )


def _render_guest(session: Session, version: ListVersion, entries: list[ListEntry]) -> dict:
    beverage_list = session.get(BeverageList, version.list_id)
    sections: list[dict] = []
    index: dict[str, dict] = {}
    for row in entries:
        name = row.section_name or "List"
        bucket = index.get(name)
        if bucket is None:
            bucket = {"name": name, "items": []}
            index[name] = bucket
            sections.append(bucket)
        bucket["items"].append(
            {
                "name": row.display_name,
                "detail": row.display_detail or "",
                "bottle_price_cents": int(row.bottle_price_cents or 0),
                "glass_price_cents": int(row.glass_price_cents or 0),
                "currency": row.currency,
            }
        )
    return {
        "list_name": "" if beverage_list is None else beverage_list.name,
        "number": int(version.number),
        "currency": "" if beverage_list is None else (beverage_list.currency or "USD"),
        "sections": sections,
    }


def _guest_rendered(value) -> dict:
    """Drop anything that is not a guest field, even if a row was written by hand."""

    raw = value if isinstance(value, dict) else {}
    sections = []
    for section in raw.get("sections") or []:
        if not isinstance(section, dict):
            continue
        items = []
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "name": str(item.get("name") or ""),
                    "detail": str(item.get("detail") or ""),
                    "bottle_price_cents": int(item.get("bottle_price_cents") or 0),
                    "glass_price_cents": int(item.get("glass_price_cents") or 0),
                    "currency": str(item.get("currency") or raw.get("currency") or "USD"),
                }
            )
        sections.append({"name": str(section.get("name") or "List"), "items": items})
    return {
        "list_name": str(raw.get("list_name") or ""),
        "number": int(raw.get("number") or 0),
        "currency": str(raw.get("currency") or "USD"),
        "sections": sections,
    }


def _render_pdf(venue: Venue, version: ListVersion, rendered: dict) -> bytes:
    lines = [
        f"{venue.name}",
        f"{rendered.get('list_name') or 'List'}  version {int(version.number)}",
        "",
    ]
    for section in rendered.get("sections") or []:
        lines.append(str(section.get("name") or "List"))
        for item in section.get("items") or []:
            lines.append(str(item.get("name") or ""))
            detail = str(item.get("detail") or "").strip()
            if detail:
                lines.append(detail[:180])
            prices = []
            glass = int(item.get("glass_price_cents") or 0)
            bottle = int(item.get("bottle_price_cents") or 0)
            if glass:
                prices.append(f"Glass {_money(glass)}")
            if bottle:
                prices.append(f"Bottle {_money(bottle)}")
            if prices:
                lines.append("  ".join(prices))
            lines.append("")
        lines.append("")
    return render_text_pdf(lines)


def _money(cents: int) -> str:
    amount = abs(int(cents))
    return f"${amount // 100}.{amount % 100:02d}"


def _public_url(token: str) -> str:
    from madira.config import FRONTEND_ORIGIN

    return f"{FRONTEND_ORIGIN.rstrip('/')}/l/{token}"


def _new_token(session: Session) -> str:
    for _ in range(5):
        token = secrets.token_urlsafe(32)
        if session.get(PublicListSnapshot, token) is None and session.scalar(
            select(ListVersion.id).where(ListVersion.public_token == token)
        ) is None:
            return token
    raise ListVersionError("A public token could not be created.", 500)


def _baseline(session: Session, version: ListVersion) -> ListVersion | None:
    if version.status == "published":
        return session.scalar(
            select(ListVersion)
            .where(
                ListVersion.list_id == version.list_id,
                ListVersion.venue_id == version.venue_id,
                ListVersion.status == "superseded",
                ListVersion.number < version.number,
            )
            .order_by(ListVersion.number.desc())
        )
    return _published(session, version.list_id)


def _published(session: Session, list_id: uuid.UUID) -> ListVersion | None:
    return session.scalar(
        select(ListVersion)
        .where(ListVersion.list_id == list_id, ListVersion.status == "published")
        .order_by(ListVersion.number.desc())
    )


def _pending(session: Session, list_id: uuid.UUID) -> ListVersion | None:
    return session.scalar(
        select(ListVersion)
        .where(ListVersion.list_id == list_id, ListVersion.status == "pending_approval")
        .order_by(ListVersion.number.desc())
    )


def _next_number(session: Session, list_id: uuid.UUID) -> int:
    current = session.scalar(
        select(ListVersion.number).where(ListVersion.list_id == list_id).order_by(ListVersion.number.desc()).limit(1)
    )
    return 1 if current is None else int(current) + 1


def _projection_revoked(session: Session, token: str) -> bool:
    row = session.get(PublicListSnapshot, token)
    return row is None or row.revoked_at is not None


def _can_submit(session: Session, list_id: uuid.UUID, actor) -> bool:
    return _role(actor) in _SUBMIT_ROLES and _pending(session, list_id) is None


def _approval(session: Session, version: ListVersion) -> Approval:
    if version.approval_id is None:
        raise ListVersionError("This list has no approval.")
    approval = session.get(Approval, version.approval_id)
    if approval is None or approval.venue_id != version.venue_id or approval.entity_id != version.id:
        raise ListVersionError("This list has no approval.")
    if approval.decision != "pending":
        raise ListVersionError("This approval is already decided.")
    return approval


def _owned_list(session: Session, venue_id: uuid.UUID, list_id: uuid.UUID) -> BeverageList:
    row = session.get(BeverageList, list_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("list not found")
    return row


def _owned_version(session: Session, venue_id: uuid.UUID, version_id: uuid.UUID) -> ListVersion:
    row = session.get(ListVersion, version_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("list version not found")
    return row


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _require_submit(actor) -> None:
    if _role(actor) not in _SUBMIT_ROLES:
        raise ListVersionError("Only the Owner or Sommelier can submit a list.", 403)


def _require_owner(actor) -> None:
    if _role(actor) != OWNER:
        raise ListVersionError("Only the Owner can approve or reject a list.", 403)


def _role(actor) -> str:
    role = getattr(actor, "role", None) if actor is not None else None
    if not role:
        ctx = current_request()
        role = None if ctx is None else ctx.role
    return role or ""


def _actor_bits(actor) -> tuple[uuid.UUID | None, str, str]:
    user_id = getattr(actor, "user_id", None) if actor is not None else None
    email = getattr(actor, "email", None) if actor is not None else None
    role = getattr(actor, "role", None) if actor is not None else None
    ctx = current_request()
    if ctx is not None:
        if user_id is None:
            user_id = ctx.user_id
        if not email:
            email = ctx.email
        if not role:
            role = ctx.role
    return user_id, email or "", role or ""


def _audit(session: Session, venue: Venue, version: ListVersion, action: str, actor, before=None, after=None) -> None:
    user_id, email, _role = _actor_bits(actor)
    record_audit_event(
        session,
        org_id=venue.organization_id,
        venue_id=venue.id,
        action=action,
        entity_type=ENTITY,
        entity_id=version.id,
        before=before,
        after=after,
        actor_user_id=user_id,
        actor_email=email,
    )


def _comment(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:500]


def _stamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
