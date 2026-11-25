"""Register probes, accept signed readings, and review a CSV before it posts.

Both paths call ``record_condition_reading``. The excursion decision stays in
that function. A reading is stored once per sensor and timestamp. The signing
secret is returned only by create and rotate.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from madira.crypto import decrypt_secret, encrypt_secret
from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import NotFound
from madira.domain.inventory.storage import (
    Rejected,
    _latest_reading,
    excursion_metric,
    paired_reading,
    record_condition_reading,
)
from madira.domain.session import session_scope
from madira.models import Location, Sensor, SensorImport, SensorReading, StorageZone, Venue
from madira.tenancy import current_request
from madira.timestamps import parse_stamp

STALE_HOURS = 6
REPLAY_SECONDS = 300
_METRICS = {"temperature_c", "humidity_pct"}
_KEY_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
_HEADER_SENSOR = {"sensor", "external_id", "external id"}
_HEADER_AT = {"timestamp", "at"}
_HEADER_METRIC = {"metric"}
_HEADER_VALUE = {"value"}
_MAX_CSV_BYTES = 200_000
_MAX_ROWS = 500


class SensorError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _stamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _actor(venue_id: uuid.UUID) -> tuple[uuid.UUID | None, str]:
    ctx = current_request()
    if ctx is None or ctx.venue_id != venue_id:
        return None, ""
    return ctx.user_id, ctx.email or ""


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


def _text(value: str, limit: int, label: str) -> str:
    cleaned = " ".join((value or "").split())
    if not cleaned:
        raise SensorError(f"{label} is required.")
    if len(cleaned) > limit:
        raise SensorError(f"{label} is too long.")
    return cleaned


def _metric(value: str) -> str:
    cleaned = (value or "").strip()
    if cleaned not in _METRICS:
        raise SensorError("Metric must be temperature_c or humidity_pct.")
    return cleaned


def _last4(secret: str) -> str:
    return secret[-4:] if len(secret) >= 4 else secret


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


def _new_key() -> str:
    return secrets.token_urlsafe(24)


def _postgres(session: Session) -> bool:
    bind = session.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def _set_config(session: Session, name: str, value: str) -> None:
    if not _postgres(session):
        return
    session.execute(text("SELECT set_config(:name, :value, true)"), {"name": name, "value": value})


def _public(session: Session, row: Sensor, *, secret: str | None = None) -> dict:
    last = session.scalar(
        select(SensorReading)
        .where(SensorReading.sensor_id == row.id)
        .order_by(SensorReading.recorded_at.desc(), SensorReading.id.desc())
        .limit(1)
    )
    zone = session.get(StorageZone, row.zone_id)
    place = session.get(Location, zone.location_id) if zone is not None and zone.location_id is not None else None
    now = datetime.now(timezone.utc)
    stale = last is None or last.recorded_at < now - timedelta(hours=STALE_HOURS)
    body = {
        "id": str(row.id),
        "name": row.name,
        "zone_id": str(row.zone_id),
        "zone_name": "" if zone is None else zone.name,
        "location_name": "" if place is None else place.name,
        "metric": row.metric,
        "external_id": row.external_id,
        "sensor_key": row.sensor_key,
        "secret_last4": row.secret_last4,
        "masked": f"····{row.secret_last4}",
        "last_value": "" if last is None else f"{Decimal(last.value):.2f}",
        "last_at": _stamp(None if last is None else last.recorded_at),
        "stale": stale,
        "stale_after_hours": STALE_HOURS,
        "created_at": _stamp(row.created_at),
    }
    if secret is not None:
        body["secret"] = secret
    return body


def _audit(session: Session, venue: Venue, action: str, entity_id: uuid.UUID, before: dict | None, after: dict | None) -> None:
    user_id, email = _actor(venue.id)
    record_audit_event(
        session,
        org_id=venue.organization_id,
        venue_id=venue.id,
        action=action,
        entity_type="sensor",
        entity_id=entity_id,
        before=before,
        after=after,
        actor_user_id=user_id,
        actor_email=email,
    )


def list_sensors(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        _venue(session, venue_id)
        rows = session.scalars(
            select(Sensor).where(Sensor.venue_id == venue_id).order_by(Sensor.name, Sensor.id)
        ).all()
        return {"sensors": [_public(session, row) for row in rows], "stale_after_hours": STALE_HOURS}


def sensor_board(session: Session, venue_id: uuid.UUID) -> list[dict]:
    rows = session.scalars(select(Sensor).where(Sensor.venue_id == venue_id).order_by(Sensor.name, Sensor.id)).all()
    return [_public(session, row) for row in rows]


def create_sensor(venue_id: uuid.UUID, *, name: str, zone_id: uuid.UUID, metric: str, external_id: str) -> dict:
    label = _text(name, 200, "Name")
    external = _text(external_id, 120, "External id")
    kind = _metric(metric)
    secret = _new_secret()
    with session_scope() as session:
        venue = _venue(session, venue_id)
        zone = _zone(session, venue_id, zone_id)
        taken = session.scalar(
            select(Sensor.id).where(Sensor.venue_id == venue_id, Sensor.external_id == external).limit(1)
        )
        if taken is not None:
            raise SensorError("A sensor with that external id already exists.", 409)
        row = Sensor(
            venue_id=venue_id,
            zone_id=zone.id,
            name=label,
            metric=kind,
            external_id=external,
            sensor_key=_new_key(),
            secret_ciphertext=encrypt_secret(secret),
            secret_last4=_last4(secret),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            venue,
            "sensor.created",
            row.id,
            None,
            {
                "name": row.name,
                "zone_id": str(row.zone_id),
                "metric": row.metric,
                "external_id": row.external_id,
                "secret_last4": row.secret_last4,
            },
        )
        body = _public(session, row, secret=secret)
        session.commit()
        return body


def rotate_secret(venue_id: uuid.UUID, sensor_id: uuid.UUID) -> dict:
    secret = _new_secret()
    with session_scope() as session:
        venue = _venue(session, venue_id)
        row = session.get(Sensor, sensor_id)
        if row is None or row.venue_id != venue_id:
            raise NotFound("sensor not found")
        previous = row.secret_last4
        row.secret_ciphertext = encrypt_secret(secret)
        row.secret_last4 = _last4(secret)
        session.flush()
        _audit(
            session,
            venue,
            "sensor.secret_rotated",
            row.id,
            {"secret_last4": previous},
            {"secret_last4": row.secret_last4},
        )
        body = _public(session, row, secret=secret)
        session.commit()
        return body


def _load_by_key(session: Session, sensor_key: str) -> Sensor:
    key = (sensor_key or "").strip()
    if not key or len(key) > 80 or any(char not in _KEY_ALPHABET for char in key):
        raise NotFound("Unknown sensor.")
    _set_config(session, "app.sensor_key", key)
    row = session.scalar(select(Sensor).where(Sensor.sensor_key == key).limit(1))
    if row is None:
        raise NotFound("Unknown sensor.")
    _set_config(session, "app.venue_id", str(row.venue_id))
    _set_config(session, "app.sensor_key", "")
    return row


def _signature(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _authorized(row: Sensor, timestamp: str, signature: str, body: bytes) -> None:
    stamp = (timestamp or "").strip()
    presented = (signature or "").strip().lower()
    if not stamp or not presented:
        raise SensorError("Signature was rejected.", 401)
    try:
        instant = int(stamp)
    except ValueError as exc:
        raise SensorError("Signature was rejected.", 401) from exc
    if abs(int(datetime.now(timezone.utc).timestamp()) - instant) > REPLAY_SECONDS:
        raise SensorError("Signature was rejected.", 401)
    try:
        secret = decrypt_secret(row.secret_ciphertext)
    except RuntimeError as exc:
        raise SensorError("Signature was rejected.", 401) from exc
    expected = _signature(secret, stamp, body)
    if len(presented) != len(expected) or not hmac.compare_digest(presented, expected):
        raise SensorError("Signature was rejected.", 401)


def _parse_readings(body: bytes, sensor: Sensor) -> list[dict]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SensorError("The reading was rejected.", 422) from exc
    if not isinstance(payload, dict) or set(payload) != {"readings"}:
        raise SensorError("The reading was rejected.", 422)
    rows = payload["readings"]
    if not isinstance(rows, list) or not rows:
        raise SensorError("The reading was rejected.", 422)
    parsed: list[dict] = []
    for item in rows:
        if not isinstance(item, dict) or not {"at", "value", "metric"} <= set(item) or not set(item) <= {"external_id", "at", "value", "metric"}:
            raise SensorError("The reading was rejected.", 422)
        external = item.get("external_id")
        if external is not None and not isinstance(external, str):
            raise SensorError("The reading was rejected.", 422)
        named = (external or "").strip()
        if named and named != sensor.external_id:
            raise SensorError("Unknown sensor.", 422)
        if item["metric"] != sensor.metric:
            raise SensorError("The reading was rejected.", 422)
        if isinstance(item["value"], bool) or not isinstance(item["value"], (int, float)):
            raise SensorError("The reading was rejected.", 422)
        try:
            when = parse_stamp(str(item["at"]))
        except (TypeError, ValueError) as exc:
            raise SensorError("The reading was rejected.", 422) from exc
        parsed.append({"at": when, "value": item["value"]})
    return parsed


def _record(session: Session, sensor: Sensor, when: datetime, value, source: str) -> dict:
    existing = session.scalar(
        select(SensorReading).where(SensorReading.sensor_id == sensor.id, SensorReading.recorded_at == when).limit(1)
    )
    if existing is not None:
        return {"status": "duplicate", "reading_id": str(existing.condition_reading_id), "excursion": False}
    zone = session.get(StorageZone, sensor.zone_id)
    if zone is None or zone.venue_id != sensor.venue_id:
        raise NotFound("storage zone not found")
    last = _latest_reading(session, zone.id)
    temp, humidity, note = paired_reading(zone, sensor.metric, value, last)
    posted = record_condition_reading(
        session,
        sensor.venue_id,
        zone.id,
        temp,
        humidity,
        actor=None,
        notes=f"{sensor.external_id}: {note}",
        source=source,
        recorded_at=when,
    )
    reading_id = uuid.UUID(posted["reading"]["id"])
    measured = temp if sensor.metric == "temperature_c" else humidity
    sample = SensorReading(
        venue_id=sensor.venue_id,
        sensor_id=sensor.id,
        condition_reading_id=reading_id,
        metric=sensor.metric,
        value=measured,
        recorded_at=when,
    )
    session.add(sample)
    session.flush()
    return {
        "status": "recorded",
        "reading_id": str(reading_id),
        "excursion": posted["excursion"] is not None,
    }


def accept_webhook(sensor_key: str, body: bytes, timestamp: str, signature: str) -> dict:
    with session_scope() as session:
        sensor = _load_by_key(session, sensor_key)
        _authorized(sensor, timestamp, signature, body)
        rows = _parse_readings(body, sensor)
        results = [_record(session, sensor, row["at"], row["value"], "sensor") for row in rows]
        session.commit()
        return {
            "accepted": sum(1 for row in results if row["status"] == "recorded"),
            "duplicates": sum(1 for row in results if row["status"] == "duplicate"),
            "readings": results,
        }


def _columns(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise SensorError("The CSV needs a header row.")
    found: dict[str, str] = {}
    for name in fieldnames:
        label = (name or "").strip().lower()
        if label in _HEADER_SENSOR:
            slot = "sensor"
        elif label in _HEADER_AT:
            slot = "at"
        elif label in _HEADER_METRIC:
            slot = "metric"
        elif label in _HEADER_VALUE:
            slot = "value"
        else:
            raise SensorError("The CSV has an unknown column.")
        if slot in found:
            raise SensorError("The CSV repeats a column.")
        found[slot] = name
    if set(found) != {"sensor", "at", "metric", "value"}:
        raise SensorError("The CSV needs sensor, timestamp, metric, and value columns.")
    return found


def _preview_row(session: Session, venue_id: uuid.UUID, line: int, raw: dict, seen: set[tuple[str, str]]) -> dict:
    external = " ".join((raw.get("sensor") or "").split())
    metric = (raw.get("metric") or "").strip()
    when_text = (raw.get("at") or "").strip()
    value_text = (raw.get("value") or "").strip()
    base = {
        "line": line,
        "sensor": "",
        "external_id": external,
        "at": "",
        "metric": metric,
        "value": value_text,
        "zone": "",
        "excursion": "",
        "duplicate": False,
        "error": "",
    }
    sensor = session.scalar(
        select(Sensor).where(Sensor.venue_id == venue_id, Sensor.external_id == external).limit(1)
    )
    if sensor is None:
        named = session.scalar(select(Sensor).where(Sensor.venue_id == venue_id, Sensor.name == external).limit(1))
        sensor = named
    if sensor is None:
        base["error"] = "Unknown sensor."
        return base
    base["sensor"] = sensor.name
    base["external_id"] = sensor.external_id
    if metric != sensor.metric:
        base["error"] = "Metric does not match the sensor."
        return base
    try:
        when = parse_stamp(when_text)
    except (TypeError, ValueError):
        base["error"] = "Timestamp could not be read."
        return base
    base["at"] = _stamp(when) or ""
    try:
        number = Decimal(value_text)
    except Exception:
        base["error"] = "Value must be a number."
        return base
    zone = session.get(StorageZone, sensor.zone_id)
    if zone is None:
        base["error"] = "Storage zone not found."
        return base
    base["zone"] = zone.name
    key = (str(sensor.id), base["at"])
    stored = session.scalar(
        select(SensorReading.id).where(SensorReading.sensor_id == sensor.id, SensorReading.recorded_at == when).limit(1)
    )
    if stored is not None or key in seen:
        base["duplicate"] = True
    seen.add(key)
    try:
        last = _latest_reading(session, zone.id)
        temp, humidity, _note = paired_reading(zone, sensor.metric, number, last)
        band = excursion_metric(zone, temp, humidity)
    except Rejected as exc:
        base["error"] = exc.message
        return base
    base["value"] = f"{number:.2f}"
    base["excursion"] = band or ""
    return base


def preview_csv(venue_id: uuid.UUID, filename: str, body: bytes) -> dict:
    if len(body) > _MAX_CSV_BYTES:
        raise SensorError("The CSV is too large.")
    try:
        text_body = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SensorError("The CSV must be UTF-8.") from exc
    reader = csv.DictReader(io.StringIO(text_body))
    columns = _columns(reader.fieldnames)
    parsed_rows: list[dict] = []
    with session_scope() as session:
        venue = _venue(session, venue_id)
        seen: set[tuple[str, str]] = set()
        for index, raw in enumerate(reader, start=2):
            if index - 1 > _MAX_ROWS:
                raise SensorError("The CSV has too many rows.")
            mapped = {slot: (raw.get(columns[slot]) or "") for slot in columns}
            parsed_rows.append(_preview_row(session, venue_id, index, mapped, seen))
        if not parsed_rows:
            raise SensorError("The CSV has no rows.")
        user_id, _email = _actor(venue_id)
        sheet = SensorImport(
            venue_id=venue_id,
            filename=_text(filename or "readings.csv", 200, "Filename"),
            status="pending_review",
            rows_json=parsed_rows,
            created_by_user_id=user_id,
        )
        session.add(sheet)
        session.flush()
        _audit(
            session,
            venue,
            "sensor.import_previewed",
            sheet.id,
            None,
            {"filename": sheet.filename, "rows": len(parsed_rows)},
        )
        body_out = _import_public(sheet)
        session.commit()
        return body_out


def _import_public(row: SensorImport) -> dict:
    return {
        "id": str(row.id),
        "filename": row.filename,
        "status": row.status,
        "rows": list(row.rows_json or []),
        "created_at": _stamp(row.created_at),
        "decided_at": _stamp(row.decided_at),
    }


def _sheet(session: Session, venue_id: uuid.UUID, import_id: uuid.UUID) -> SensorImport:
    row = session.get(SensorImport, import_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("import not found")
    return row


def list_imports(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        _venue(session, venue_id)
        rows = session.scalars(
            select(SensorImport).where(SensorImport.venue_id == venue_id).order_by(SensorImport.created_at.desc())
        ).all()
        return {"imports": [_import_public(row) for row in rows]}


def apply_import(venue_id: uuid.UUID, import_id: uuid.UUID) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        sheet = _sheet(session, venue_id, import_id)
        if sheet.status != "pending_review":
            raise SensorError("This import is already decided.", 409)
        rows = list(sheet.rows_json or [])
        if any(row.get("error") for row in rows):
            raise SensorError("Fix the rows with errors, or reject this import.")
        posted = 0
        skipped = 0
        excursions = 0
        for row in rows:
            sensor = session.scalar(
                select(Sensor).where(Sensor.venue_id == venue_id, Sensor.external_id == row["external_id"]).limit(1)
            )
            if sensor is None:
                raise SensorError("Unknown sensor.")
            result = _record(session, sensor, parse_stamp(row["at"]), row["value"], "csv")
            if result["status"] == "duplicate":
                skipped += 1
            else:
                posted += 1
                if result["excursion"]:
                    excursions += 1
        user_id, _email = _actor(venue_id)
        sheet.status = "applied"
        sheet.decided_by_user_id = user_id
        sheet.decided_at = datetime.now(timezone.utc)
        session.flush()
        _audit(
            session,
            venue,
            "sensor.import_applied",
            sheet.id,
            {"status": "pending_review"},
            {"status": "applied", "posted": posted, "skipped": skipped, "excursions": excursions},
        )
        body = _import_public(sheet)
        body["posted"] = posted
        body["skipped"] = skipped
        body["excursions"] = excursions
        session.commit()
        return body


def reject_import(venue_id: uuid.UUID, import_id: uuid.UUID) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        sheet = _sheet(session, venue_id, import_id)
        if sheet.status != "pending_review":
            raise SensorError("This import is already decided.", 409)
        user_id, _email = _actor(venue_id)
        sheet.status = "rejected"
        sheet.decided_by_user_id = user_id
        sheet.decided_at = datetime.now(timezone.utc)
        session.flush()
        _audit(
            session,
            venue,
            "sensor.import_rejected",
            sheet.id,
            {"status": "pending_review"},
            {"status": "rejected"},
        )
        body = _import_public(sheet)
        session.commit()
        return body
