"""CSV sensor import previews, applies through the existing excursion path, or rejects."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.main import app
from madira.models import AuditEvent, ConditionExcursion, ConditionReading, Sensor, SensorReading, StorageZone
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _zone_id(venue_id) -> str:
    session = SessionLocal()
    try:
        zone = session.scalar(select(StorageZone).where(StorageZone.venue_id == venue_id, StorageZone.name == "Main Cellar"))
        assert zone is not None
        return str(zone.id)
    finally:
        session.close()


def test_csv_preview_apply_reject_and_dedupe():
    demo = _demo()
    zone_id = _zone_id(demo.venue_id)
    external = f"csv-{uuid.uuid4().hex[:8]}"
    at = datetime(2020, 1, 15, tzinfo=timezone.utc).isoformat()
    with TestClient(app) as client:
        created = client.post(
            "/sensors",
            json={"name": "CSV probe", "zone_id": zone_id, "metric": "temperature_c", "external_id": external},
        )
        assert created.status_code == 200, created.text
        secret = created.json()["secret"]
        good = (
            "sensor,timestamp,metric,value\n"
            f"{external},{at},temperature_c,30\n"
            f"{external},{at},temperature_c,30\n"
        ).encode()
        preview = client.post(
            "/sensors/imports",
            files={"file": ("readings.csv", good, "text/csv")},
            data={"filename": "readings.csv"},
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["status"] == "pending_review"
        assert secret not in preview.text
        assert body["rows"][0]["excursion"] == "temp_high"
        assert body["rows"][1]["duplicate"] is True
        bad = client.post(
            "/sensors/imports",
            files={"file": ("bad.csv", b"sensor,timestamp,metric,value\nmissing,2026-01-01T00:00:00Z,temperature_c,30\n", "text/csv")},
            data={"filename": "bad.csv"},
        )
        assert bad.status_code == 200, bad.text
        assert bad.json()["rows"][0]["error"] == "Unknown sensor."
        refused = client.post(f"/sensors/imports/{bad.json()['id']}/apply")
        assert refused.status_code == 422
        rejected = client.post(f"/sensors/imports/{bad.json()['id']}/reject")
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "rejected"
        applied = client.post(f"/sensors/imports/{body['id']}/apply")
        assert applied.status_code == 200, applied.text
        assert applied.json()["posted"] == 1
        assert applied.json()["skipped"] == 1
        assert applied.json()["excursions"] == 1
        second = client.post(f"/sensors/imports/{body['id']}/apply")
        assert second.status_code == 409
    session = SessionLocal()
    try:
        sensor = session.scalar(select(Sensor).where(Sensor.external_id == external))
        assert sensor is not None
        rows = session.scalars(select(SensorReading).where(SensorReading.sensor_id == sensor.id)).all()
        assert len(rows) == 1
        condition = session.get(ConditionReading, rows[0].condition_reading_id)
        assert condition is not None and condition.source == "csv"
        excursion = session.scalar(select(ConditionExcursion).where(ConditionExcursion.reading_id == condition.id))
        assert excursion is not None and excursion.metric == "temp_high"
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "sensor.import_applied").order_by(AuditEvent.seq.desc())
        )
        assert event is not None
        assert secret not in str(event.after_json)
    finally:
        session.close()
