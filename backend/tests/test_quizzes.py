"""Quiz answers are graded in the service. Reviews follow the Leitner boxes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from madira.auth import SESSION_COOKIE, issue_session
from madira.db import SessionLocal, init_db
from madira.domain.training.quizzes import INTERVALS_DAYS, due_reviews, from_list, grade, set_clock
from madira.main import app
from madira.models import Quiz, QuizReview
from madira.seed import seed
from madira.tenancy import DEMO_PERSONA_COOKIE, DEMO_USER_SUB, ensure_demo_tenant
from sqlalchemy import delete, select


@pytest.fixture(autouse=True)
def _reset_clock():
    set_clock(None)
    yield
    set_clock(None)


def _seeded(venue_id):
    session = SessionLocal()
    try:
        quiz = session.scalar(select(Quiz).where(Quiz.venue_id == venue_id, Quiz.title == "Floor quiz — autumn pairings"))
        assert quiz is not None
        return quiz.id
    finally:
        session.close()


def test_leitner_boxes_use_the_frozen_clock():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    quiz_id = _seeded(demo.venue_id)
    session = SessionLocal()
    try:
        session.execute(delete(QuizReview).where(QuizReview.user_id == demo.user_id, QuizReview.quiz_id == quiz_id))
        session.commit()
    finally:
        session.close()
    now = {"at": datetime(2026, 3, 1, 12, tzinfo=timezone.utc)}
    set_clock(lambda: now["at"])
    first = grade(demo.venue_id, quiz_id, [1, 2, 2, 1])
    assert first["score_bp"] == 10000
    assert first["next_review_on"] == "2026-03-02"
    assert due_reviews(demo.venue_id)["reviews"] == []

    now["at"] = now["at"] + timedelta(days=1)
    due = due_reviews(demo.venue_id)["reviews"]
    assert len(due) == 4
    assert {row["due_on"] for row in due} == {"2026-03-02"}

    missed = grade(demo.venue_id, quiz_id, [0, 0, 0, 0])
    assert missed["score"] == 0.0
    assert missed["next_review_on"] == "2026-03-03"
    session = SessionLocal()
    try:
        boxes = session.scalars(select(QuizReview).where(QuizReview.user_id == demo.user_id, QuizReview.quiz_id == quiz_id)).all()
        assert boxes
        assert {row.box for row in boxes} == {0}
        assert {row.last_result for row in boxes} == {"wrong"}
    finally:
        session.close()

    again = grade(demo.venue_id, quiz_id, [1, 2, 2, 1])
    assert again["next_review_on"] == (now["at"] + timedelta(days=INTERVALS_DAYS[0])).date().isoformat()
    session = SessionLocal()
    try:
        boxes = session.scalars(select(QuizReview).where(QuizReview.user_id == demo.user_id, QuizReview.quiz_id == quiz_id)).all()
        assert {row.box for row in boxes} == {1}
    finally:
        session.close()

    for _ in range(6):
        grade(demo.venue_id, quiz_id, [1, 2, 2, 1])
    session = SessionLocal()
    try:
        boxes = session.scalars(select(QuizReview).where(QuizReview.user_id == demo.user_id, QuizReview.quiz_id == quiz_id)).all()
        assert {row.box for row in boxes} == {5}
        due_at = boxes[0].due_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        assert due_at - now["at"] == timedelta(days=INTERVALS_DAYS[-1])
    finally:
        session.close()


def test_list_quiz_answers_match_service_cards():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        from madira.models import BeverageList, ListItem, ListSection, Sku

        skus = session.scalars(
            select(Sku).where(
                Sku.venue_id == demo.venue_id,
                Sku.barcode.in_(["W-MUS-01", "W-BAR-01", "W-CHA-01", "W-COT-01"]),
            )
        ).all()
        beverage = BeverageList(
            venue_id=demo.venue_id,
            name="Quiz service list",
            budget=500_000,
            currency="USD",
            target_margin=3.0,
            created_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )
        session.add(beverage)
        session.flush()
        section = ListSection(venue_id=demo.venue_id, list_id=beverage.id, name="Service", position=1)
        session.add(section)
        session.flush()
        for index, sku in enumerate(skus, start=1):
            session.add(
                ListItem(
                    venue_id=demo.venue_id,
                    list_id=beverage.id,
                    sku_id=sku.id,
                    section=section.name,
                    section_id=section.id,
                    position=index,
                    cost=0,
                    pour_price=0,
                    bottle_price=0,
                    currency="USD",
                    margin_pct=0,
                )
            )
        session.commit()
    finally:
        session.close()
    quiz = from_list(demo.venue_id)
    assert quiz["source"] == "list"
    assert quiz["questions"]
    assert all("answer" not in question for question in quiz["questions"])
    session = SessionLocal()
    try:
        stored = session.get(Quiz, quiz["id"])
        assert stored is not None
        from madira.domain.training.grounding import on_list_facts
        from madira.domain.training.quizzes import inconsistent_answers

        facts = on_list_facts(session, demo.venue_id)
        assert inconsistent_answers(facts, list(stored.questions)) == 0
        glasses = {question["choices"][question["answer"]] for question in stored.questions if question["kind"] == "glassware"}
        assert "White wine glass" in glasses
        assert "Bordeaux glass" in glasses
    finally:
        session.close()


def test_persona_cookie_is_demo_only(monkeypatch):
    init_db()
    seed()
    with TestClient(app) as client:
        missing = client.post("/auth/demo-persona", json={"slug": "nobody"})
        assert missing.status_code == 404
        switched = client.post("/auth/demo-persona", json={"slug": "ana"})
        assert switched.status_code == 200, switched.text
        assert switched.json()["name"] == "Ana"
        assert client.cookies.get(DEMO_PERSONA_COOKIE) == "ana"
        lessons = client.get("/training/lessons")
        assert lessons.status_code == 200
        assert lessons.json()["name"] == "Ana"
        assert lessons.json()["can_author"] is False

        monkeypatch.setenv("MADIRA_AUTH_SECRET", "persona-test-secret")
        client.cookies.set(SESSION_COOKIE, issue_session(DEMO_USER_SUB))
        owner = client.get("/training/lessons")
        assert owner.status_code == 200
        assert owner.json()["name"] == "Demo Owner"
        client.cookies.pop(SESSION_COOKIE)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-not-a-fixture")
    with TestClient(app) as client:
        client.cookies.set(DEMO_PERSONA_COOKIE, "ana")
        assert client.get("/training/lessons").status_code == 401
        assert client.get("/auth/demo-personas").status_code == 404
        assert client.post("/auth/demo-persona", json={"slug": "ana"}).status_code == 404
