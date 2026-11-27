"""The 86 flag is a counted action, audited, and limited to this venue."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.catalog.service import ensure_sku
from madira.main import app
from madira.models import AuditEvent, Membership, Sku, User, Venue
from madira.seed import seed
from madira.tenancy import AUDITOR, DEMO_USER_SUB, ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "eighty-six-test-secret"


def _auditor(venue_id) -> None:
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.google_sub == "eighty-six-auditor"))
        if user is None:
            user = User(
                google_sub="eighty-six-auditor",
                email="eighty-six-auditor@example.com",
                name="Eighty Auditor",
                picture="",
                created_at=utcnow(),
                last_login_at=utcnow(),
            )
            session.add(user)
            session.flush()
        member = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id))
        if member is None:
            session.add(Membership(user_id=user.id, venue_id=venue_id, role=AUDITOR))
        else:
            member.role = AUDITOR
        session.commit()
    finally:
        session.close()


def test_eighty_six_is_audited_idempotent_and_scoped(monkeypatch):
    init_db()
    seed()
    demo = ensure_demo_tenant()
    _auditor(demo.venue_id)
    session = SessionLocal()
    try:
        sku = session.scalar(select(Sku).where(Sku.venue_id == demo.venue_id, Sku.barcode == "W-MUS-01"))
        sku.eighty_sixed_at = None
        sku.eighty_sixed_by_user_id = None
        other = session.scalar(select(Venue).where(Venue.slug == "other-eighty-six"))
        if other is None:
            other = Venue(organization_id=demo.organization_id, name="Other Eighty", slug="other-eighty-six")
            session.add(other)
            session.flush()
        foreign = ensure_sku(
            session,
            other.id,
            category="wine",
            producer="Other House",
            name="Other House Bottle",
            grape="Gamay",
            barcode="W-OTH-86",
            par=1,
            cost=1000,
        )
        foreign_id = foreign.id
        sku_id = sku.id
        session.commit()
    finally:
        session.close()

    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, issue_session(DEMO_USER_SUB))
        session = SessionLocal()
        try:
            before = session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "sku.eighty_six", AuditEvent.entity_id == sku_id)
            )
        finally:
            session.close()
        flagged = client.post(f"/cellar/skus/{sku_id}/86")
        assert flagged.status_code == 200, flagged.text
        assert flagged.json()["eighty_sixed"] is True
        assert flagged.json()["eighty_sixed_at"]
        assert "cost" not in flagged.text.lower()
        again = client.post(f"/cellar/skus/{sku_id}/86")
        assert again.status_code == 200
        session = SessionLocal()
        try:
            count = session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "sku.eighty_six", AuditEvent.entity_id == sku_id)
            )
            assert count == before + 1
        finally:
            session.close()
        cleared = client.delete(f"/cellar/skus/{sku_id}/86")
        assert cleared.status_code == 200
        assert cleared.json()["eighty_sixed"] is False
        session = SessionLocal()
        try:
            cleared_count = session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.venue_id == demo.venue_id,
                    AuditEvent.action == "sku.eighty_six_clear",
                    AuditEvent.entity_id == sku_id,
                )
            )
            assert cleared_count == 1
        finally:
            session.close()
        missing = client.post(f"/cellar/skus/{uuid.uuid4()}/86")
        assert missing.status_code == 404
        foreign_flag = client.post(f"/cellar/skus/{foreign_id}/86")
        assert foreign_flag.status_code == 404

        client.cookies.pop(SESSION_COOKIE)
        client.cookies.set("madira_demo_persona", "ana")
        assert client.post(f"/cellar/skus/{sku_id}/86").status_code == 403
        client.cookies.pop("madira_demo_persona")
        client.cookies.set(SESSION_COOKIE, issue_session("eighty-six-auditor"))
        assert client.post(f"/cellar/skus/{sku_id}/86").status_code == 403
        assert client.delete(f"/cellar/skus/{sku_id}/86").status_code == 403


def test_migration_0017_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0017_briefings.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0016_training_content"' in source
    assert source.count('_enable_rls("') == 2
    assert "if not _is_postgres():" in source
    db = tmp_path / "briefings.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "0016_training_content")
engine = sa.create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    venues = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(venues)"))}
    assert "timezone" not in venues
    tables = set(sa.inspect(conn).get_table_names())
    assert "briefings" not in tables

command.upgrade(cfg, "0017_briefings")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0017_briefings"
    venues = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(venues)"))}
    assert {"timezone", "briefing_hour"} <= venues
    skus = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(skus)"))}
    assert {"eighty_sixed_at", "eighty_sixed_by_user_id"} <= skus
    dishes = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(dishes)"))}
    assert "is_special" in dishes
    tables = set(sa.inspect(conn).get_table_names())
    assert {"briefings", "briefing_acks"} <= tables

command.downgrade(cfg, "0016_training_content")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0016_training_content"
    venues = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(venues)"))}
    assert "timezone" not in venues
    assert "briefing_hour" not in venues
    skus = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(skus)"))}
    assert "eighty_sixed_at" not in skus
    dishes = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(dishes)"))}
    assert "is_special" not in dishes
    tables = set(sa.inspect(conn).get_table_names())
    assert "briefings" not in tables
    assert "briefing_acks" not in tables

command.upgrade(cfg, "0017_briefings")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0017_briefings"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
