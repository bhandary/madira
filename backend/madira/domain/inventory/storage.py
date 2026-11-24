"""Storage zones, condition readings, and excursion alerts.

A reading inside the zone's temperature and humidity band is only an audit
event. A reading outside that band opens an excursion listing the bottles
currently in the zone's bins, and the acknowledgement is its own event.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import as_qty, public_qty
from madira.models import (
    EXCURSION_METRICS,
    Bin,
    ConditionExcursion,
    ConditionReading,
    Location,
    Product,
    ProductVariant,
    Sku,
    StockMovement,
    StorageZone,
    Venue,
)
from madira.tenancy import current_request

ACTION_READING = "storage.reading_recorded"
ACTION_EXCURSION = "storage.excursion_detected"
ACTION_ACK = "storage.excursion_acknowledged"

_HUNDREDTH = Decimal("0.01")
_LIMIT = Decimal("1000")


class Rejected(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _number(value, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise Rejected(f"{label} must be a number")
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except Exception as exc:
        raise Rejected(f"{label} must be a number") from exc
    if not dec.is_finite():
        raise Rejected(f"{label} must be a number")
    quantized = dec.quantize(_HUNDREDTH, rounding=ROUND_HALF_UP)
    if quantized.copy_abs() >= _LIMIT:
        raise Rejected(f"{label} is out of range")
    return quantized


def _text(value: str | None, limit: int, label: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise Rejected(f"{label} is required")
        return None
    text = str(value).strip()
    if not text:
        if required:
            raise Rejected(f"{label} is required")
        return None
    if len(text) > limit:
        raise Rejected(f"{label} is too long")
    return text


def _num(value) -> float:
    return float(Decimal(value).quantize(_HUNDREDTH))


def _stamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _actor(actor):
    user_id = getattr(actor, "user_id", None) if actor is not None else None
    email = getattr(actor, "email", None) if actor is not None else None
    if user_id is None or not email:
        ctx = current_request()
        if ctx is not None:
            if user_id is None:
                user_id = ctx.user_id
            if not email:
                email = ctx.email
    return user_id, email or ""


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _zone(session: Session, venue_id: uuid.UUID, zone_id: uuid.UUID) -> StorageZone:
    row = session.get(StorageZone, zone_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("storage zone not found")
    return row


def _location(session: Session, venue_id: uuid.UUID, location_id: uuid.UUID | None) -> Location | None:
    if location_id is None:
        return None
    row = session.get(Location, location_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("location not found")
    return row


def _bounds(zone: StorageZone) -> None:
    if zone.target_temp_min_c > zone.target_temp_max_c:
        raise Rejected("Temperature minimum cannot exceed the maximum")
    if zone.target_humidity_min_pct > zone.target_humidity_max_pct:
        raise Rejected("Humidity minimum cannot exceed the maximum")


def _side(value: Decimal, low: Decimal, high: Decimal) -> str | None:
    if value < low:
        return "low"
    if value > high:
        return "high"
    return None


def _metric(temp: Decimal, humidity: Decimal, zone: StorageZone) -> str | None:
    temp_side = _side(temp, zone.target_temp_min_c, zone.target_temp_max_c)
    humidity_side = _side(humidity, zone.target_humidity_min_pct, zone.target_humidity_max_pct)
    if temp_side and humidity_side:
        metric = "temp_and_humidity"
    elif temp_side:
        metric = f"temp_{temp_side}"
    elif humidity_side:
        metric = f"humidity_{humidity_side}"
    else:
        return None
    if metric not in EXCURSION_METRICS:
        raise Rejected("Excursion metric is not recognized")
    return metric


def affected_skus(session: Session, venue_id: uuid.UUID, location_id: uuid.UUID | None) -> list[dict]:
    """Bottles currently stored in the zone's bins. A zone with no location uses every venue bin."""

    stmt = select(Bin).where(Bin.venue_id == venue_id)
    if location_id is not None:
        stmt = stmt.where(Bin.location_id == location_id)
    bins = session.scalars(stmt).all()
    if not bins:
        return []
    codes = {row.id: row.code for row in bins}
    totals = session.execute(
        select(StockMovement.sku_id, StockMovement.bin_id, func.sum(StockMovement.quantity))
        .where(StockMovement.venue_id == venue_id, StockMovement.bin_id.in_(list(codes)))
        .group_by(StockMovement.sku_id, StockMovement.bin_id)
    ).all()
    found: list[dict] = []
    for sku_id, bin_id, quantity in totals:
        on_hand = as_qty(quantity or 0)
        if on_hand <= 0:
            continue
        stock = session.get(Sku, sku_id)
        product_name = ""
        sku_code = str(sku_id)
        if stock is not None:
            sku_code = stock.barcode or str(stock.id)
            variant = session.get(ProductVariant, stock.product_variant_id)
            product = session.get(Product, variant.product_id) if variant is not None else None
            product_name = product.name if product is not None else ""
        found.append(
            {
                "sku": sku_code,
                "product_name": product_name,
                "bin_code": codes.get(bin_id, ""),
                "on_hand": public_qty(on_hand),
            }
        )
    found.sort(key=lambda row: (row["bin_code"], row["sku"], row["product_name"]))
    return found


def reading_public(row: ConditionReading, *, in_range: bool | None = None) -> dict:
    body = {
        "id": str(row.id),
        "zone_id": str(row.zone_id),
        "temp_c": _num(row.temp_c),
        "humidity_pct": _num(row.humidity_pct),
        "source": row.source or "manual",
        "recorded_by_user_id": None if row.recorded_by_user_id is None else str(row.recorded_by_user_id),
        "recorded_at": _stamp(row.recorded_at),
        "notes": row.notes or "",
    }
    if in_range is not None:
        body["in_range"] = in_range
    return body


def excursion_public(row: ConditionExcursion) -> dict:
    return {
        "id": str(row.id),
        "zone_id": str(row.zone_id),
        "reading_id": str(row.reading_id),
        "metric": row.metric,
        "measured_temp_c": _num(row.measured_temp_c),
        "measured_humidity_pct": _num(row.measured_humidity_pct),
        "affected_skus": list(row.affected_skus or []),
        "status": row.status,
        "acknowledged_by_user_id": None if row.acknowledged_by_user_id is None else str(row.acknowledged_by_user_id),
        "acknowledged_at": _stamp(row.acknowledged_at),
        "resolution_note": row.resolution_note or "",
        "created_at": _stamp(row.created_at),
    }


def _latest_reading(session: Session, zone_id: uuid.UUID) -> ConditionReading | None:
    return session.scalar(
        select(ConditionReading)
        .where(ConditionReading.zone_id == zone_id)
        .order_by(ConditionReading.recorded_at.desc(), ConditionReading.id.desc())
        .limit(1)
    )


def _open_excursion(session: Session, zone_id: uuid.UUID) -> ConditionExcursion | None:
    return session.scalar(
        select(ConditionExcursion)
        .where(ConditionExcursion.zone_id == zone_id, ConditionExcursion.status == "open")
        .order_by(ConditionExcursion.created_at.desc(), ConditionExcursion.id.desc())
        .limit(1)
    )


def _latest_excursion(session: Session, zone_id: uuid.UUID) -> ConditionExcursion | None:
    return session.scalar(
        select(ConditionExcursion)
        .where(ConditionExcursion.zone_id == zone_id)
        .order_by(ConditionExcursion.created_at.desc(), ConditionExcursion.id.desc())
        .limit(1)
    )


def zone_public(session: Session, zone: StorageZone) -> dict:
    place = session.get(Location, zone.location_id) if zone.location_id is not None else None
    latest = _latest_reading(session, zone.id)
    in_range = True if latest is None else _metric(latest.temp_c, latest.humidity_pct, zone) is None
    open_row = _open_excursion(session, zone.id)
    shown = open_row if open_row is not None else (None if in_range else _latest_excursion(session, zone.id))
    return {
        "id": str(zone.id),
        "venue_id": str(zone.venue_id),
        "location_id": None if zone.location_id is None else str(zone.location_id),
        "location_name": "" if place is None else place.name,
        "name": zone.name,
        "target_temp_min_c": _num(zone.target_temp_min_c),
        "target_temp_max_c": _num(zone.target_temp_max_c),
        "target_humidity_min_pct": _num(zone.target_humidity_min_pct),
        "target_humidity_max_pct": _num(zone.target_humidity_max_pct),
        "notes": zone.notes or "",
        "created_at": _stamp(zone.created_at),
        "latest_reading": None if latest is None else reading_public(latest, in_range=in_range),
        "status": "ok" if in_range else "excursion",
        "excursion": None if shown is None else excursion_public(shown),
    }


def create_storage_zone(
    session: Session,
    venue_id: uuid.UUID,
    *,
    name: str,
    location_id: uuid.UUID | None,
    target_temp_min_c,
    target_temp_max_c,
    target_humidity_min_pct,
    target_humidity_max_pct,
    notes: str | None = None,
) -> StorageZone:
    _venue(session, venue_id)
    place = _location(session, venue_id, location_id)
    label = _text(name, 200, "Name", required=True)
    existing = session.scalar(
        select(StorageZone.id).where(StorageZone.venue_id == venue_id, StorageZone.name == label).limit(1)
    )
    if existing is not None:
        raise Rejected("A storage zone with that name already exists.", 409)
    row = StorageZone(
        venue_id=venue_id,
        location_id=None if place is None else place.id,
        name=label or "",
        target_temp_min_c=_number(target_temp_min_c, "Minimum temperature"),
        target_temp_max_c=_number(target_temp_max_c, "Maximum temperature"),
        target_humidity_min_pct=_number(target_humidity_min_pct, "Minimum humidity"),
        target_humidity_max_pct=_number(target_humidity_max_pct, "Maximum humidity"),
        notes=_text(notes, 4000, "Notes"),
    )
    _bounds(row)
    session.add(row)
    session.flush()
    return row


def list_storage_zones(session: Session, venue_id: uuid.UUID) -> list[dict]:
    _venue(session, venue_id)
    rows = session.scalars(
        select(StorageZone).where(StorageZone.venue_id == venue_id).order_by(StorageZone.name, StorageZone.id)
    ).all()
    return [zone_public(session, row) for row in rows]


def list_readings(session: Session, venue_id: uuid.UUID, zone_id: uuid.UUID) -> list[dict]:
    zone = _zone(session, venue_id, zone_id)
    rows = session.scalars(
        select(ConditionReading)
        .where(ConditionReading.venue_id == venue_id, ConditionReading.zone_id == zone.id)
        .order_by(ConditionReading.recorded_at.desc(), ConditionReading.id.desc())
    ).all()
    return [reading_public(row, in_range=_metric(row.temp_c, row.humidity_pct, zone) is None) for row in rows]


def list_excursions(session: Session, venue_id: uuid.UUID, status: str | None = None) -> list[dict]:
    _venue(session, venue_id)
    stmt = select(ConditionExcursion).where(ConditionExcursion.venue_id == venue_id)
    if status:
        label = status.strip()
        if label not in {"open", "acknowledged"}:
            raise Rejected("status must be open or acknowledged")
        stmt = stmt.where(ConditionExcursion.status == label)
    stmt = stmt.order_by(ConditionExcursion.created_at.desc(), ConditionExcursion.id.desc())
    return [excursion_public(row) for row in session.scalars(stmt).all()]


def record_condition_reading(
    session: Session,
    venue_id: uuid.UUID,
    zone_id: uuid.UUID,
    temp_c,
    humidity_pct,
    actor,
    notes: str | None = None,
    source: str = "manual",
) -> dict:
    venue = _venue(session, venue_id)
    zone = _zone(session, venue_id, zone_id)
    temp = _number(temp_c, "Temperature")
    humidity = _number(humidity_pct, "Humidity")
    origin = _text(source, 32, "Source") or "manual"
    user_id, email = _actor(actor)
    now = datetime.now(timezone.utc)
    reading = ConditionReading(
        venue_id=venue_id,
        zone_id=zone.id,
        temp_c=temp,
        humidity_pct=humidity,
        source=origin,
        recorded_by_user_id=user_id,
        recorded_at=now,
        notes=_text(notes, 4000, "Notes"),
    )
    session.add(reading)
    session.flush()
    metric = _metric(temp, humidity, zone)
    excursion = None
    if metric is None:
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_READING,
            entity_type="condition_reading",
            entity_id=reading.id,
            after={
                "zone_id": str(zone.id),
                "zone": zone.name,
                "temp_c": f"{temp:.2f}",
                "humidity_pct": f"{humidity:.2f}",
                "source": origin,
            },
            actor_user_id=user_id,
            actor_email=email,
        )
    else:
        stock = affected_skus(session, venue_id, zone.location_id)
        excursion = ConditionExcursion(
            venue_id=venue_id,
            zone_id=zone.id,
            reading_id=reading.id,
            metric=metric,
            measured_temp_c=temp,
            measured_humidity_pct=humidity,
            affected_skus=stock,
            status="open",
        )
        session.add(excursion)
        session.flush()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_EXCURSION,
            entity_type="condition_excursion",
            entity_id=excursion.id,
            after={
                "zone_id": str(zone.id),
                "zone": zone.name,
                "reading_id": str(reading.id),
                "metric": metric,
                "temp_c": f"{temp:.2f}",
                "humidity_pct": f"{humidity:.2f}",
                "affected_skus": stock,
                "status": "open",
            },
            actor_user_id=user_id,
            actor_email=email,
        )
    return {
        "reading": reading_public(reading, in_range=metric is None),
        "excursion": None if excursion is None else excursion_public(excursion),
        "zone": zone_public(session, zone),
    }


def acknowledge_excursion(
    session: Session,
    venue_id: uuid.UUID,
    excursion_id: uuid.UUID,
    actor,
    resolution_note: str | None = None,
) -> dict:
    venue = _venue(session, venue_id)
    row = session.get(ConditionExcursion, excursion_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("excursion not found")
    if row.status != "open":
        raise Rejected("This excursion is already acknowledged.", 409)
    user_id, email = _actor(actor)
    note = _text(resolution_note, 4000, "Resolution note")
    row.status = "acknowledged"
    row.acknowledged_by_user_id = user_id
    row.acknowledged_at = datetime.now(timezone.utc)
    row.resolution_note = note
    session.flush()
    record_audit_event(
        session,
        org_id=venue.organization_id,
        venue_id=venue_id,
        action=ACTION_ACK,
        entity_type="condition_excursion",
        entity_id=row.id,
        before={"status": "open"},
        after={
            "status": "acknowledged",
            "zone_id": str(row.zone_id),
            "resolution_note": note or "",
        },
        actor_user_id=user_id,
        actor_email=email,
    )
    return excursion_public(row)


def ensure_demo_zones(session: Session, venue_id: uuid.UUID) -> None:
    """Two in-range demo zones. A second seed does not add another reading."""

    specs = (
        ("Main Cellar", "Main Cellar", "12", "14", "60", "75", "13", "68", "House cellar band"),
        ("Bar & Cold Box", "Walk-In Cooler", "4", "10", "50", "70", "6", "60", "Cold box band"),
    )
    for name, location_name, tmin, tmax, hmin, hmax, temp, humidity, notes in specs:
        place = session.scalar(
            select(Location).where(Location.venue_id == venue_id, Location.name == location_name)
        )
        zone = session.scalar(select(StorageZone).where(StorageZone.venue_id == venue_id, StorageZone.name == name))
        if zone is None:
            zone = create_storage_zone(
                session,
                venue_id,
                name=name,
                location_id=None if place is None else place.id,
                target_temp_min_c=tmin,
                target_temp_max_c=tmax,
                target_humidity_min_pct=hmin,
                target_humidity_max_pct=hmax,
                notes=notes,
            )
        elif place is not None and zone.location_id is None:
            zone.location_id = place.id
            session.flush()
        existing = session.scalar(
            select(ConditionReading.id).where(ConditionReading.zone_id == zone.id).limit(1)
        )
        if existing is None:
            record_condition_reading(
                session,
                venue_id,
                zone.id,
                temp,
                humidity,
                actor=None,
                notes="Seeded in-range reading",
            )
