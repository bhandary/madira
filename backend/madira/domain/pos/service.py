"""Connect a register, map variations, and post POS sales onto the stock ledger."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from madira.crypto import decrypt_secret, encrypt_secret
from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import Rejected, as_qty, post_movement, public_qty
from madira.domain.pos.adapter import CatalogVariation, PosAdapter, PosError, SaleLine
from madira.domain.pos.demo import DemoPosDriver
from madira.domain.pos.square import SquarePosDriver
from madira.domain.session import session_scope
from madira.models import Location, PosConnection, PosCredential, PosItemMapping, PosSale, PosSyncRun, Sku, Venue
from madira.tenancy import current_request, demo_posture

ACTION_CONNECTED = "pos.connected"
ACTION_MAPPING = "pos.mapping_saved"
ACTION_MAPPING_REMOVED = "pos.mapping_removed"
ACTION_SYNCED = "pos.synced"
ACTION_SYNC_FAILED = "pos.sync_failed"
STALE_AFTER = timedelta(hours=24)
_SECRET_MARKERS = ("ciphertext", "access_token", "authorization", "bearer ")


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _actor(venue_id: uuid.UUID) -> tuple[uuid.UUID | None, str]:
    ctx = current_request()
    if ctx is not None and ctx.venue_id == venue_id:
        return ctx.user_id, ctx.email or ""
    return None, ""


def _stamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise PosError("A POS timestamp was not a date.", 422) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _last4(token: str) -> str:
    cleaned = token.strip()
    if len(cleaned) < 4:
        return ""
    return cleaned[-4:]


def _connection(session: Session, venue_id: uuid.UUID) -> PosConnection | None:
    rows = list(session.scalars(select(PosConnection).where(PosConnection.venue_id == venue_id)).all())
    if not rows:
        return None
    preferred = "demo" if demo_posture() else "square"
    matched = [row for row in rows if row.provider == preferred]
    pool = matched or rows
    active = [row for row in pool if row.status == "active"]
    chosen = active or pool

    def _created(row: PosConnection) -> datetime:
        stamp = row.created_at or datetime.min.replace(tzinfo=timezone.utc)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp

    chosen.sort(key=_created, reverse=True)
    return chosen[0]


def _public_connection(session: Session, row: PosConnection | None) -> dict:
    if row is None:
        return {
            "connected": False,
            "provider": "",
            "status": "",
            "location_id": "",
            "location_name": "",
            "key_last4": "",
            "masked": "",
            "last_synced_at": None,
            "watermark": "",
            "demo_mode": demo_posture(),
        }
    last4 = ""
    if row.credential_id is not None:
        credential = session.get(PosCredential, row.credential_id)
        if credential is not None and credential.venue_id == row.venue_id:
            last4 = credential.key_last4 or ""
    return {
        "connected": row.status == "active",
        "provider": row.provider,
        "status": row.status,
        "location_id": row.location_id or "",
        "location_name": row.location_name or "",
        "key_last4": last4,
        "masked": f"····{last4}" if last4 else "",
        "last_synced_at": _stamp(row.last_synced_at),
        "watermark": row.watermark or "",
        "demo_mode": demo_posture(),
    }


def _variation_public(item: CatalogVariation) -> dict:
    return {
        "item_id": item.item_id,
        "variation_id": item.variation_id,
        "name": item.name,
        "variation_name": item.variation_name,
        "sku_hint": item.sku,
    }


def _mapping_public(session: Session, row: PosItemMapping) -> dict:
    sku = session.get(Sku, row.sku_id)
    return {
        "id": str(row.id),
        "provider": row.provider,
        "item_id": row.item_id,
        "variation_id": row.variation_id,
        "sku_id": str(row.sku_id),
        "sku": "" if sku is None else sku.barcode,
        "pour_ml": row.pour_ml,
        "units_per_sale": public_qty(row.units_per_sale),
    }


def _run_public(row: PosSyncRun) -> dict:
    counts = row.counts or {}
    return {
        "id": str(row.id),
        "status": row.status,
        "started_at": _stamp(row.started_at),
        "finished_at": _stamp(row.finished_at),
        "posted": int(counts.get("posted") or 0),
        "skipped": int(counts.get("skipped") or 0),
        "unmapped_count": len(counts.get("unmapped") or []),
        "error": row.error or "",
    }


def _token(session: Session, row: PosConnection) -> str:
    if row.credential_id is None:
        return ""
    credential = session.get(PosCredential, row.credential_id)
    if credential is None or credential.venue_id != row.venue_id:
        raise PosError("Square needs an access token.", 422)
    try:
        return decrypt_secret(credential.ciphertext)
    except RuntimeError as exc:
        raise PosError("Square credential cannot be read.", 422) from exc


def open_driver(session: Session, row: PosConnection, client=None) -> PosAdapter:
    if row.provider == "demo":
        if not demo_posture():
            raise PosError("Demo POS is only available in demo mode.", 422)
        posted = set(
            session.scalars(
                select(PosSale.external_line_id).where(
                    PosSale.venue_id == row.venue_id,
                    PosSale.provider == "demo",
                )
            ).all()
        )
        return DemoPosDriver(posted)
    if row.provider == "square":
        token = _token(session, row)
        if not token:
            raise PosError("Square needs an access token.", 422)
        return SquarePosDriver(token, client=client)
    raise PosError("Unknown POS provider.", 422)


def _store_token(session: Session, venue_id: uuid.UUID, token: str) -> PosCredential:
    credential = PosCredential(
        venue_id=venue_id,
        ciphertext=encrypt_secret(token),
        key_last4=_last4(token),
    )
    session.add(credential)
    session.flush()
    return credential


def _audit(session: Session, venue: Venue, action: str, entity_id: uuid.UUID, before: dict, after: dict) -> None:
    actor_id, email = _actor(venue.id)
    record_audit_event(
        session,
        org_id=venue.organization_id,
        venue_id=venue.id,
        action=action,
        entity_type="pos_connection",
        entity_id=entity_id,
        before=before,
        after=after,
        actor_user_id=actor_id,
        actor_email=email,
    )


def status(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        return _public_connection(session, _connection(session, venue_id))


def connect_demo(venue_id: uuid.UUID) -> dict:
    if not demo_posture():
        raise PosError("Demo POS is only available in demo mode.", 422)
    with session_scope() as session:
        try:
            venue = _venue(session, venue_id)
            actor_id, _email = _actor(venue_id)
            row = session.scalar(
                select(PosConnection).where(PosConnection.venue_id == venue_id, PosConnection.provider == "demo")
            )
            before = _public_connection(session, row)
            if row is None:
                row = PosConnection(venue_id=venue_id, provider="demo", status="active")
                session.add(row)
            row.status = "active"
            row.location_id = "demo-bar"
            row.location_name = "Main Bar"
            row.actor_user_id = actor_id
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            _audit(
                session,
                venue,
                ACTION_CONNECTED,
                row.id,
                before,
                {"provider": "demo", "status": "active", "location_id": "demo-bar"},
            )
            session.commit()
            return _public_connection(session, row)
        except Exception:
            session.rollback()
            raise


def connect_square(venue_id: uuid.UUID, access_token: str, location_id: str = "", client=None) -> dict:
    if demo_posture():
        raise PosError("Demo mode connects the demo register. Square is for live mode.", 422)
    token = (access_token or "").strip()
    if not token:
        raise PosError("Square needs an access token.", 422)
    driver = SquarePosDriver(token, client=client)
    locations = driver.list_locations()
    chosen = None
    if location_id:
        chosen = next((row for row in locations if row.location_id == location_id), None)
        if chosen is None:
            raise PosError("That Square location is not on this account.", 422)
    with session_scope() as session:
        try:
            venue = _venue(session, venue_id)
            actor_id, _email = _actor(venue_id)
            row = session.scalar(
                select(PosConnection).where(PosConnection.venue_id == venue_id, PosConnection.provider == "square")
            )
            before = {"provider": "square", "status": "" if row is None else row.status}
            credential = _store_token(session, venue_id, token)
            if row is None:
                row = PosConnection(venue_id=venue_id, provider="square", status="pending")
                session.add(row)
            row.credential_id = credential.id
            row.actor_user_id = actor_id
            row.updated_at = datetime.now(timezone.utc)
            if chosen is None:
                row.status = "pending"
                row.location_id = ""
                row.location_name = ""
            else:
                row.status = "active"
                row.location_id = chosen.location_id
                row.location_name = chosen.name
            session.flush()
            _audit(
                session,
                venue,
                ACTION_CONNECTED,
                row.id,
                before,
                {
                    "provider": "square",
                    "status": row.status,
                    "location_id": row.location_id,
                    "key_last4": credential.key_last4,
                },
            )
            session.commit()
            body = _public_connection(session, row)
            body["locations"] = [{"location_id": item.location_id, "name": item.name} for item in locations]
            return body
        except Exception:
            session.rollback()
            raise


def set_location(venue_id: uuid.UUID, location_id: str, client=None) -> dict:
    place = (location_id or "").strip()
    if not place:
        raise PosError("Choose a location.", 422)
    with session_scope() as session:
        try:
            venue = _venue(session, venue_id)
            row = _connection(session, venue_id)
            if row is None or row.provider != "square":
                raise PosError("Connect Square before choosing a location.", 422)
            driver = open_driver(session, row, client=client)
            match = next((item for item in driver.list_locations() if item.location_id == place), None)
            if match is None:
                raise PosError("That Square location is not on this account.", 422)
            before = {"location_id": row.location_id, "status": row.status}
            row.location_id = match.location_id
            row.location_name = match.name
            row.status = "active"
            row.updated_at = datetime.now(timezone.utc)
            _audit(
                session,
                venue,
                ACTION_CONNECTED,
                row.id,
                before,
                {"location_id": match.location_id, "status": "active"},
            )
            session.commit()
            return _public_connection(session, row)
        except Exception:
            session.rollback()
            raise


def catalog(venue_id: uuid.UUID, client=None) -> dict:
    with session_scope() as session:
        row = _connection(session, venue_id)
        if row is None:
            raise PosError("Connect a register before listing items.", 422)
        driver = open_driver(session, row, client=client)
        items = [_variation_public(item) for item in driver.list_variations()]
        items.sort(key=lambda item: (item["name"], item["variation_id"]))
        return {"items": items}


def list_mappings(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        rows = session.scalars(
            select(PosItemMapping)
            .where(PosItemMapping.venue_id == venue_id)
            .order_by(PosItemMapping.variation_id.asc())
        ).all()
        return {"mappings": [_mapping_public(session, row) for row in rows]}


def save_mapping(
    venue_id: uuid.UUID,
    *,
    variation_id: str,
    item_id: str,
    sku: str,
    pour_ml: int | None,
    units_per_sale,
) -> dict:
    variation = (variation_id or "").strip()
    if not variation:
        raise PosError("Choose a POS item.", 422)
    units = as_qty(units_per_sale)
    if units <= 0:
        raise Rejected("units per sale must be positive")
    if pour_ml is not None:
        try:
            pour = int(pour_ml)
        except (TypeError, ValueError) as exc:
            raise Rejected("pour size must be a whole number of millilitres") from exc
        if pour <= 0:
            raise Rejected("pour size must be a whole number of millilitres")
    else:
        pour = None
    with session_scope() as session:
        try:
            venue = _venue(session, venue_id)
            connection = _connection(session, venue_id)
            if connection is None:
                raise PosError("Connect a register before mapping items.", 422)
            code = (sku or "").strip().upper()
            stock = session.scalar(
                select(Sku).where(Sku.venue_id == venue_id, func.upper(Sku.barcode) == code)
            )
            if stock is None:
                raise NotFound(f"unknown sku {sku}")
            row = session.scalar(
                select(PosItemMapping).where(
                    PosItemMapping.venue_id == venue_id,
                    PosItemMapping.provider == connection.provider,
                    PosItemMapping.variation_id == variation,
                )
            )
            before = None if row is None else _mapping_public(session, row)
            if row is None:
                row = PosItemMapping(
                    venue_id=venue_id,
                    provider=connection.provider,
                    variation_id=variation,
                    sku_id=stock.id,
                    units_per_sale=units,
                )
                session.add(row)
            row.item_id = (item_id or "")[:128]
            row.sku_id = stock.id
            row.pour_ml = pour
            row.units_per_sale = units
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            after = _mapping_public(session, row)
            actor_id, email = _actor(venue_id)
            record_audit_event(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                action=ACTION_MAPPING,
                entity_type="pos_item_mapping",
                entity_id=row.id,
                before=before,
                after=after,
                actor_user_id=actor_id,
                actor_email=email,
            )
            session.commit()
            return {"mapping": after}
        except Exception:
            session.rollback()
            raise


def remove_mapping(venue_id: uuid.UUID, mapping_id: uuid.UUID) -> dict:
    with session_scope() as session:
        try:
            venue = _venue(session, venue_id)
            row = session.get(PosItemMapping, mapping_id)
            if row is None or row.venue_id != venue_id:
                raise NotFound("mapping not found")
            before = _mapping_public(session, row)
            actor_id, email = _actor(venue_id)
            record_audit_event(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                action=ACTION_MAPPING_REMOVED,
                entity_type="pos_item_mapping",
                entity_id=row.id,
                before=before,
                after=None,
                actor_user_id=actor_id,
                actor_email=email,
            )
            session.delete(row)
            session.commit()
            return {"removed": str(mapping_id)}
        except Exception:
            session.rollback()
            raise


def list_runs(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        rows = session.scalars(
            select(PosSyncRun)
            .where(PosSyncRun.venue_id == venue_id)
            .order_by(PosSyncRun.started_at.desc())
            .limit(20)
        ).all()
        return {"runs": [_run_public(row) for row in rows]}


def _sale_location(session: Session, venue_id: uuid.UUID) -> Location:
    bar = session.scalar(
        select(Location).where(Location.venue_id == venue_id, Location.kind == "bar").order_by(Location.name.asc()).limit(1)
    )
    if bar is not None:
        return bar
    place = session.scalar(select(Location).where(Location.venue_id == venue_id).order_by(Location.name.asc()).limit(1))
    if place is None:
        raise PosError("This venue has no stock location for a POS sale.", 422)
    return place


def _record_failure(venue_id: uuid.UUID, connection_id: uuid.UUID, started: datetime, message: str) -> None:
    safe = message
    for marker in _SECRET_MARKERS:
        if marker in safe.lower():
            safe = "POS sync failed."
            break
    with session_scope() as session:
        try:
            venue = session.get(Venue, venue_id)
            if venue is None:
                return
            actor_id, email = _actor(venue_id)
            run = PosSyncRun(
                venue_id=venue_id,
                connection_id=connection_id,
                status="failed",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                counts={"posted": 0, "skipped": 0, "unmapped": []},
                error=safe[:2000],
                actor_user_id=actor_id,
            )
            session.add(run)
            session.flush()
            record_audit_event(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                action=ACTION_SYNC_FAILED,
                entity_type="pos_sync_run",
                entity_id=run.id,
                before=None,
                after={"status": "failed", "error": safe[:200]},
                actor_user_id=actor_id,
                actor_email=email,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise


def run_sync(session: Session, venue_id: uuid.UUID, driver: PosAdapter) -> dict:
    venue = _venue(session, venue_id)
    row = _connection(session, venue_id)
    if row is None or row.status != "active" or not row.location_id:
        raise PosError("Connect a register before syncing sales.", 422)
    started = datetime.now(timezone.utc)
    end = started
    if row.watermark:
        start = _parse_time(row.watermark)
    else:
        start = end - timedelta(days=30)
    lines = driver.search_sales(row.location_id, _stamp(start) or "", _stamp(end) or "")
    place = _sale_location(session, venue_id)
    mappings = {
        item.variation_id: item
        for item in session.scalars(
            select(PosItemMapping).where(
                PosItemMapping.venue_id == venue_id,
                PosItemMapping.provider == row.provider,
            )
        ).all()
    }
    posted_ids = set(
        session.scalars(
            select(PosSale.external_line_id).where(
                PosSale.venue_id == venue_id,
                PosSale.provider == row.provider,
            )
        ).all()
    )
    posted = 0
    skipped = 0
    unmapped: list[dict] = []
    handled: list[datetime] = []
    pending: list[datetime] = []
    actor_id, email = _actor(venue_id)
    for line in lines:
        closed = _parse_time(line.closed_at)
        external = line.external_line_id[:200]
        if external in posted_ids:
            skipped += 1
            handled.append(closed)
            continue
        mapping = mappings.get(line.variation_id)
        if mapping is None or not line.variation_id:
            unmapped.append(
                {
                    "variation_id": line.variation_id,
                    "item_id": line.item_id,
                    "name": line.name,
                    "quantity": line.quantity,
                    "closed_at": _stamp(closed),
                }
            )
            pending.append(closed)
            continue
        try:
            sold = Decimal(str(line.quantity).strip() or "0")
        except Exception as exc:
            raise PosError("A POS quantity was not a number.", 422) from exc
        units = as_qty(sold * Decimal(mapping.units_per_sale))
        if units == 0:
            skipped += 1
            handled.append(closed)
            continue
        stock = session.get(Sku, mapping.sku_id)
        if stock is None or stock.venue_id != venue_id:
            unmapped.append(
                {
                    "variation_id": line.variation_id,
                    "item_id": line.item_id,
                    "name": line.name,
                    "quantity": line.quantity,
                    "closed_at": _stamp(closed),
                }
            )
            pending.append(closed)
            continue
        sale_id = uuid.uuid4()
        movement = post_movement(
            session,
            venue_id,
            sku=stock.barcode,
            location_id=place.id,
            quantity=-units,
            movement_type="sale",
            source_type="pos_sale",
            source_id=str(sale_id),
            reason="pos_sale",
            created_at=closed,
            action="inventory.movement",
            actor_user_id=actor_id,
            actor_email=email,
        )
        session.add(
            PosSale(
                id=sale_id,
                venue_id=venue_id,
                provider=row.provider,
                external_line_id=external,
                order_id=line.order_id[:128],
                variation_id=line.variation_id[:128],
                sku_id=stock.id,
                movement_id=movement.id,
                quantity=units,
                closed_at=closed,
            )
        )
        posted_ids.add(external)
        posted += 1
        handled.append(closed)
    if pending:
        row.watermark = _stamp(min(pending)) or ""
    elif handled:
        row.watermark = _stamp(max(handled)) or ""
    row.last_cursor = ""
    row.last_synced_at = end
    row.updated_at = end
    counts = {"posted": posted, "skipped": skipped, "unmapped": unmapped}
    run = PosSyncRun(
        venue_id=venue_id,
        connection_id=row.id,
        status="completed",
        started_at=started,
        finished_at=end,
        counts=counts,
        error="",
        actor_user_id=actor_id,
    )
    session.add(run)
    session.flush()
    record_audit_event(
        session,
        org_id=venue.organization_id,
        venue_id=venue_id,
        action=ACTION_SYNCED,
        entity_type="pos_sync_run",
        entity_id=run.id,
        before=None,
        after={"posted": posted, "skipped": skipped, "unmapped": len(unmapped)},
        actor_user_id=actor_id,
        actor_email=email,
    )
    return {"run": _run_public(run), "posted": posted, "skipped": skipped, "unmapped": unmapped}


def sync(venue_id: uuid.UUID, client=None) -> dict:
    started = datetime.now(timezone.utc)
    connection_id: uuid.UUID | None = None
    with session_scope() as session:
        row = _connection(session, venue_id)
        if row is not None:
            connection_id = row.id
        try:
            if row is None:
                raise PosError("Connect a register before syncing sales.", 422)
            driver = open_driver(session, row, client=client)
            result = run_sync(session, venue_id, driver)
            session.commit()
            return result
        except Exception as exc:
            session.rollback()
            message = exc.message if isinstance(exc, (PosError, Rejected, NotFound)) else "POS sync failed."
            if connection_id is not None:
                _record_failure(venue_id, connection_id, started, message)
            raise


def sync_all() -> int:
    """Sync every venue that has an active register. Returns the number of failures."""

    from madira.db import SessionLocal

    session = SessionLocal()
    try:
        rows = list(
            session.scalars(select(PosConnection).where(PosConnection.status == "active").order_by(PosConnection.id)).all()
        )
        venue_ids = [row.venue_id for row in rows]
    finally:
        session.close()
    failures = 0
    for venue_id in venue_ids:
        try:
            sync(venue_id)
        except (PosError, Rejected, NotFound):
            failures += 1
    return failures


def unmapped_items(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        return {"items": _unmapped(session, venue_id)}


def _unmapped(session: Session, venue_id: uuid.UUID) -> list[dict]:
    run = session.scalar(
        select(PosSyncRun)
        .where(PosSyncRun.venue_id == venue_id, PosSyncRun.status == "completed")
        .order_by(PosSyncRun.started_at.desc())
        .limit(1)
    )
    if run is None:
        return []
    mapped = set(
        session.scalars(select(PosItemMapping.variation_id).where(PosItemMapping.venue_id == venue_id)).all()
    )
    items = []
    seen: set[str] = set()
    for row in (run.counts or {}).get("unmapped") or []:
        if not isinstance(row, dict):
            continue
        variation = str(row.get("variation_id") or "")
        if variation in mapped or variation in seen:
            continue
        seen.add(variation)
        items.append(
            {
                "variation_id": variation,
                "item_id": str(row.get("item_id") or ""),
                "name": str(row.get("name") or variation or "Unmapped item"),
                "quantity": str(row.get("quantity") or ""),
            }
        )
    return items


def gap_alerts(session: Session, venue_id: uuid.UUID, *, now: datetime | None = None) -> list[dict]:
    row = session.scalar(
        select(PosConnection).where(PosConnection.venue_id == venue_id, PosConnection.status == "active").limit(1)
    )
    alerts: list[dict] = []
    if row is None:
        return alerts
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    synced = row.last_synced_at
    if synced is not None and synced.tzinfo is None:
        synced = synced.replace(tzinfo=timezone.utc)
    if synced is None or moment - synced > STALE_AFTER:
        alerts.append(
            {
                "kind": "stale",
                "title": "No successful POS sync in the last 24 hours",
                "href": "/pos",
            }
        )
    for item in _unmapped(session, venue_id):
        alerts.append(
            {
                "kind": "unmapped",
                "title": f"Unmapped POS item {item['name']}",
                "href": "/pos",
            }
        )
    return alerts

