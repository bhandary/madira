"""Tasting sessions: CRUD, the old tasting rows, a valid calendar file, roles, and venues."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.agents.tools import get_tasting, plan_tasting
from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.tastings.service import build_ics, create_session, ics_text
from madira.main import app
from madira.models import AuditEvent, Membership, Supplier, User, Venue
from madira.seed import seed
from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, bind, ensure_demo_tenant, reset

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "tasting-sessions-test-secret"


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _member(session, google_sub: str, email: str, venue_id, role: str) -> None:
    user = session.scalar(select(User).where(User.google_sub == google_sub))
    now = utcnow()
    if user is None:
        user = User(google_sub=google_sub, email=email, name=email, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
    membership = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id))
    if membership is None:
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=role))
    else:
        membership.role = role


def test_ics_is_rfc5545_and_stable():
    notes = "Cellar, hold; draft only — " + ("long note " * 12)
    first = build_ics(
        "Loire, new releases",
        "2026-12-01T15:00",
        "2026-12-01T17:00",
        "Maison Madira cellar",
        notes,
        uid="session@madira.local",
        dtstamp="2026-11-25T02:00:00Z",
    )
    second = build_ics(
        "Loire, new releases",
        "2026-12-01T15:00",
        "2026-12-01T17:00",
        "Maison Madira cellar",
        notes,
        uid="session@madira.local",
        dtstamp="2026-11-25T02:00:00Z",
    )
    assert first == second
    assert first.startswith("BEGIN:VCALENDAR\r\n")
    assert first.endswith("END:VCALENDAR\r\n")
    assert "VERSION:2.0" in first
    assert "PRODID:-//Maison Madira//Madira//EN" in first
    assert "CALSCALE:GREGORIAN" in first
    assert "METHOD:PUBLISH" in first
    assert "UID:session@madira.local" in first
    assert "DTSTAMP:20261125T020000Z" in first
    assert "DTSTART:20261201T150000Z" in first
    assert "DTEND:20261201T170000Z" in first
    assert "SUMMARY:Loire\\, new releases" in first
    for line in first.split("\r\n"):
        if line:
            assert len(line.encode("utf-8")) <= 75


def test_session_crud_audits_edits_and_downloads_ics():
    demo = _demo()
    created = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title="CRUD Loire tasting",
        starts_at="2026-12-01T15:00",
        ends_at="2026-12-01T17:00",
    )
    draft = created["draft"]
    assert draft["sent"] is False
    assert "ics" not in created["tastings"][0]
    text = ics_text(demo.venue_id, draft["id"])
    assert text == draft["ics"]
    assert "DTSTART:20261201T150000Z" in text

    with TestClient(app) as client:
        patched = client.patch(f"/tastings/{draft['id']}", json={"title": "CRUD Loire held", "status": "held"})
        assert patched.status_code == 200, patched.text
        assert patched.json()["session"]["title"] == "CRUD Loire held"
        assert patched.json()["session"]["status"] == "held"
        calendar = client.get(f"/tastings/{draft['id']}.ics")
        assert calendar.status_code == 200
        assert calendar.headers["content-type"].startswith("text/calendar")
        assert calendar.text.startswith("BEGIN:VCALENDAR")
        removed = client.delete(f"/tastings/{draft['id']}")
        assert removed.status_code == 200
        missing = client.get(f"/tastings/{draft['id']}")
        assert missing.status_code == 404

    session = SessionLocal()
    try:
        actions = set(
            session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.venue_id == demo.venue_id,
                    AuditEvent.entity_id == draft["id"],
                )
            )
        )
    finally:
        session.close()
    assert "tasting_session.created" in actions
    assert "tasting_session.updated" in actions
    assert "tasting_session.deleted" in actions


def test_plan_and_get_tools_use_the_venue():
    demo = _demo()
    token = bind(demo)
    try:
        import json

        planned = json.loads(
            plan_tasting(supplier="Kermit Lynch Wine Merchant", when="2026-12-04T15:00", title="Tool Loire tasting")
        )
        assert planned["draft"]["sent"] is False
        assert "DTSTART:20261204T150000Z" in planned["draft"]["ics"]
        listed = json.loads(get_tasting(""))
        assert "Tool Loire tasting" in listed["tastings"][0]["title"] or any(
            row["title"] == "Tool Loire tasting" for row in listed["tastings"]
        )
        detail = json.loads(get_tasting(str(planned["draft"]["id"])))
        assert detail["session"]["title"] == "Tool Loire tasting"
        assert "SampleCard" in json.dumps(detail["a2ui_operations"]) or detail["samples"] == []
    finally:
        reset(token)


def test_roles_and_other_venues():
    demo = _demo()
    session = SessionLocal()
    try:
        other = Venue(
            organization_id=demo.organization_id,
            name="Other Tastings",
            slug=f"other-tastings-{uuid.uuid4().hex[:8]}",
        )
        session.add(other)
        session.flush()
        session.add(Supplier(venue_id=other.id, name="Other House Wines", kind="distributor"))
        _member(session, "staff-tastings", "staff-tastings@example.com", demo.venue_id, STAFF)
        _member(session, "auditor-tastings", "auditor-tastings@example.com", demo.venue_id, AUDITOR)
        _member(session, "manager-tastings", "manager-tastings@example.com", demo.venue_id, MANAGER)
        _member(session, "sommelier-tastings", "sommelier-tastings@example.com", demo.venue_id, SOMMELIER)
        session.commit()
        other_id = other.id
    finally:
        session.close()

    hidden = create_session(
        other_id,
        supplier_name="Other House Wines",
        title="B secret tasting session",
        starts_at="2026-12-02T15:00",
        ends_at="2026-12-02T16:00",
    )

    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "ana")
        denied = client.get("/tastings")
        assert denied.status_code == 403

        client.cookies.set("madira_demo_persona", "owner")
        visible = client.get("/tastings")
        assert visible.status_code == 200
        assert "B secret tasting session" not in visible.text
        foreign = client.get(f"/tastings/{hidden['draft']['id']}.ics")
        assert foreign.status_code == 404

    monkeypatch_secret = os.environ.get("MADIRA_AUTH_SECRET")
    os.environ["MADIRA_AUTH_SECRET"] = AUTH_SECRET
    try:
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE, issue_session("staff-tastings"))
            assert client.get("/tastings").status_code == 403

            client.cookies.set(SESSION_COOKIE, issue_session("auditor-tastings"))
            assert client.get("/tastings").status_code == 200
            blocked = client.post(
                "/tastings",
                json={"supplier_name": "Kermit Lynch Wine Merchant", "title": "Auditor tasting", "starts_at": "2026-12-05T15:00"},
            )
            assert blocked.status_code == 403

            client.cookies.set(SESSION_COOKIE, issue_session("manager-tastings"))
            managed = client.post(
                "/tastings",
                json={"supplier_name": "Kermit Lynch Wine Merchant", "title": "Manager tasting", "starts_at": "2026-12-06T15:00"},
            )
            assert managed.status_code == 200, managed.text

            client.cookies.set(SESSION_COOKIE, issue_session("sommelier-tastings"))
            poured = client.post(
                "/tastings",
                json={"supplier_name": "Kermit Lynch Wine Merchant", "title": "Sommelier tasting", "starts_at": "2026-12-07T15:00"},
            )
            assert poured.status_code == 200, poured.text
    finally:
        if monkeypatch_secret is None:
            os.environ.pop("MADIRA_AUTH_SECRET", None)
        else:
            os.environ["MADIRA_AUTH_SECRET"] = monkeypatch_secret


def test_migration_0021_moves_tastings_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0021_tasting_sessions.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0020_supplier_offers"' in source
    assert source.count('_enable_rls("') == 3
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "venue_isolation" in source
    assert "if not _is_postgres():" in source
    db = tmp_path / "tastings.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import uuid
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "0020_supplier_offers")
engine = sa.create_engine(os.environ["DATABASE_URL"])
venue_id = uuid.uuid4()
supplier_id = uuid.uuid4()
tasting_id = uuid.uuid4()
with engine.begin() as conn:
    org_id = conn.execute(sa.text("SELECT id FROM organizations WHERE slug = 'maison-madira'")).scalar_one()
    venue_id = conn.execute(sa.text("SELECT id FROM venues WHERE slug = 'maison-madira'")).scalar_one()
    supplier_id = uuid.uuid4()
    tasting_id = uuid.uuid4()
    conn.execute(
        sa.text(
            "INSERT INTO suppliers (id, venue_id, name, kind, contact_email, notes) "
            "VALUES (:id, :venue_id, 'Migration House', 'importer', '', '')"
        ),
        {"id": str(supplier_id), "venue_id": venue_id},
    )
    conn.execute(
        sa.text(
            "INSERT INTO tastings (id, venue_id, supplier_id, title, starts_at, ends_at, location, notes, ics) "
            "VALUES (:id, :venue_id, :supplier_id, 'Migrated Loire', '2026-12-01 15:00:00', '2026-12-01 17:00:00', 'cellar', 'keep me', 'BEGIN:VCALENDAR')"
        ),
        {"id": str(tasting_id), "venue_id": venue_id, "supplier_id": str(supplier_id)},
    )

command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0027_pairing_cache"
    tables = set(sa.inspect(conn).get_table_names())
    assert "tastings" not in tables
    assert "tasting_sessions" in tables
    assert "samples" in tables
    row = conn.execute(sa.text("SELECT title, status, location, notes FROM tasting_sessions")).one()
    assert row.title == "Migrated Loire"
    assert row.status == "planned"
    assert row.location == "cellar"
    assert row.notes == "keep me"

command.downgrade(cfg, "0020_supplier_offers")
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "tasting_sessions" not in tables
    assert "samples" not in tables
    assert "tastings" in tables
    restored = conn.execute(sa.text("SELECT title, ics, supplier_id FROM tastings")).one()
    assert restored.title == "Migrated Loire"
    assert "BEGIN:VCALENDAR" in restored.ics
    assert restored.supplier_id is not None

command.upgrade(cfg, "head")
with engine.connect() as conn:
    assert conn.execute(sa.text("SELECT title FROM tasting_sessions")).scalar_one() == "Migrated Loire"
    assert "tastings" not in set(sa.inspect(conn).get_table_names())
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
