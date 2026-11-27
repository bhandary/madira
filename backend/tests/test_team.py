"""Roster, invites, the manager staff-only rule, sign-in acceptance, and migration 0018."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from madira.auth import SESSION_COOKIE, issue_session, upsert_google_user, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.errors import DraftFailed
from madira.domain.team.service import remove_membership, update_membership
from madira.main import app
from madira.models import AuditEvent, Membership, Organization, User, Venue, VenueInvite
from madira.seed import seed
from madira.tenancy import DEMO_USER_SUB, OWNER, SOMMELIER, STAFF, RequestContext, bind, ensure_demo_tenant, reset

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "team-test-secret"


def _ready() -> None:
    init_db()
    seed()
    ensure_demo_tenant()


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    return TestClient(app)


def _member(google_sub: str, email: str, venue_id, role: str, position: str | None = None) -> User:
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.google_sub == google_sub))
        now = utcnow()
        if user is None:
            user = User(google_sub=google_sub, email=email, name=email, picture="", created_at=now, last_login_at=now)
            session.add(user)
            session.flush()
        membership = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id))
        if membership is None:
            session.add(Membership(user_id=user.id, venue_id=venue_id, role=role, position=position))
        else:
            membership.role = role
            membership.position = position
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def test_owner_invites_and_a_manager_can_invite_staff_only(monkeypatch):
    _ready()
    demo = ensure_demo_tenant()
    address = f"new.server.{uuid.uuid4().hex}@example.com"
    sommelier = _member(f"team-sommelier-{uuid.uuid4().hex}", f"sommelier.{uuid.uuid4().hex}@example.com", demo.venue_id, SOMMELIER)
    with _client(monkeypatch) as client:
        invited = client.post("/team/invites", json={"email": address, "role": "Staff", "position": "server"})
        assert invited.status_code == 200, invited.text
        assert invited.json()["email"] == address
        duplicate = client.post("/team/invites", json={"email": address.upper(), "role": "Staff", "position": "bartender"})
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "This person already has an active invite."
        roster = client.get("/team")
        assert roster.status_code == 200
        assert any(row["email"] == address for row in roster.json()["invites"])
        client.cookies.set("madira_demo_persona", "mia")
        for role in ("Manager", "Owner", "Sommelier"):
            blocked = client.post("/team/invites", json={"email": f"{role}.{uuid.uuid4().hex}@example.com", "role": role})
            assert blocked.status_code == 403, blocked.text
            assert blocked.json()["detail"] == "A manager can only invite staff."
        staff_invite = client.post(
            "/team/invites",
            json={"email": f"mia.staff.{uuid.uuid4().hex}@example.com", "role": "Staff", "position": "host"},
        )
        assert staff_invite.status_code == 200, staff_invite.text
        client.cookies.set("madira_demo_persona", "ana")
        denied = client.post("/team/invites", json={"email": f"ana.{uuid.uuid4().hex}@example.com", "role": "Staff", "position": "server"})
        assert denied.status_code == 403
        assert denied.json()["detail"] == "This role cannot do that."
        client.cookies.pop("madira_demo_persona")
        client.cookies.set(SESSION_COOKIE, issue_session(sommelier.google_sub))
        assert client.get("/team").status_code == 200
        assert client.get("/team/progress").status_code == 200
        blocked_sommelier = client.post(
            "/team/invites",
            json={"email": f"from.sommelier.{uuid.uuid4().hex}@example.com", "role": "Staff", "position": "server"},
        )
        assert blocked_sommelier.status_code == 403
        client.cookies.delete(SESSION_COOKIE)
        owner = client.get("/team").json()
        owner_id = next(row["user_id"] for row in owner["members"] if row["role"] == "Owner")
        client.cookies.set("madira_demo_persona", "mia")
        manager_blocked = client.patch(f"/team/members/{owner_id}", json={"role": "Staff", "position": "server"})
        assert manager_blocked.status_code == 403
        assert manager_blocked.json()["detail"] == "A manager can only assign staff."
        client.cookies.pop("madira_demo_persona")
        invite_id = invited.json()["id"]
        revoked = client.post(f"/team/invites/{invite_id}/revoke")
        assert revoked.status_code == 200, revoked.text
        again = client.post("/team/invites", json={"email": address, "role": "Sommelier"})
        assert again.status_code == 200, again.text
    session = SessionLocal()
    try:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "team.invite")
        ).all()
        assert any((event.after_json or {}).get("email") == address for event in events)
    finally:
        session.close()


def test_the_last_owner_cannot_be_demoted_or_removed():
    _ready()
    session = SessionLocal()
    try:
        org = Organization(name="Solo House", slug=f"solo-{uuid.uuid4().hex[:8]}")
        session.add(org)
        session.flush()
        venue = Venue(organization_id=org.id, name="Solo", slug=f"solo-{uuid.uuid4().hex[:8]}", currency="USD")
        session.add(venue)
        session.flush()
        user = User(
            google_sub=f"solo-{uuid.uuid4().hex}",
            email=f"solo.{uuid.uuid4().hex}@example.com",
            name="Solo Owner",
            picture="",
            created_at=utcnow(),
            last_login_at=utcnow(),
        )
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, venue_id=venue.id, role=OWNER))
        session.commit()
        solo = RequestContext(
            user_id=user.id,
            email=user.email,
            name=user.name,
            venue_id=venue.id,
            organization_id=org.id,
            role=OWNER,
        )
    finally:
        session.close()
    token = bind(solo)
    try:
        with pytest.raises(DraftFailed) as demoted:
            update_membership(solo.user_id, STAFF, "server")
        assert demoted.value.status == 409
        assert demoted.value.message == "The venue needs an owner."
        with pytest.raises(DraftFailed) as removed:
            remove_membership(solo.user_id)
        assert removed.value.message == "You cannot remove your own membership."
    finally:
        reset(token)


def test_active_invite_is_unique_and_hidden_from_another_venue(monkeypatch):
    _ready()
    demo = ensure_demo_tenant()
    address = f"unique.{uuid.uuid4().hex}@example.com"
    session = SessionLocal()
    try:
        other = Venue(organization_id=demo.organization_id, name="Other Team", slug=f"other-team-{uuid.uuid4().hex[:8]}")
        session.add(other)
        session.commit()
        other_id = other.id
    finally:
        session.close()
    outsider = _member(f"outsider-{uuid.uuid4().hex}", f"outsider.{uuid.uuid4().hex}@example.com", other_id, OWNER)
    session = SessionLocal()
    try:
        owner = session.scalar(select(User).where(User.google_sub == DEMO_USER_SUB))
        session.add(
            VenueInvite(
                venue_id=demo.venue_id,
                email=address,
                role=STAFF,
                position="server",
                invited_by_user_id=owner.id,
                created_at=utcnow(),
            )
        )
        session.flush()
        session.add(
            VenueInvite(
                venue_id=demo.venue_id,
                email=address,
                role=STAFF,
                position="bartender",
                invited_by_user_id=owner.id,
                created_at=utcnow(),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
    finally:
        session.close()
    with _client(monkeypatch) as client:
        created = client.post("/team/invites", json={"email": address, "role": "Staff", "position": "server"})
        assert created.status_code == 200, created.text
        client.cookies.set(SESSION_COOKIE, issue_session(outsider.google_sub))
        hidden = client.post(f"/team/invites/{created.json()['id']}/revoke")
        assert hidden.status_code == 404


def test_google_sign_in_accepts_an_invite_and_keeps_the_owner_email(monkeypatch):
    _ready()
    demo = ensure_demo_tenant()
    staff_email = f"invited.{uuid.uuid4().hex}@example.com"
    owner_email = f"configured.owner.{uuid.uuid4().hex}@example.com"
    with _client(monkeypatch) as client:
        staff_invite = client.post("/team/invites", json={"email": staff_email, "role": "Staff", "position": "bartender"})
        owner_invite = client.post("/team/invites", json={"email": owner_email, "role": "Staff", "position": "server"})
        assert staff_invite.status_code == 200
        assert owner_invite.status_code == 200
    upsert_google_user({"sub": f"google-{uuid.uuid4().hex}", "email": staff_email, "name": "Invited Server", "picture": ""})
    monkeypatch.setenv("MADIRA_OWNER_EMAIL", owner_email)
    upsert_google_user({"sub": f"google-{uuid.uuid4().hex}", "email": owner_email, "name": "Configured Owner", "picture": ""})
    session = SessionLocal()
    try:
        staff = session.scalar(select(User).where(User.email == staff_email))
        staff_membership = session.scalar(select(Membership).where(Membership.user_id == staff.id, Membership.venue_id == demo.venue_id))
        assert staff_membership.role == STAFF
        assert staff_membership.position == "bartender"
        staff_row = session.get(VenueInvite, uuid.UUID(staff_invite.json()["id"]))
        assert staff_row.accepted_at is not None
        assert staff_row.accepted_user_id == staff.id
        owner = session.scalar(select(User).where(User.email == owner_email))
        owner_membership = session.scalar(select(Membership).where(Membership.user_id == owner.id, Membership.venue_id == demo.venue_id))
        assert owner_membership.role == OWNER
        owner_row = session.get(VenueInvite, uuid.UUID(owner_invite.json()["id"]))
        assert owner_row.accepted_at is not None
        accepted = session.scalar(
            select(AuditEvent).where(AuditEvent.venue_id == demo.venue_id, AuditEvent.entity_id == staff_row.id, AuditEvent.action == "team.invite.accept")
        )
        assert accepted is not None
    finally:
        session.close()


def test_migration_0018_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0018_team_roleplay_certificates.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0017_briefings"' in source
    assert source.count('_enable_rls("') == 3
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "if not _is_postgres():" in source
    db = tmp_path / "team.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "0017_briefings")
engine = sa.create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "venue_invites" not in tables
    assert "roleplay_sessions" not in tables
    assert "certificates" not in tables

command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0030_catalog_embeddings"
    tables = set(sa.inspect(conn).get_table_names())
    assert {"venue_invites", "roleplay_sessions", "certificates"} <= tables
    invites = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(venue_invites)"))}
    assert {"email", "role", "position", "accepted_at", "accepted_user_id", "revoked_at"} <= invites
    sessions = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(roleplay_sessions)"))}
    assert {"persona", "transcript", "rubric", "score", "status"} <= sessions
    certificates = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(certificates)"))}
    assert {"kind", "issued_on", "expires_on", "document_id"} <= certificates

command.downgrade(cfg, "0017_briefings")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0017_briefings"
    tables = set(sa.inspect(conn).get_table_names())
    assert "venue_invites" not in tables
    assert "roleplay_sessions" not in tables
    assert "certificates" not in tables

command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0030_catalog_embeddings"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
