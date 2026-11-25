"""License and certificate reminders stay in the app."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.auth import SESSION_COOKIE, issue_session
from madira.db import SessionLocal, init_db
from madira.domain.session import session_scope
from madira.domain.team.certificates import venue_today
from madira.main import app
from madira.models import AuditEvent, Membership, User
from madira.seed import seed
from madira.tenancy import AUDITOR, STAFF, ensure_demo_tenant

AUTH_SECRET = "reminder-test-secret"


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _user(venue_id, role: str, sub: str) -> str:
    session = SessionLocal()
    try:
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
        session.commit()
        return sub
    finally:
        session.close()


def test_license_certificate_ack_and_snooze_send_nothing(monkeypatch):
    demo = _demo()
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    suffix = uuid.uuid4().hex[:8]
    staff = _user(demo.venue_id, STAFF, f"rem-staff-{suffix}")
    auditor = _user(demo.venue_id, AUDITOR, f"rem-auditor-{suffix}")
    with session_scope() as session:
        today = venue_today(session, demo.venue_id)
    with TestClient(app) as client:
        listed = client.get("/reminders")
        assert listed.status_code == 200, listed.text
        payload = listed.json()
        assert payload["jurisdiction"] == "US-CA"
        assert payload["channel"] == "in_app"
        rules = {row["code"]: row for row in payload["rules"]}
        assert rules["abc_license"]["lead_days"] == 60
        assert rules["certificate_expiry"]["lead_days"] == 30
        assert "statute" not in rules["abc_license"]["detail"].lower()
        assert "mailto" not in listed.text
        titles = {row["title"] for row in payload["reminders"]}
        assert "ABC license renewal" in titles
        soon = client.post(
            "/licenses",
            json={"label": f"Test license {suffix}", "expires_on": (today + timedelta(days=50)).isoformat()},
        )
        assert soon.status_code == 200, soon.text
        later = client.post(
            "/licenses",
            json={"label": f"Far license {suffix}", "expires_on": (today + timedelta(days=90)).isoformat()},
        )
        assert later.status_code == 200, later.text
        cert = client.post(
            "/team/certificates",
            data={
                "user_id": str(demo.user_id),
                "kind": "other",
                "label": f"Card {suffix}",
                "issued_on": today.isoformat(),
                "expires_on": (today + timedelta(days=10)).isoformat(),
            },
        )
        assert cert.status_code == 200, cert.text
        far_cert = client.post(
            "/team/certificates",
            data={
                "user_id": str(demo.user_id),
                "kind": "food_handler",
                "label": f"Later card {suffix}",
                "issued_on": today.isoformat(),
                "expires_on": (today + timedelta(days=40)).isoformat(),
            },
        )
        assert far_cert.status_code == 200, far_cert.text
        again = client.get("/reminders")
        assert "mailto" not in again.text
        reminders = again.json()["reminders"]
        labels = {row["label"] for row in reminders}
        assert f"Test license {suffix}" in labels
        assert f"Far license {suffix}" not in labels
        assert f"Card {suffix}" in labels
        assert f"Later card {suffix}" not in labels
        license_row = next(row for row in reminders if row["label"] == f"Test license {suffix}")
        cert_row = next(row for row in reminders if row["label"] == f"Card {suffix}")
        gaps = client.get("/compliance/gaps")
        assert gaps.status_code == 200
        gap_labels = {row["label"] for row in gaps.json()["reminders"]}
        assert f"Test license {suffix}" in gap_labels
        snoozed = client.post(
            "/reminders/decide",
            json={"source_type": "license", "source_id": license_row["source_id"], "action": "snooze", "snooze_days": 7},
        )
        assert snoozed.status_code == 200, snoozed.text
        assert snoozed.json()["channel"] == "in_app"
        assert "mailto" not in snoozed.text
        acked = client.post(
            "/reminders/decide",
            json={"source_type": "certificate", "source_id": cert_row["source_id"], "action": "acknowledge"},
        )
        assert acked.status_code == 200, acked.text
        after = client.get("/reminders").json()["reminders"]
        after_labels = {row["label"] for row in after}
        assert f"Test license {suffix}" not in after_labels
        assert f"Card {suffix}" not in after_labels
        assert "ABC license renewal" in {row["title"] for row in after}
        client.cookies.set(SESSION_COOKIE, issue_session(staff))
        assert client.get("/reminders").status_code == 403
        assert client.post("/reminders/decide", json={"source_type": "license", "source_id": license_row["source_id"], "action": "acknowledge"}).status_code == 403
        client.cookies.set(SESSION_COOKIE, issue_session(auditor))
        assert client.get("/reminders").status_code == 200
        assert client.post("/reminders/decide", json={"source_type": "certificate", "source_id": cert_row["source_id"], "action": "acknowledge"}).status_code == 403
    session = SessionLocal()
    try:
        actions = set(
            session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.venue_id == demo.venue_id,
                    AuditEvent.action.in_(("reminder.acknowledged", "reminder.snoozed", "license.recorded")),
                )
            ).all()
        )
        assert {"reminder.acknowledged", "reminder.snoozed", "license.recorded"} <= actions
    finally:
        session.close()
