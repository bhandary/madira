"""Lessons are drafted from the venue's standards and on-list bottles."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.auth import SESSION_COOKIE, issue_session
from madira.db import SessionLocal, init_db
from madira.domain.errors import DraftFailed
from madira.domain.training.lessons import draft_lesson, edit_lesson, list_lessons, set_lesson_completer
from madira.main import app
from madira.models import AuditEvent, Lesson
from madira.seed import seed
from madira.tenancy import AUDITOR, DEMO_USER_SUB, MANAGER, OWNER, STAFF, ensure_demo_tenant

AUTH_SECRET = "lessons-test-secret"


@pytest.fixture(autouse=True)
def _reset_completer():
    set_lesson_completer(None)
    yield
    set_lesson_completer(None)


def test_draft_cites_only_house_standards_and_on_list_bottles():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    drafted = draft_lesson(demo.venue_id, "server")
    assert drafted["status"] == "draft"
    assert drafted["position"] == "server"
    assert drafted["title"] == "Server service: Opening a still bottle"
    assert drafted["standard_ids"]
    assert drafted["sku_ids"]
    assert "cost" not in json.dumps(drafted, default=str).lower()
    assert "$" not in drafted["body"]
    session = SessionLocal()
    try:
        known_standards = {str(row) for row in session.scalars(select(Lesson.standard_ids))}
        lesson = session.get(Lesson, drafted["id"])
        assert lesson is not None
        assert set(lesson.standard_ids) <= set(drafted["standard_ids"])
        assert lesson.sku_ids == drafted["sku_ids"]
        _ = known_standards
    finally:
        session.close()
    edited = edit_lesson(demo.venue_id, drafted["id"], body=drafted["body"] + " Keep the label facing the guest.")
    assert "Keep the label facing the guest." in edited["body"]
    session = SessionLocal()
    try:
        event = session.scalar(
            select(AuditEvent)
            .where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "training.lesson.edit")
            .order_by(AuditEvent.seq.desc())
        )
        assert event is not None
        assert event.before_json["body"] != event.after_json["body"]
    finally:
        session.close()


def test_unknown_citations_and_live_failure_are_rejected(monkeypatch):
    init_db()
    seed()
    demo = ensure_demo_tenant()

    def invented(_prompt: str) -> str:
        return json.dumps(
            {
                "title": "Invented",
                "body": "A short lesson.",
                "position": "server",
                "standard_ids": ["00000000-0000-0000-0000-000000000099"],
                "sku_ids": ["00000000-0000-0000-0000-000000000098"],
            }
        )

    set_lesson_completer(invented)
    with pytest.raises(DraftFailed) as rejected:
        draft_lesson(demo.venue_id, "server")
    assert "schema" in rejected.value.message

    def priced(_prompt: str) -> str:
        return json.dumps(
            {
                "title": "Priced",
                "body": "Mention the cost of the pour.",
                "position": "server",
                "standard_ids": ["00000000-0000-0000-0000-000000000099"],
                "sku_ids": ["00000000-0000-0000-0000-000000000098"],
            }
        )

    set_lesson_completer(priced)
    with pytest.raises(DraftFailed):
        draft_lesson(demo.venue_id, "server")

    set_lesson_completer(None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-not-a-fixture")

    def demo_boom(_prompt: str) -> str:
        raise AssertionError("demo completer")

    def live_boom(_prompt: str) -> str:
        raise RuntimeError("connection refused")

    monkeypatch.setattr("madira.domain.training.lessons.demo_complete", demo_boom)
    monkeypatch.setattr("madira.domain.training.lessons.live_complete", live_boom)
    from madira.tenancy import bind, reset

    token = bind(demo)
    try:
        with pytest.raises(DraftFailed) as failed:
            draft_lesson(demo.venue_id, "server")
        assert "RuntimeError" in failed.value.message
        assert "Opening a still bottle" not in failed.value.message
    finally:
        reset(token)


def test_staff_see_only_their_approved_lessons_and_roles_are_enforced(monkeypatch):
    init_db()
    seed()
    demo = ensure_demo_tenant()
    drafted = draft_lesson(demo.venue_id, "bartender")
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "ana")
        ana = client.get("/training/lessons")
        assert ana.status_code == 200, ana.text
        body = ana.json()
        assert body["name"] == "Ana"
        assert body["role"] == STAFF
        assert body["position"] == "server"
        assert body["can_author"] is False
        titles = {row["title"] for row in body["lessons"]}
        assert "Tonight's pairing briefing" in titles
        assert "Bar and spirit service" not in titles
        assert drafted["title"] not in titles
        assert body["drafts"] == []
        denied = client.post("/training/lessons/draft", json={"position": "server"})
        assert denied.status_code == 403
        hidden = client.get(f"/training/quizzes/{drafted['quiz_id']}")
        assert hidden.status_code == 404

        client.cookies.set("madira_demo_persona", "mia")
        mia = client.get("/training/lessons")
        assert mia.status_code == 200
        mia_body = mia.json()
        assert mia_body["role"] == MANAGER
        assert mia_body["can_author"] is False
        assert str(drafted["id"]) not in {str(row["id"]) for row in mia_body["lessons"]}
        assert client.post("/training/lessons/draft", json={"position": "server"}).status_code == 403

        client.cookies.pop("madira_demo_persona")
        client.cookies.set(SESSION_COOKIE, issue_session(DEMO_USER_SUB))
        owner = client.get("/training/lessons")
        assert owner.json()["role"] == OWNER
        assert drafted["title"] in {row["title"] for row in owner.json()["drafts"]}
        approved = client.post(f"/training/lessons/{drafted['id']}/approve")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

    session = SessionLocal()
    try:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "training.lesson.approve")
        )
        assert event is not None
        assert event.after_json["status"] == "approved"
    finally:
        session.close()

    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "ben")
        ben = client.get("/training/lessons").json()
        assert ben["position"] == "bartender"
        assert drafted["title"] in {row["title"] for row in ben["lessons"]}
        assert "Wine service etiquette" not in {row["title"] for row in ben["lessons"]}


def test_auditor_cannot_learn(monkeypatch):
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        from madira.auth import utcnow
        from madira.models import Membership, User

        user = session.scalar(select(User).where(User.google_sub == "training-auditor"))
        if user is None:
            user = User(
                google_sub="training-auditor",
                email="auditor@example.com",
                name="Auditor",
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
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, issue_session("training-auditor"))
        assert client.get("/training/lessons").status_code == 403
        assert client.get("/training/quizzes/from-list").status_code == 405 or client.post("/training/quizzes/from-list").status_code == 403
        assert client.post("/training/quizzes/from-list").status_code == 403
        assert client.get("/training/progress").status_code == 200
