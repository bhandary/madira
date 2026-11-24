"""Each person acknowledges a published briefing once. The week report is per user."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.training.briefing import set_clock, set_intro_completer
from madira.main import app
from madira.models import Briefing, BriefingAck, Membership, User, Venue
from madira.seed import seed
from madira.tenancy import AUDITOR, DEMO_USER_SUB, ensure_demo_tenant

AUTH_SECRET = "briefing-ack-test-secret"


@pytest.fixture(autouse=True)
def _clock():
    set_clock(None)
    set_intro_completer(None)
    yield
    set_clock(None)
    set_intro_completer(None)


def _prepare() -> None:
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        session.execute(delete(BriefingAck).where(BriefingAck.venue_id == demo.venue_id))
        session.execute(delete(Briefing).where(Briefing.venue_id == demo.venue_id))
        venue = session.get(Venue, demo.venue_id)
        venue.timezone = "America/Los_Angeles"
        venue.briefing_hour = 15
        user = session.scalar(select(User).where(User.google_sub == "briefing-auditor"))
        if user is None:
            user = User(
                google_sub="briefing-auditor",
                email="briefing-auditor@example.com",
                name="Briefing Auditor",
                picture="",
                created_at=utcnow(),
                last_login_at=utcnow(),
            )
            session.add(user)
            session.flush()
        member = session.scalar(
            select(Membership).where(Membership.user_id == user.id, Membership.venue_id == demo.venue_id)
        )
        if member is None:
            session.add(Membership(user_id=user.id, venue_id=demo.venue_id, role=AUDITOR))
        else:
            member.role = AUDITOR
        session.commit()
    finally:
        session.close()


def _open(moment: datetime) -> None:
    set_clock(lambda: moment)


def test_ack_is_once_and_the_week_report_counts_people(monkeypatch):
    _prepare()
    _open(datetime(2026, 11, 24, 23, 30, tzinfo=timezone.utc))
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, issue_session(DEMO_USER_SUB))
        created = client.post("/tonight/briefing/rebuild")
        assert created.status_code == 200, created.text
        briefing_id = created.json()["briefing"]["id"]
        blocked = client.post(f"/tonight/briefing/{briefing_id}/ack", json={"seconds_to_ack": 12})
        assert blocked.status_code == 409
        published = client.post("/tonight/briefing/publish")
        assert published.status_code == 200
        assert published.json()["briefing"]["status"] == "published"

        client.cookies.pop(SESSION_COOKIE)
        client.cookies.set("madira_demo_persona", "ana")
        first = client.post(f"/tonight/briefing/{briefing_id}/ack", json={"seconds_to_ack": 42})
        assert first.status_code == 200, first.text
        assert first.json()["acknowledged"] is True
        assert first.json()["seconds_to_ack"] == 42
        second = client.post(f"/tonight/briefing/{briefing_id}/ack", json={"seconds_to_ack": 90})
        assert second.status_code == 200
        assert second.json()["seconds_to_ack"] == 42

        denied = client.get("/tonight/briefing/report", params={"start": "2026-11-23", "end": "2026-11-25"})
        assert denied.status_code == 403
        rebuild = client.post("/tonight/briefing/rebuild")
        assert rebuild.status_code == 403

        client.cookies.pop("madira_demo_persona")
        client.cookies.set(SESSION_COOKIE, issue_session("briefing-auditor"))
        hidden = client.get("/tonight/briefing")
        assert hidden.status_code == 403
        report = client.get("/tonight/briefing/report", params={"start": "2026-11-23", "end": "2026-11-25"})
        assert report.status_code == 200, report.text
        days = {row["service_date"]: row for row in report.json()["days"]}
        assert list(days) == ["2026-11-23", "2026-11-24", "2026-11-25"]
        tuesday = days["2026-11-24"]
        ana = next(user for user in tuesday["users"] if user["name"] == "Ana")
        assert ana["acknowledged"] is True
        assert ana["seconds_to_ack"] == 42
        assert tuesday["acknowledged_count"] == 1
        assert tuesday["user_count"] == len(tuesday["users"])

        client.cookies.pop(SESSION_COOKIE)
        client.cookies.set("madira_demo_persona", "mia")
        managed = client.get("/tonight/briefing/report", params={"start": "2026-11-24", "end": "2026-11-24"})
        assert managed.status_code == 200
        backwards = client.get("/tonight/briefing/report", params={"start": "2026-11-25", "end": "2026-11-23"})
        assert backwards.status_code == 422

        client.cookies.pop("madira_demo_persona")
        client.cookies.set(SESSION_COOKIE, issue_session(DEMO_USER_SUB))
        rebuilt = client.post("/tonight/briefing/rebuild")
        assert rebuilt.status_code == 200
        assert client.post("/tonight/briefing/publish").status_code == 200
        client.cookies.pop(SESSION_COOKIE)
        client.cookies.set("madira_demo_persona", "ana")
        fresh = client.get("/tonight/briefing")
        assert fresh.json()["briefing"]["acknowledged"] is False
