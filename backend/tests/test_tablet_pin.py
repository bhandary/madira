"""Shared-tablet PINs: hashing, roles, lockout, expiry, and venue scope."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.auth import SESSION_COOKIE, issue_session
from madira.csrf import BLOCKED, CSRF_COOKIE, CSRF_HEADER, sign_csrf
from madira.db import SessionLocal, init_db
from madira.domain.tablet import hash_pin, verify_pin
from madira.main import app
from madira.models import AuditEvent, Membership, Organization, SharedTablet, TabletActor, User, Venue
from madira.seed import seed
from madira.tenancy import DEMO_USER_SUB, OWNER, STAFF, ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "tablet-pin-test-secret"


def _ready() -> None:
    init_db()
    seed()
    ensure_demo_tenant()


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    return TestClient(app)


def _ana(client: TestClient) -> str:
    roster = client.get("/team")
    assert roster.status_code == 200, roster.text
    ana = next(row for row in roster.json()["members"] if row["name"] == "Ana")
    return ana["user_id"]


def test_pin_hash_is_salted_and_not_the_pin():
    first = hash_pin("1357")
    second = hash_pin("1357")
    assert first != second
    assert "1357" not in first
    assert first.startswith("scrypt$")
    assert verify_pin("1357", first)
    assert not verify_pin("9999", first)
    assert not verify_pin("1357", "scrypt$not-a-hash")


def test_owner_sets_a_pin_staff_cannot_share_and_a_manager_clears_staff_only(monkeypatch):
    _ready()
    demo = ensure_demo_tenant()
    with _client(monkeypatch) as client:
        missing = client.post("/me/pin", json={"pin": "12"})
        assert missing.status_code == 422
        saved = client.post("/me/pin", json={"pin": "1357"})
        assert saved.status_code == 200, saved.text
        assert saved.json() == {"ok": True, "has_pin": True}
        session = SessionLocal()
        try:
            owner = session.scalar(select(Membership).where(Membership.user_id == demo.user_id, Membership.venue_id == demo.venue_id))
            assert owner is not None
            assert owner.pin_hash
            assert "1357" not in owner.pin_hash
        finally:
            session.close()
        client.cookies.set("madira_demo_persona", "ana")
        assert client.post("/me/pin", json={"pin": "2468"}).status_code == 200
        denied = client.post("/tablet/enable")
        assert denied.status_code == 403
        assert denied.json()["detail"] == "This role cannot do that."
        client.cookies.set("madira_demo_persona", "mia")
        assert client.post("/me/pin", json={"pin": "1470"}).status_code == 200
        ana_id = _ana(client)
        cleared = client.delete(f"/team/members/{ana_id}/pin")
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["has_pin"] is False
        blocked = client.delete(f"/team/members/{demo.user_id}/pin")
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "A manager can only clear a staff PIN."
        client.cookies.set("madira_demo_persona", "owner")
        cleared_own = client.delete(f"/team/members/{demo.user_id}/pin")
        assert cleared_own.status_code == 200, cleared_own.text
        assert cleared_own.json()["has_pin"] is False


def test_pin_switch_cannot_approve_or_open_settings_and_then_expires(monkeypatch, caplog):
    _ready()
    caplog.set_level(logging.INFO, logger="madira.tablet")
    with _client(monkeypatch) as client:
        assert client.get("/settings/llm").status_code == 200
        assert client.post("/me/pin", json={"pin": "1357"}).status_code == 200
        client.cookies.set("madira_demo_persona", "ana")
        assert client.post("/me/pin", json={"pin": "2468"}).status_code == 200
        client.cookies.set("madira_demo_persona", "owner")
        enabled = client.post("/tablet/enable")
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["enabled"] is True
        assert enabled.json()["locked"] is True
        ana_id = next(row["user_id"] for row in enabled.json()["candidates"] if row["name"] == "Ana")
        owner_id = next(row["user_id"] for row in enabled.json()["candidates"] if row["name"] == "Demo Owner")
        switched = client.post("/tablet/unlock", json={"user_id": ana_id, "pin": "2468"})
        assert switched.status_code == 200, switched.text
        assert switched.json()["actor"]["name"] == "Ana"
        assert switched.json()["pin_session"] is True
        assert "2468" not in caplog.text
        denied_pin = client.post("/me/pin", json={"pin": "1111"})
        assert denied_pin.status_code == 403
        assert denied_pin.json()["detail"] == "Sign in to do that."
        settings = client.get("/settings/llm")
        assert settings.status_code == 403
        assert settings.json()["detail"] == "Sign in to do that."
        approve = client.post(f"/procurement/orders/{uuid.uuid4()}/approve", json={})
        assert approve.status_code == 403
        assert approve.json()["detail"] == "Sign in to do that."
        locked = client.post("/tablet/lock")
        assert locked.status_code == 200, locked.text
        assert locked.json()["locked"] is True
        assert client.get("/settings/llm").status_code == 423
        owner = client.post("/tablet/unlock", json={"user_id": owner_id, "pin": "1357"})
        assert owner.status_code == 200, owner.text
        assert owner.json()["actor"]["role"] == OWNER
        assert client.get("/settings/llm").json()["detail"] == "Sign in to do that."
        session = SessionLocal()
        try:
            for row in session.scalars(select(TabletActor)).all():
                row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            session.commit()
        finally:
            session.close()
        assert client.get("/settings/llm").status_code == 423
        assert client.get("/tablet").json()["locked"] is True
        ended = client.post("/tablet/disable", json={"pin": "1357"})
        assert ended.status_code == 200, ended.text
        assert ended.json()["enabled"] is False
        assert client.get("/settings/llm").status_code == 200
        session = SessionLocal()
        try:
            actions = set(
                session.scalars(select(AuditEvent.action).where(AuditEvent.action.in_(["tablet.enable", "tablet.disable"]))).all()
            )
        finally:
            session.close()
        assert actions == {"tablet.enable", "tablet.disable"}


def test_wrong_pins_lock_the_membership_and_the_tablet(monkeypatch, caplog):
    _ready()
    caplog.set_level(logging.INFO, logger="madira.tablet")
    with _client(monkeypatch) as client:
        assert client.post("/me/pin", json={"pin": "1357"}).status_code == 200
        client.cookies.set("madira_demo_persona", "ben")
        assert client.post("/me/pin", json={"pin": "2580"}).status_code == 200
        client.cookies.set("madira_demo_persona", "owner")
        enabled = client.post("/tablet/enable")
        assert enabled.status_code == 200, enabled.text
        ben_id = next(row["user_id"] for row in enabled.json()["candidates"] if row["name"] == "Ben")
        for _ in range(4):
            wrong = client.post("/tablet/unlock", json={"user_id": ben_id, "pin": "0000"})
            assert wrong.status_code == 401
            assert wrong.json()["detail"] == "That PIN is wrong."
        tripped = client.post("/tablet/unlock", json={"user_id": ben_id, "pin": "0000"})
        assert tripped.status_code == 423
        assert tripped.json()["detail"] == "This tablet is locked. Try again later."
        assert "0000" not in caplog.text
        still = client.post("/tablet/unlock", json={"user_id": ben_id, "pin": "2580"})
        assert still.status_code == 423
        session = SessionLocal()
        try:
            member = session.scalar(select(Membership).where(Membership.user_id == uuid.UUID(ben_id)))
            tablet = session.scalar(select(SharedTablet).where(SharedTablet.enabled.is_(True)).order_by(SharedTablet.created_at.desc()))
            assert member is not None and tablet is not None
            assert member.pin_locked_until is not None
            assert tablet.pin_locked_until is not None
            member.pin_locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
            member.pin_failures = 0
            session.commit()
            tablet_id = tablet.id
        finally:
            session.close()
        blocked = client.post("/tablet/unlock", json={"user_id": ben_id, "pin": "2580"})
        assert blocked.status_code == 423
        session = SessionLocal()
        try:
            tablet = session.get(SharedTablet, tablet_id)
            assert tablet is not None
            tablet.pin_locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
            tablet.pin_failures = 0
            session.commit()
        finally:
            session.close()
        opened = client.post("/tablet/unlock", json={"user_id": ben_id, "pin": "2580"})
        assert opened.status_code == 200, opened.text
        session = SessionLocal()
        try:
            actions = session.scalars(select(AuditEvent.action).where(AuditEvent.action == "tablet.pin.lockout")).all()
        finally:
            session.close()
        assert actions


def test_a_pin_from_another_venue_cannot_unlock_this_tablet(monkeypatch):
    _ready()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        org = Organization(name="Other House", slug=f"other-{uuid.uuid4().hex[:8]}")
        session.add(org)
        session.flush()
        venue = Venue(organization_id=org.id, name="Other House", slug=f"bar-{uuid.uuid4().hex[:8]}")
        session.add(venue)
        session.flush()
        user = User(
            google_sub=f"other-{uuid.uuid4().hex}",
            email=f"{uuid.uuid4().hex}@example.com",
            name="Other Staff",
            picture="",
            created_at=datetime.now(timezone.utc),
            last_login_at=datetime.now(timezone.utc),
        )
        session.add(user)
        session.flush()
        session.add(
            Membership(
                user_id=user.id,
                venue_id=venue.id,
                role=STAFF,
                position="server",
                pin_hash=hash_pin("1357"),
            )
        )
        session.commit()
        other_id = user.id
        other_sub = user.google_sub
    finally:
        session.close()
    with _client(monkeypatch) as client:
        assert client.post("/me/pin", json={"pin": "1357"}).status_code == 200
        assert client.post("/tablet/enable").status_code == 200
        foreign = client.post("/tablet/unlock", json={"user_id": str(other_id), "pin": "1357"})
        assert foreign.status_code == 404
        assert foreign.json()["detail"] == "That person is not on this tablet."
        client.cookies.set(SESSION_COOKIE, issue_session(other_sub))
        client.cookies.pop("madira_demo_persona", None)
        state = client.get("/tablet")
        assert state.status_code == 200, state.text
        assert state.json()["enabled"] is False
        lessons = client.get("/training/lessons")
        assert lessons.status_code == 200, lessons.text
        assert lessons.status_code != 423
    assert other_id != demo.user_id


def test_pin_write_keeps_the_csrf_check(monkeypatch):
    _ready()
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    monkeypatch.setenv("MADIRA_CSRF_TEST_RAW", "1")
    token = issue_session(DEMO_USER_SUB)
    signed = sign_csrf(token)
    assert signed
    with TestClient(app) as client:
        blocked = client.post("/me/pin", json={"pin": "1357"}, cookies={SESSION_COOKIE: token})
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == BLOCKED
        allowed = client.post(
            "/me/pin",
            json={"pin": "1357"},
            cookies={SESSION_COOKIE: token, CSRF_COOKIE: signed},
            headers={CSRF_HEADER: signed, "Origin": "http://localhost:3000"},
        )
        assert allowed.status_code == 200, allowed.text


def test_migration_0029_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0029_tablet_pin.py").read_text()
    assert 'revision: str = "0029_tablet_pin"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "0028_jobs"' in source
    assert source.count('_enable_rls("') == 2
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "if not _is_postgres():" in source
    assert "venue_isolation" in source
    db = tmp_path / "tablet.db"
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
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0030_catalog_embeddings"
    tables = set(sa.inspect(conn).get_table_names())
    assert "shared_tablets" in tables
    assert "tablet_actors" in tables
    columns = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(memberships)"))}
    assert {"pin_hash", "pin_failures", "pin_locked_until"} <= columns

command.downgrade(cfg, "0028_jobs")
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "shared_tablets" not in tables
    assert "tablet_actors" not in tables
    columns = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(memberships)"))}
    assert "pin_hash" not in columns
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0028_jobs"

command.upgrade(cfg, "head")
with engine.connect() as conn:
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0030_catalog_embeddings"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
