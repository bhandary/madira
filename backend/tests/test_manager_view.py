"""Manager view numbers are computed by the service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.agents.tools import get_team_progress
from madira.auth import utcnow
from madira.db import SessionLocal, init_db
from madira.domain.team.certificates import venue_today
from madira.domain.training.manager import progress
from madira.main import app
from madira.models import Briefing, BriefingAck, Lesson, Membership, Quiz, QuizAttempt, RoleplaySession, User
from madira.seed import seed
from madira.tenancy import STAFF, RequestContext, bind, ensure_demo_tenant, reset


def _person(venue_id) -> User:
    session = SessionLocal()
    try:
        token = uuid.uuid4().hex
        user = User(
            google_sub=f"progress-{token}",
            email=f"progress.{token}@example.com",
            name=f"Progress {token[:6]}",
            picture="",
            created_at=utcnow(),
            last_login_at=utcnow(),
        )
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=STAFF, position="server"))
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def test_progress_counts_acks_lessons_quizzes_roleplay_and_weak_topics():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    user = _person(demo.venue_id)
    before = next(row for row in progress()["people"] if row["user_id"] == str(user.id))
    assert before["lessons_done"] == 0
    assert before["quiz_average_label"] == "—"
    assert before["roleplay_average_label"] == "—"
    session = SessionLocal()
    try:
        today = venue_today(session, demo.venue_id)
        start = today - timedelta(days=today.weekday())
        week = [start + timedelta(days=offset) for offset in range(7)]
        existing = session.scalars(
            select(Briefing).where(
                Briefing.venue_id == demo.venue_id,
                Briefing.service_date >= week[0],
                Briefing.service_date <= week[-1],
            )
        ).all()
        briefing = next((row for row in existing if row.status == "published"), None)
        if briefing is None:
            used = {row.service_date for row in existing}
            free = next(day for day in week if day not in used)
            briefing = Briefing(
                venue_id=demo.venue_id,
                service_date=free,
                status="published",
                intro="",
                cards=[],
                due_review_count=0,
                built_at=datetime.now(timezone.utc),
                published_at=datetime.now(timezone.utc),
            )
            session.add(briefing)
            session.flush()
        session.add(
            BriefingAck(
                venue_id=demo.venue_id,
                briefing_id=briefing.id,
                user_id=user.id,
                seconds_to_ack=12,
                acknowledged_at=datetime.now(timezone.utc),
            )
        )
        lesson = Lesson(
            venue_id=demo.venue_id,
            slug=f"progress-{uuid.uuid4().hex[:8]}",
            title="Progress lesson",
            body="Listen.",
            position="server",
            status="approved",
            source="seed",
        )
        session.add(lesson)
        session.flush()
        quiz = Quiz(
            venue_id=demo.venue_id,
            lesson_id=lesson.id,
            title="Progress quiz",
            questions=[
                {"id": "g1", "prompt": "Glass?", "choices": ["A", "B"], "kind": "team-glass-8238"},
                {"id": "r1", "prompt": "Region?", "choices": ["A", "B"], "kind": "team-region-8238"},
            ],
            status="approved",
            source="lesson",
        )
        session.add(quiz)
        session.flush()
        session.add(
            QuizAttempt(
                venue_id=demo.venue_id,
                quiz_id=quiz.id,
                user_id=user.id,
                staff_name=user.name,
                answers=[0, 1],
                score=50,
                score_bp=5000,
                per_question=[{"id": "g1", "selected": 0, "ok": False}, {"id": "r1", "selected": 1, "ok": True}],
                created_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            RoleplaySession(
                venue_id=demo.venue_id,
                user_id=user.id,
                persona="skeptic",
                transcript=[],
                rubric={"listened": {"pass": True, "evidence": "I hear you."}},
                score=3,
                status="scored",
                started_at=datetime.now(timezone.utc),
                scored_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    finally:
        session.close()
    payload = progress()
    person = next(row for row in payload["people"] if row["user_id"] == str(user.id))
    assert person["briefing_ack"]["acked"] == before["briefing_ack"]["acked"] + 1
    assert person["briefing_ack"]["label"] == f"{person['briefing_ack']['acked']}/{person['briefing_ack']['published']}"
    assert person["lessons_done"] == 1
    assert person["quiz_average_bp"] == 5000
    assert person["quiz_average_label"] == "50%"
    assert person["roleplay_average_bp"] == 300
    assert person["roleplay_average_label"] == "3.00"
    topics = {row["topic"]: row for row in payload["weak_topics"]}
    assert topics["team-glass-8238"]["accuracy_bp"] == 0
    assert topics["team-region-8238"]["accuracy_bp"] == 10000
    assert topics["team-glass-8238"]["label"] == "0%"
    names = [row["topic"] for row in payload["weak_topics"]]
    assert names.index("team-glass-8238") < names.index("team-region-8238")


def test_staff_cannot_read_team_progress():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.google_sub == "madira-demo-ana"))
        ctx = RequestContext(
            user_id=user.id,
            email=user.email,
            name=user.name,
            venue_id=demo.venue_id,
            organization_id=demo.organization_id,
            role=STAFF,
        )
    finally:
        session.close()
    token = bind(ctx)
    try:
        body = json.loads(get_team_progress())
    finally:
        reset(token)
    assert body == {"error": "This role cannot do that."}
    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "ana")
        denied = client.get("/team/progress")
    assert denied.status_code == 403
    assert "people" not in denied.text
