"""Phone counts, offline replay, and variance approval.

A session stays ``in_progress`` while devices sync lines. Replaying the same
``(session_id, client_mutation_id)`` returns the stored line and does not
insert another. The latest line from each ``device_id`` is that device's
reading. Two devices with different quantities for one SKU are a conflict.
Approval is refused until someone records a resolved quantity.

Submit snapshots ``expected_quantity`` from the stock ledger at the session's
location. Approval posts one ``count_adjustment`` per SKU whose counted
quantity differs from that snapshot, with ``source_type="count_session"``.
A zero variance posts nothing. The caller commits through these functions.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import (
    Rejected,
    as_qty,
    post_movement,
    public_qty,
    valuation_cents,
)
from madira.domain.session import session_scope
from madira.models import (
    Bin,
    CountConflictResolution,
    CountLine,
    CountSession,
    Location,
    Sku,
    StockMovement,
    Venue,
)

ACTION_STARTED = "count_session.started"
ACTION_APPROVED = "count_session.approved"
ACTION_RESOLVED = "count_conflict.resolved"

_QR = re.compile(r"^madira:bin:([^:]+):([A-Za-z0-9][A-Za-z0-9_-]{0,63})$")
_MAX_BATCH = 500


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _when(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _actor(actor) -> tuple[uuid.UUID | None, str]:
    if actor is None:
        return None, ""
    user_id = getattr(actor, "user_id", None)
    email = getattr(actor, "email", "") or ""
    return user_id, email


def _clip(value: str | None, limit: int, label: str) -> str:
    text = "" if value is None else str(value).strip()
    if len(text) > limit:
        raise Rejected(f"{label} is too long")
    return text


def _uuid(value, label: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise NotFound(f"{label} not found") from exc


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _location(session: Session, venue_id: uuid.UUID, location_id: uuid.UUID) -> Location:
    row = session.get(Location, location_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("location not found")
    return row


def _count(session: Session, venue_id: uuid.UUID, session_id: uuid.UUID) -> CountSession:
    row = session.get(CountSession, session_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("count session not found")
    return row


def _sku(session: Session, venue_id: uuid.UUID, code: str) -> Sku:
    cleaned = (code or "").strip().upper()
    if not cleaned:
        raise NotFound("unknown sku")
    row = session.scalar(select(Sku).where(Sku.venue_id == venue_id, func.upper(Sku.barcode) == cleaned))
    if row is None:
        raise NotFound(f"unknown sku {code}")
    return row


def _bin_from_qr(session: Session, venue_id: uuid.UUID, payload: str) -> Bin:
    match = _QR.match((payload or "").strip())
    if match is None:
        raise NotFound("bin not found")
    try:
        parsed = uuid.UUID(match.group(1))
    except ValueError as exc:
        raise NotFound("bin not found") from exc
    if parsed != venue_id:
        raise NotFound("bin not found")
    code = match.group(2).upper()
    row = session.scalar(select(Bin).where(Bin.venue_id == venue_id, Bin.code == code))
    if row is None:
        raise NotFound("bin not found")
    return row


def _bin_row(session: Session, venue_id: uuid.UUID, bin_id: uuid.UUID) -> Bin:
    row = session.get(Bin, bin_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("bin not found")
    return row


def _stamp_at(value) -> datetime:
    if value is None or value == "":
        return _now()
    if isinstance(value, datetime):
        return _when(value)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise Rejected("counted_at is not a timestamp") from exc
    return _when(parsed)


def _device(value) -> str:
    if value is None:
        return "web"
    text = str(value).strip()
    if not text:
        return "web"
    if len(text) > 64:
        raise Rejected("device_id is too long")
    return text


def _mutation(value) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise Rejected("client_mutation_id is required")
    if len(text) > 120:
        raise Rejected("client_mutation_id is too long")
    return text


def _quantity(value) -> Decimal:
    qty = as_qty(value)
    if qty < 0:
        raise Rejected("counted_quantity cannot be negative")
    return qty


def _run(fn):
    with session_scope() as session:
        try:
            result = fn(session)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise


def _lines(session: Session, count_id: uuid.UUID) -> list[CountLine]:
    return list(
        session.scalars(
            select(CountLine).where(CountLine.session_id == count_id).order_by(CountLine.counted_at, CountLine.id)
        ).all()
    )


def _skus(session: Session, sku_ids: set[uuid.UUID]) -> dict[uuid.UUID, Sku]:
    if not sku_ids:
        return {}
    rows = session.scalars(select(Sku).where(Sku.id.in_(sku_ids))).all()
    return {row.id: row for row in rows}


def _bins(session: Session, bin_ids: set[uuid.UUID]) -> dict[uuid.UUID, Bin]:
    if not bin_ids:
        return {}
    rows = session.scalars(select(Bin).where(Bin.id.in_(bin_ids))).all()
    return {row.id: row for row in rows}


def _resolutions(session: Session, count_id: uuid.UUID) -> dict[uuid.UUID, CountConflictResolution]:
    rows = session.scalars(
        select(CountConflictResolution).where(CountConflictResolution.session_id == count_id)
    ).all()
    return {row.sku_id: row for row in rows}


def _latest_by_device(lines: list[CountLine]) -> dict[str, CountLine]:
    found: dict[str, CountLine] = {}
    for line in sorted(lines, key=lambda item: (_when(item.counted_at), str(item.id))):
        found[line.device_id] = line
    return found


def _location_qty(session: Session, venue_id: uuid.UUID, sku_id: uuid.UUID, location_id: uuid.UUID) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
            StockMovement.venue_id == venue_id,
            StockMovement.sku_id == sku_id,
            StockMovement.location_id == location_id,
        )
    )
    return as_qty(total or 0)


def _name(stock: Sku) -> str:
    try:
        return stock.variant.product.name
    except Exception:
        return stock.barcode


def _session_public(row: CountSession, place: Location) -> dict:
    return {
        "id": str(row.id),
        "venue_id": str(row.venue_id),
        "location_id": str(row.location_id),
        "location_name": place.name,
        "status": row.status,
        "notes": row.notes or "",
        "started_by_user_id": None if row.started_by_user_id is None else str(row.started_by_user_id),
        "submitted_by_user_id": None if row.submitted_by_user_id is None else str(row.submitted_by_user_id),
        "approved_by_user_id": None if row.approved_by_user_id is None else str(row.approved_by_user_id),
        "started_at": _iso(row.started_at),
        "submitted_at": _iso(row.submitted_at),
        "approved_at": _iso(row.approved_at),
    }


def _line_public(line: CountLine, stock: Sku, spot: Bin | None) -> dict:
    expected = None if line.expected_quantity is None else public_qty(line.expected_quantity)
    return {
        "id": str(line.id),
        "session_id": str(line.session_id),
        "sku_id": str(line.sku_id),
        "sku": stock.barcode,
        "name": _name(stock),
        "bin_id": None if line.bin_id is None else str(line.bin_id),
        "bin_code": "" if spot is None else spot.code,
        "counted_quantity": public_qty(line.counted_quantity),
        "expected_quantity": expected,
        "device_id": line.device_id,
        "client_mutation_id": line.client_mutation_id,
        "counted_at": _iso(line.counted_at),
        "notes": line.notes or "",
    }


def _groups(lines: list[CountLine]) -> dict[uuid.UUID, list[CountLine]]:
    grouped: dict[uuid.UUID, list[CountLine]] = {}
    for line in lines:
        grouped.setdefault(line.sku_id, []).append(line)
    return grouped


def _conflicts(grouped, resolutions, stocks) -> list[dict]:
    found = []
    for sku_id, group in grouped.items():
        latest = _latest_by_device(group)
        quantities = {as_qty(line.counted_quantity) for line in latest.values()}
        if len(latest) < 2 or len(quantities) < 2:
            continue
        resolution = resolutions.get(sku_id)
        readings = [
            {
                "device_id": line.device_id,
                "counted_quantity": public_qty(line.counted_quantity),
                "counted_at": _iso(line.counted_at),
            }
            for line in sorted(latest.values(), key=lambda item: (_when(item.counted_at), str(item.id)))
        ]
        found.append(
            {
                "sku": stocks[sku_id].barcode,
                "readings": readings,
                "resolved": resolution is not None,
                "resolved_quantity": None if resolution is None else public_qty(resolution.resolved_quantity),
            }
        )
    found.sort(key=lambda item: item["sku"])
    return found


def _effective(group: list[CountLine], resolution: CountConflictResolution | None) -> Decimal | None:
    if resolution is not None:
        return as_qty(resolution.resolved_quantity)
    latest = _latest_by_device(group)
    quantities = {as_qty(line.counted_quantity) for line in latest.values()}
    if len(quantities) == 1:
        return next(iter(quantities))
    return None


def _expected_for(session: Session, count: CountSession, sku_id: uuid.UUID, group: list[CountLine]) -> Decimal:
    snapped = [line.expected_quantity for line in group if line.expected_quantity is not None]
    if snapped and len(snapped) == len(group):
        return as_qty(snapped[0])
    return _location_qty(session, count.venue_id, sku_id, count.location_id)


def _variance_lines(session: Session, count: CountSession, grouped, resolutions, stocks) -> list[dict]:
    rows = []
    for sku_id, group in grouped.items():
        stock = stocks[sku_id]
        expected = _expected_for(session, count, sku_id, group)
        counted = _effective(group, resolutions.get(sku_id))
        variance = None if counted is None else counted - expected
        cost = int(stock.cost or 0)
        rows.append(
            {
                "sku": stock.barcode,
                "name": _name(stock),
                "counted_quantity": None if counted is None else public_qty(counted),
                "expected_quantity": public_qty(expected),
                "variance": None if variance is None else public_qty(variance),
                "variance_value_cents": None if variance is None else valuation_cents(variance, cost),
                "unit_cost_cents": cost,
            }
        )
    rows.sort(key=lambda item: item["sku"])
    return rows


def _report(session: Session, count: CountSession) -> dict:
    place = _location(session, count.venue_id, count.location_id)
    lines = _lines(session, count.id)
    sku_ids = {line.sku_id for line in lines}
    stocks = _skus(session, sku_ids)
    spots = _bins(session, {line.bin_id for line in lines if line.bin_id is not None})
    grouped = _groups(lines)
    resolutions = _resolutions(session, count.id)
    return {
        "session": _session_public(count, place),
        "lines": [_line_public(line, stocks[line.sku_id], None if line.bin_id is None else spots.get(line.bin_id)) for line in lines],
        "variance_lines": _variance_lines(session, count, grouped, resolutions, stocks),
        "conflicts": _conflicts(grouped, resolutions, stocks),
    }


def _unresolved(report: dict) -> bool:
    return any(not row["resolved"] for row in report["conflicts"])


def start_count_session(venue_id: uuid.UUID, location_id: uuid.UUID, actor, notes: str | None = None) -> dict:
    """Open an in-progress count and append count_session.started."""

    venue_id = _uuid(venue_id, "venue")
    location_id = _uuid(location_id, "location")
    user_id, email = _actor(actor)
    cleaned = _clip(notes, 2000, "notes")

    def write(session: Session) -> dict:
        venue = _venue(session, venue_id)
        place = _location(session, venue_id, location_id)
        row = CountSession(
            venue_id=venue_id,
            location_id=place.id,
            status="in_progress",
            started_by_user_id=user_id,
            notes=cleaned,
            started_at=_now(),
        )
        session.add(row)
        session.flush()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_STARTED,
            entity_type="count_session",
            entity_id=row.id,
            before=None,
            after={"status": "in_progress", "location_id": str(place.id), "location_name": place.name, "notes": cleaned},
            actor_user_id=user_id,
            actor_email=email,
        )
        return _session_public(row, place)

    return _run(write)


def list_count_sessions(venue_id: uuid.UUID) -> dict:
    venue_id = _uuid(venue_id, "venue")

    def read(session: Session) -> dict:
        rows = session.execute(
            select(CountSession, Location)
            .join(Location, Location.id == CountSession.location_id)
            .where(CountSession.venue_id == venue_id)
            .order_by(CountSession.started_at.desc(), CountSession.id.desc())
        ).all()
        return {"sessions": [_session_public(row, place) for row, place in rows]}

    return _run(read)


def get_count_report(venue_id: uuid.UUID, session_id: uuid.UUID) -> dict:
    venue_id = _uuid(venue_id, "venue")
    session_id = _uuid(session_id, "count session")

    def read(session: Session) -> dict:
        count = _count(session, venue_id, session_id)
        return _report(session, count)

    return _run(read)


def sync_count_lines(venue_id: uuid.UUID, session_id: uuid.UUID, entries: list[dict], actor) -> dict:
    """Insert offline lines. A repeated client_mutation_id returns the saved row."""

    venue_id = _uuid(venue_id, "venue")
    session_id = _uuid(session_id, "count session")
    batch = list(entries or [])
    if len(batch) > _MAX_BATCH:
        raise Rejected("Too many count lines in one sync.")

    def write(session: Session) -> dict:
        count = _count(session, venue_id, session_id)
        if count.status != "in_progress":
            raise Rejected("Count session is not in progress.", 409)
        place = _location(session, venue_id, count.location_id)
        saved: list[CountLine] = []
        for entry in batch:
            if not isinstance(entry, dict):
                raise Rejected("count line must be an object")
            mutation = _mutation(entry.get("client_mutation_id"))
            existing = session.scalar(
                select(CountLine).where(
                    CountLine.session_id == count.id,
                    CountLine.client_mutation_id == mutation,
                )
            )
            if existing is not None:
                saved.append(existing)
                continue
            code = entry.get("sku") or entry.get("barcode") or ""
            stock = _sku(session, venue_id, str(code))
            spot = None
            if entry.get("bin_qr"):
                spot = _bin_from_qr(session, venue_id, str(entry.get("bin_qr")))
            elif entry.get("bin_id"):
                spot = _bin_row(session, venue_id, _uuid(entry.get("bin_id"), "bin"))
            if spot is not None and spot.location_id != place.id:
                raise Rejected("bin is not in that location")
            line = CountLine(
                venue_id=venue_id,
                session_id=count.id,
                sku_id=stock.id,
                bin_id=None if spot is None else spot.id,
                counted_quantity=_quantity(entry.get("counted_quantity")),
                expected_quantity=None,
                device_id=_device(entry.get("device_id")),
                client_mutation_id=mutation,
                counted_at=_stamp_at(entry.get("counted_at")),
                notes=_clip(entry.get("notes"), 2000, "notes"),
            )
            session.add(line)
            session.flush()
            saved.append(line)
        sku_ids = {line.sku_id for line in saved}
        stocks = _skus(session, sku_ids)
        spots = _bins(session, {line.bin_id for line in saved if line.bin_id is not None})
        report = _report(session, count)
        return {
            "session": report["session"],
            "lines": [
                _line_public(line, stocks[line.sku_id], None if line.bin_id is None else spots.get(line.bin_id))
                for line in saved
            ],
            "conflicts": report["conflicts"],
        }

    return _run(write)


def resolve_count_conflict(
    venue_id: uuid.UUID,
    session_id: uuid.UUID,
    sku: str,
    resolved_quantity,
    actor,
    notes: str | None = None,
) -> dict:
    """Store the quantity that variance approval should use for this SKU."""

    venue_id = _uuid(venue_id, "venue")
    session_id = _uuid(session_id, "count session")
    user_id, email = _actor(actor)
    chosen = _quantity(resolved_quantity)
    cleaned = _clip(notes, 2000, "notes")

    def write(session: Session) -> dict:
        venue = _venue(session, venue_id)
        count = _count(session, venue_id, session_id)
        if count.status not in {"in_progress", "submitted"}:
            raise Rejected("Count session can no longer be changed.", 409)
        stock = _sku(session, venue_id, sku)
        present = session.scalar(
            select(CountLine.id).where(CountLine.session_id == count.id, CountLine.sku_id == stock.id).limit(1)
        )
        if present is None:
            raise NotFound(f"unknown sku {sku}")
        row = session.scalar(
            select(CountConflictResolution).where(
                CountConflictResolution.session_id == count.id,
                CountConflictResolution.sku_id == stock.id,
            )
        )
        before = None if row is None else {"sku": stock.barcode, "resolved_quantity": public_qty(row.resolved_quantity)}
        if row is None:
            row = CountConflictResolution(
                venue_id=venue_id,
                session_id=count.id,
                sku_id=stock.id,
                resolved_quantity=chosen,
                notes=cleaned,
                resolved_by_user_id=user_id,
                resolved_at=_now(),
            )
            session.add(row)
        else:
            row.resolved_quantity = chosen
            row.notes = cleaned
            row.resolved_by_user_id = user_id
            row.resolved_at = _now()
        session.flush()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_RESOLVED,
            entity_type="count_session",
            entity_id=count.id,
            before=before,
            after={"sku": stock.barcode, "resolved_quantity": public_qty(chosen), "notes": cleaned},
            actor_user_id=user_id,
            actor_email=email,
        )
        return _report(session, count)

    return _run(write)


def submit_count_session(venue_id: uuid.UUID, session_id: uuid.UUID, actor) -> dict:
    """Snapshot expected quantity per counted SKU and mark the session submitted."""

    venue_id = _uuid(venue_id, "venue")
    session_id = _uuid(session_id, "count session")
    user_id, _email = _actor(actor)

    def write(session: Session) -> dict:
        count = _count(session, venue_id, session_id)
        if count.status != "in_progress":
            raise Rejected("Count session is not in progress.", 409)
        lines = _lines(session, count.id)
        for sku_id, group in _groups(lines).items():
            expected = _location_qty(session, venue_id, sku_id, count.location_id)
            for line in group:
                line.expected_quantity = expected
        count.status = "submitted"
        count.submitted_at = _now()
        count.submitted_by_user_id = user_id
        session.flush()
        return _report(session, count)

    return _run(write)


def approve_count_session(venue_id: uuid.UUID, session_id: uuid.UUID, actor) -> dict:
    """Post count adjustments for every non-zero variance, then mark the session approved."""

    venue_id = _uuid(venue_id, "venue")
    session_id = _uuid(session_id, "count session")
    user_id, email = _actor(actor)

    def write(session: Session) -> dict:
        venue = _venue(session, venue_id)
        count = _count(session, venue_id, session_id)
        if count.status != "submitted":
            raise Rejected("Count session is not submitted.", 409)
        report = _report(session, count)
        if _unresolved(report):
            raise Rejected("Resolve multi-device conflicts before approving this count.", 409)
        lines = _lines(session, count.id)
        grouped = _groups(lines)
        stocks = _skus(session, set(grouped))
        resolutions = _resolutions(session, count.id)
        movements = []
        for sku_id, group in grouped.items():
            stock = stocks[sku_id]
            expected = _expected_for(session, count, sku_id, group)
            counted = _effective(group, resolutions.get(sku_id))
            if counted is None:
                continue
            delta = counted - expected
            if delta == 0:
                continue
            bin_ids = {line.bin_id for line in group}
            bin_id = next(iter(bin_ids)) if len(bin_ids) == 1 else None
            movement = post_movement(
                session,
                venue_id,
                sku=stock.barcode,
                location_id=count.location_id,
                bin_id=bin_id,
                quantity=delta,
                movement_type="count_adjustment",
                unit_cost_cents=int(stock.cost or 0),
                source_type="count_session",
                source_id=str(count.id),
                reason=f"Count variance {stock.barcode}",
                actor_user_id=user_id,
                actor_email=email,
            )
            movements.append(
                {
                    "id": str(movement.id),
                    "sku": stock.barcode,
                    "quantity": public_qty(movement.quantity),
                    "movement_type": movement.movement_type,
                    "source_type": movement.source_type,
                    "source_id": movement.source_id,
                    "location_id": str(movement.location_id),
                }
            )
        count.status = "approved"
        count.approved_at = _now()
        count.approved_by_user_id = user_id
        session.flush()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_APPROVED,
            entity_type="count_session",
            entity_id=count.id,
            before={"status": "submitted"},
            after={"status": "approved", "adjustments": movements},
            actor_user_id=user_id,
            actor_email=email,
        )
        body = _report(session, count)
        body["movements"] = movements
        return body

    return _run(write)
