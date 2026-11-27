"""Signed sensor webhook: venue comes from the sensor, and a reading posts once."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from madira.auth import SESSION_COOKIE, issue_session
from madira.db import SessionLocal, init_db
from madira.main import app
from madira.models import (
    AuditEvent,
    ConditionExcursion,
    ConditionReading,
    Membership,
    Sensor,
    SensorReading,
    StorageZone,
    User,
    Venue,
)
from madira.seed import seed
from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "sensor-webhook-test-secret"


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _sign(secret: str, body: bytes, stamp: int) -> str:
    message = f"{stamp}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _zone_id(venue_id, name: str) -> str:
    session = SessionLocal()
    try:
        zone = session.scalar(select(StorageZone).where(StorageZone.venue_id == venue_id, StorageZone.name == name))
        assert zone is not None
        return str(zone.id)
    finally:
        session.close()


def _post(client: TestClient, key: str, secret: str, body: bytes, stamp: int | None = None):
    when = int(datetime.now(timezone.utc).timestamp()) if stamp is None else stamp
    return client.post(
        f"/sensors/webhook/{key}",
        content=body,
        headers={
            "X-Madira-Timestamp": str(when),
            "X-Madira-Signature": _sign(secret, body, when),
            "Content-Type": "application/json",
        },
    )


def test_webhook_signature_replay_dedupe_and_excursion(caplog):
    demo = _demo()
    zone_id = _zone_id(demo.venue_id, "Main Cellar")
    external = f"probe-{uuid.uuid4().hex[:8]}"
    caplog.set_level(logging.DEBUG)
    with TestClient(app) as client:
        created = client.post(
            "/sensors",
            json={"name": "Cellar probe", "zone_id": zone_id, "metric": "temperature_c", "external_id": external},
        )
        assert created.status_code == 200, created.text
        secret = created.json()["secret"]
        assert secret
        assert created.json()["secret_last4"] == secret[-4:]
        listed = client.get("/sensors")
        assert listed.status_code == 200
        assert secret not in listed.text
        assert "secret_ciphertext" not in listed.text
        session = SessionLocal()
        try:
            before = session.scalar(select(func.count()).select_from(ConditionExcursion).where(ConditionExcursion.venue_id == demo.venue_id))
            stored = session.scalar(select(Sensor).where(Sensor.external_id == external))
            assert stored is not None
            assert secret not in stored.secret_ciphertext
        finally:
            session.close()
        at = datetime(2020, 1, 15, tzinfo=timezone.utc).isoformat()
        body = json.dumps({"readings": [{"at": at, "value": 30, "metric": "temperature_c"}]}).encode()
        bad = client.post(
            f"/sensors/webhook/{created.json()['sensor_key']}",
            content=body,
            headers={"X-Madira-Timestamp": str(int(datetime.now(timezone.utc).timestamp())), "X-Madira-Signature": "0" * 64},
        )
        assert bad.status_code == 401
        assert secret not in bad.text
        stale = int((datetime.now(timezone.utc) - timedelta(minutes=6)).timestamp())
        assert _post(client, created.json()["sensor_key"], secret, body, stale).status_code == 401
        extra = json.dumps({"readings": [{"at": at, "value": 30, "metric": "temperature_c"}], "venue_id": str(demo.venue_id)}).encode()
        assert _post(client, created.json()["sensor_key"], secret, extra).status_code == 422
        unknown = json.dumps(
            {"readings": [{"external_id": "someone-else", "at": at, "value": 30, "metric": "temperature_c"}]}
        ).encode()
        assert _post(client, created.json()["sensor_key"], secret, unknown).status_code == 422
        ok = _post(client, created.json()["sensor_key"], secret, body)
        assert ok.status_code == 200, ok.text
        assert ok.json()["accepted"] == 1
        assert secret not in ok.text
        again = _post(client, created.json()["sensor_key"], secret, body)
        assert again.status_code == 200, again.text
        assert again.json()["duplicates"] == 1
        assert again.json()["accepted"] == 0
    assert secret not in caplog.text
    session = SessionLocal()
    try:
        sensor = session.scalar(select(Sensor).where(Sensor.external_id == external))
        assert sensor is not None
        readings = session.scalars(select(SensorReading).where(SensorReading.sensor_id == sensor.id)).all()
        assert len(readings) == 1
        condition = session.get(ConditionReading, readings[0].condition_reading_id)
        assert condition is not None
        assert condition.venue_id == demo.venue_id
        assert condition.source == "sensor"
        assert condition.zone_id == uuid.UUID(zone_id)
        excursion = session.scalar(
            select(ConditionExcursion).where(ConditionExcursion.reading_id == condition.id)
        )
        assert excursion is not None
        assert excursion.metric == "temp_high"
        assert excursion.venue_id == demo.venue_id
        after = session.scalar(select(func.count()).select_from(ConditionExcursion).where(ConditionExcursion.venue_id == demo.venue_id))
        assert after == before + 1
    finally:
        session.close()


def test_webhook_uses_the_sensor_venue_without_a_session(monkeypatch):
    demo = _demo()
    other_id = uuid.uuid4()
    session = SessionLocal()
    try:
        home = session.get(Venue, demo.venue_id)
        other = Venue(
            id=other_id,
            organization_id=home.organization_id,
            name="Probe room",
            slug=f"probe-{other_id.hex[:8]}",
            timezone="America/Los_Angeles",
            invite_delivery="draft_only",
            jurisdiction="US-CA",
        )
        session.add(other)
        session.flush()
        zone = StorageZone(
            venue_id=other_id,
            name="Other cellar",
            target_temp_min_c=12,
            target_temp_max_c=14,
            target_humidity_min_pct=60,
            target_humidity_max_pct=75,
        )
        session.add(zone)
        session.commit()
        zone_id = zone.id
    finally:
        session.close()
    from madira.domain.sensors.service import create_sensor
    from madira.tenancy import RequestContext, bind, reset

    token = bind(
        RequestContext(
            user_id=demo.user_id,
            email="owner@maison-madira.demo",
            name="Owner",
            venue_id=other_id,
            organization_id=demo.organization_id,
            role=OWNER,
        )
    )
    try:
        created = create_sensor(other_id, name="Other probe", zone_id=zone_id, metric="temperature_c", external_id="other-probe")
    finally:
        reset(token)
    secret = created["secret"]
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-sensor")
    at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    body = json.dumps({"readings": [{"at": at, "value": 13, "metric": "temperature_c"}]}).encode()
    with TestClient(app) as client:
        denied = client.get("/sensors")
        assert denied.status_code == 401
        accepted = _post(client, created["sensor_key"], secret, body)
        assert accepted.status_code == 200, accepted.text
        assert secret not in accepted.text
    session = SessionLocal()
    try:
        reading = session.scalar(select(SensorReading).where(SensorReading.venue_id == other_id))
        assert reading is not None
        condition = session.get(ConditionReading, reading.condition_reading_id)
        assert condition is not None
        assert condition.venue_id == other_id
        assert session.scalar(select(SensorReading.id).where(SensorReading.venue_id == demo.venue_id, SensorReading.sensor_id == uuid.UUID(created["id"]))) is None
    finally:
        session.close()


def test_sensor_rbac(monkeypatch):
    demo = _demo()
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    zone_id = _zone_id(demo.venue_id, "Main Cellar")
    session = SessionLocal()
    try:
        def add_user(sub: str, role: str, venue_id):
            user = User(
                google_sub=sub,
                email=f"{sub}@example.com",
                name=sub,
                picture="",
                created_at=datetime.now(timezone.utc),
                last_login_at=datetime.now(timezone.utc),
            )
            session.add(user)
            session.flush()
            session.add(Membership(user_id=user.id, venue_id=venue_id, role=role))
            return user

        suffix = uuid.uuid4().hex[:8]
        staff = add_user(f"sensor-staff-{suffix}", STAFF, demo.venue_id)
        sommelier = add_user(f"sensor-somm-{suffix}", SOMMELIER, demo.venue_id)
        auditor = add_user(f"sensor-auditor-{suffix}", AUDITOR, demo.venue_id)
        manager = add_user(f"sensor-manager-{suffix}", MANAGER, demo.venue_id)
        session.commit()
        subs = {
            "staff": staff.google_sub,
            "sommelier": sommelier.google_sub,
            "auditor": auditor.google_sub,
            "manager": manager.google_sub,
        }
    finally:
        session.close()

    def cookie(client: TestClient, sub: str):
        client.cookies.set(SESSION_COOKIE, issue_session(sub))

    with TestClient(app) as client:
        cookie(client, subs["staff"])
        assert client.get("/sensors").status_code == 403
        assert client.post("/sensors", json={"name": "Nope", "zone_id": zone_id, "metric": "temperature_c", "external_id": "nope"}).status_code == 403
        cookie(client, subs["sommelier"])
        assert client.get("/sensors").status_code == 200
        assert client.post("/sensors", json={"name": "Nope", "zone_id": zone_id, "metric": "temperature_c", "external_id": "nope"}).status_code == 403
        cookie(client, subs["auditor"])
        assert client.get("/sensors").status_code == 200
        assert client.post("/sensors", json={"name": "Nope", "zone_id": zone_id, "metric": "temperature_c", "external_id": "nope"}).status_code == 403
        cookie(client, subs["manager"])
        created = client.post(
            "/sensors",
            json={"name": "Manager probe", "zone_id": zone_id, "metric": "humidity_pct", "external_id": f"mgr-{suffix}"},
        )
        assert created.status_code == 200, created.text
        assert created.json()["secret"]
        hidden = client.get("/sensors")
        assert created.json()["secret"] not in hidden.text
        session = SessionLocal()
        try:
            event = session.scalar(
                select(AuditEvent).where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "sensor.created").order_by(AuditEvent.seq.desc())
            )
            assert event is not None
            assert created.json()["secret"] not in json.dumps(event.after_json)
        finally:
            session.close()


def test_migration_0025_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0025_sensors_reminders.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0024_pos"' in source
    assert source.count('_enable_rls("') == 6
    assert "sensor_webhook" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "if not _is_postgres():" in source
    db = tmp_path / "sensors.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "head")
engine = sa.create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0028_jobs"
    tables = set(sa.inspect(conn).get_table_names())
    assert {"sensors", "sensor_readings", "sensor_imports", "venue_licenses", "reminder_rules", "reminder_states"} <= tables
    venues = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(venues)"))}
    assert "jurisdiction" in venues

command.downgrade(cfg, "0024_pos")
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "sensors" not in tables
    assert "reminder_states" not in tables
    venues = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(venues)"))}
    assert "jurisdiction" not in venues
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0024_pos"

command.upgrade(cfg, "head")
with engine.connect() as conn:
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0028_jobs"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
