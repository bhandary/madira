"""Training routes score a named quiz for the signed-in user."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.domain.errors import NotFound
from madira.domain.training.quizzes import grade, progress
from madira.domain.training.service import briefing
from madira.main import app
from madira.models import Quiz, Venue
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant


def _other_venue(organization_id: uuid.UUID) -> uuid.UUID:
    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "training-service-other"))
        if venue is None:
            venue = Venue(organization_id=organization_id, name="Training Service Other", slug="training-service-other")
            session.add(venue)
            session.commit()
        return venue.id
    finally:
        session.close()


def _quiz_id(venue_id: uuid.UUID) -> uuid.UUID:
    session = SessionLocal()
    try:
        quiz_id = session.scalar(
            select(Quiz.id).where(Quiz.venue_id == venue_id, Quiz.title == "Floor quiz — autumn pairings")
        )
        assert quiz_id is not None
        return quiz_id
    finally:
        session.close()


def test_grade_scores_the_seeded_quiz_and_hides_the_answer_key():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    quiz_id = _quiz_id(demo.venue_id)
    result = grade(demo.venue_id, quiz_id, "1,2,2,1")
    assert result["score"] == 100.0
    assert result["score_bp"] == 10000
    assert result["correct"] == 4
    assert result["total"] == 4
    assert result["name"] == "Demo Owner"
    assert result["user_id"] == demo.user_id
    assert all("answer" not in question for question in result["questions"])
    assert result["review"][0]["ok"] is True
    assert result["next_review_on"]
    missed = grade(demo.venue_id, quiz_id, "0,0,0,0")
    assert missed["score"] == 0.0
    assert missed["correct"] == 0


def test_attempts_do_not_cross_venues():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    other = _other_venue(demo.organization_id)
    quiz_id = _quiz_id(demo.venue_id)
    with pytest.raises(NotFound):
        grade(other, quiz_id, "1,2,2,1")
    grade(demo.venue_id, quiz_id, "1,2,2,1")
    demo_names = {row["name"] for row in progress(demo.venue_id)["attempts"]}
    assert "Demo Owner" in demo_names
    assert progress(other)["attempts"] == []
    assert briefing(other)["lessons"] == []
    assert briefing(demo.venue_id)["lessons"]
    assert briefing(demo.venue_id)["quiz"] is None


def test_training_routes_emit_lessons_and_score_a_named_quiz():
    init_db()
    seed()
    with TestClient(app) as client:
        briefing_response = client.get("/training")
        assert briefing_response.status_code == 200
        body = briefing_response.json()
        surfaces = [op["createSurface"]["surfaceId"] for op in body["a2ui_operations"] if "createSurface" in op]
        assert surfaces == ["briefing"]
        assert "LessonCards" in json.dumps(body["a2ui_operations"])
        assert body["quiz"] is None
        lessons = client.get("/training/lessons")
        assert lessons.status_code == 200
        quiz_id = next(row["quiz_id"] for row in lessons.json()["lessons"] if row["slug"] == "daily-briefing")
        graded = client.post(f"/training/quizzes/{quiz_id}/attempts", json={"answers": [1, 2, 2, 1]})
        assert graded.status_code == 200, graded.text
        quiz = graded.json()
        assert quiz["score"] == 100.0
        assert quiz["score_bp"] == 10000
        assert all("answer" not in question for question in quiz["questions"])
        played = client.post("/training/roleplay", json={"persona": "skeptic"})
        assert played.status_code == 200, played.text
        session = played.json()["session"]
        assert session["persona"] == "skeptic"
        assert session["status"] == "open"
        assert session["score"] is None
        assert session["transcript"][0]["role"] == "guest"
        assert "RoleplayPanel" in json.dumps(played.json()["a2ui_operations"])
        progress_response = client.get("/training/progress")
        assert progress_response.status_code == 200
        assert progress_response.json()["attempts"][0]["name"] == "Demo Owner"
