"""Flag a SKU 86'd, or clear the flag. The stock ledger still decides zero on hand."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import NotFound
from madira.domain.session import session_scope
from madira.models import ProductVariant, Sku, Venue
from madira.tenancy import active_venue_id, current_request


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(sku: Sku) -> dict:
    product = sku.variant.product if sku.variant is not None else None
    stamped = sku.eighty_sixed_at
    if stamped is not None and stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    return {
        "id": str(sku.id),
        "sku": sku.barcode,
        "name": "" if product is None else product.name,
        "eighty_sixed_at": None if stamped is None else stamped.astimezone(timezone.utc).isoformat(),
        "eighty_sixed": stamped is not None,
    }


def _load(session, venue_id: uuid.UUID, sku_id: uuid.UUID) -> tuple[Venue, Sku]:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    sku = session.scalar(
        select(Sku)
        .where(Sku.id == sku_id, Sku.venue_id == venue_id)
        .options(joinedload(Sku.variant).joinedload(ProductVariant.product))
    )
    if sku is None:
        raise NotFound("sku not found")
    return venue, sku


def _stamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def set_eighty_six(sku_id: uuid.UUID, flagged: bool) -> dict:
    venue_id = active_venue_id()
    ctx = current_request()
    actor_id = None if ctx is None else ctx.user_id
    with session_scope() as session:
        venue, sku = _load(session, venue_id, sku_id)
        before = {"eighty_sixed_at": _stamp(sku.eighty_sixed_at)}
        if flagged and sku.eighty_sixed_at is None:
            sku.eighty_sixed_at = _now()
            sku.eighty_sixed_by_user_id = actor_id
            record_audit_event(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                action="sku.eighty_six",
                entity_type="sku",
                entity_id=sku.id,
                before=before,
                after={"eighty_sixed_at": _stamp(sku.eighty_sixed_at), "sku": sku.barcode},
            )
            session.commit()
            sku = _load(session, venue_id, sku_id)[1]
        elif not flagged and sku.eighty_sixed_at is not None:
            sku.eighty_sixed_at = None
            sku.eighty_sixed_by_user_id = None
            record_audit_event(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                action="sku.eighty_six_clear",
                entity_type="sku",
                entity_id=sku.id,
                before=before,
                after={"eighty_sixed_at": None, "sku": sku.barcode},
            )
            session.commit()
            sku = _load(session, venue_id, sku_id)[1]
        return _public(sku)
