"""Certificates, the 30-day reminder, and the compliance gap."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.session import session_scope
from madira.domain.team.certificates import venue_today
from madira.main import app
from madira.models import AuditEvent, Document, Membership, User
from madira.seed import seed
from madira.tenancy import AUDITOR, SOMMELIER, ensure_demo_tenant


def _ready():
    init_db()
    seed()
    return ensure_demo_tenant()


def _user(venue_id, role: str) -> User:
    session = SessionLocal()
    try:
        token = uuid.uuid4().hex
        user = User(
            google_sub=f"cert-{token}",
            email=f"cert.{token}@example.com",
            name=f"Cert {role}",
            picture="",
            created_at=utcnow(),
            last_login_at=utcnow(),
        )
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=role, position=None))
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def _mia_id() -> str:
    session = SessionLocal()
    try:
        return str(session.scalar(select(User.id).where(User.google_sub == "madira-demo-mia")))
    finally:
        session.close()


def _ana_id() -> str:
    session = SessionLocal()
    try:
        return str(session.scalar(select(User.id).where(User.google_sub == "madira-demo-ana")))
    finally:
        session.close()


def test_certificates_expire_into_tonight_and_compliance(monkeypatch, tmp_path):
    demo = _ready()
    monkeypatch.setenv("MADIRA_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("MADIRA_AUTH_SECRET", "certificate-test-secret")
    auditor = _user(demo.venue_id, AUDITOR)
    sommelier = _user(demo.venue_id, SOMMELIER)
    with session_scope() as session:
        today = venue_today(session, demo.venue_id)
    mia = _mia_id()
    ana = _ana_id()
    with TestClient(app) as client:
        soon = client.post(
            "/team/certificates",
            data={
                "user_id": mia,
                "kind": "responsible_service",
                "label": "Responsible service",
                "issued_on": (today - timedelta(days=20)).isoformat(),
                "expires_on": (today + timedelta(days=30)).isoformat(),
            },
            files={"file": ("certificate.txt", b"card", "text/plain")},
        )
        assert soon.status_code == 200, soon.text
        created = soon.json()["certificate"]
        assert created["expiring"] is True
        assert created["document_id"]
        assert created["document_filename"] == "certificate.txt"
        later = client.post(
            "/team/certificates",
            data={
                "user_id": mia,
                "kind": "food_handler",
                "label": "Food handler",
                "issued_on": today.isoformat(),
                "expires_on": (today + timedelta(days=31)).isoformat(),
            },
        )
        assert later.status_code == 200, later.text
        expired = client.post(
            "/team/certificates",
            data={
                "user_id": ana,
                "kind": "other",
                "label": "Allergy card",
                "issued_on": (today - timedelta(days=40)).isoformat(),
                "expires_on": (today - timedelta(days=1)).isoformat(),
            },
        )
        assert expired.status_code == 200, expired.text
        assert expired.json()["certificate"]["gap_type"] == "certificate_expired"
        listed = client.get("/team/certificates")
        ids = {row["id"] for row in listed.json()["certificates"]}
        assert created["id"] in ids
        assert later.json()["certificate"]["id"] in ids
        gaps = client.get("/compliance/gaps")
        assert gaps.status_code == 200
        gap_ids = {row["id"] for row in gaps.json()["certificate_gaps"]}
        assert created["id"] in gap_ids
        assert expired.json()["certificate"]["id"] in gap_ids
        assert later.json()["certificate"]["id"] not in gap_ids
        board = client.get("/tonight")
        tonight_ids = {row["id"] for row in board.json()["expiring_certificates"]}
        assert created["id"] in tonight_ids
        assert expired.json()["certificate"]["id"] in tonight_ids
        client.cookies.set("madira_demo_persona", "mia")
        managed = client.get("/tonight")
        assert created["id"] in {row["id"] for row in managed.json()["expiring_certificates"]}
        client.cookies.set("madira_demo_persona", "ana")
        floor = client.get("/tonight")
        assert floor.json()["expiring_certificates"] == []
        own = client.get("/training/certificates")
        assert own.status_code == 200
        own_ids = {row["id"] for row in own.json()["certificates"]}
        assert expired.json()["certificate"]["id"] in own_ids
        assert created["id"] not in own_ids
        assert client.get("/team/certificates").status_code == 403
        blocked = client.post(
            "/team/certificates",
            data={
                "user_id": ana,
                "kind": "other",
                "label": "Nope",
                "issued_on": today.isoformat(),
                "expires_on": today.isoformat(),
            },
        )
        assert blocked.status_code == 403
        client.cookies.pop("madira_demo_persona")
        client.cookies.set(SESSION_COOKIE, issue_session(sommelier.google_sub))
        assert client.post(
            "/team/certificates",
            data={
                "user_id": mia,
                "kind": "other",
                "label": "Nope",
                "issued_on": today.isoformat(),
                "expires_on": today.isoformat(),
            },
        ).status_code == 403
        client.cookies.set(SESSION_COOKIE, issue_session(auditor.google_sub))
        visible = client.get("/team/certificates")
        assert visible.status_code == 200
        assert created["id"] in {row["id"] for row in visible.json()["certificates"]}
        assert client.delete(f"/team/certificates/{created['id']}").status_code == 403
        client.cookies.delete(SESSION_COOKIE)
        client.cookies.set("madira_demo_persona", "mia")
        edited = client.patch(f"/team/certificates/{later.json()['certificate']['id']}", json={"label": "Food handler card"})
        assert edited.status_code == 200, edited.text
        assert edited.json()["certificate"]["label"] == "Food handler card"
        removed = client.delete(f"/team/certificates/{created['id']}")
        assert removed.status_code == 200
    session = SessionLocal()
    try:
        document = session.get(Document, uuid.UUID(created["document_id"]))
        assert document is not None
        assert document.doc_type == "certificate"
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(created["id"]), AuditEvent.action == "certificate.create")
        )
        assert event is not None
    finally:
        session.close()
