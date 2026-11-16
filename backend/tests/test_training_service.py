"""Training service: quiz scores are computed here, and attempts stay in the venue."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.domain.training.service import briefing, grade, progress, roleplay
from madira.main import app
from madira.models import Venue
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


def test_grade_scores_the_seeded_quiz_and_hides_the_answer_key():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    result = grade(demo.venue_id, "1,2,2,1", staff_name="Floor")
    assert result["score"] == 100.0
    assert result["correct"] == 4
    assert result["total"] == 4
    assert all("answer" not in question for question in result["questions"])
    assert result["review"][0]["ok"] is True
    missed = grade(demo.venue_id, "0,0,0,0", staff_name="Floor")
    assert missed["score"] == 0.0
    assert missed["correct"] == 0


def test_attempts_do_not_cross_venues():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    other = _other_venue(demo.organization_id)
    assert grade(other, "1,2,2,1") == {"error": "no quiz seeded"}
    grade(demo.venue_id, "1,2,2,1", staff_name="Ava")
    demo_names = {row["staff_name"] for row in progress(demo.venue_id)["attempts"]}
    assert "Ava" in demo_names
    assert progress(other)["attempts"] == []
    other_lessons = briefing(other)["lessons"]
    assert other_lessons == []
    assert briefing(demo.venue_id)["lessons"]


def test_training_routes_emit_briefing_and_quiz_surfaces():
    init_db()
    seed()
    with TestClient(app) as client:
        briefing_response = client.get("/training")
        assert briefing_response.status_code == 200
        body = briefing_response.json()
        surfaces = [op["createSurface"]["surfaceId"] for op in body["a2ui_operations"] if "createSurface" in op]
        assert surfaces == ["briefing", "quiz"]
        assert "LessonCards" in json.dumps(body["a2ui_operations"])
        assert "answer" not in json.dumps(body["quiz"]["questions"])
        graded = client.post("/training/quiz", json={"answers": "1,2,2,1", "staff_name": "Floor"})
        assert graded.status_code == 200
        quiz = graded.json()
        assert quiz["score"] == 100.0
        assert quiz["a2ui_operations"][0]["createSurface"]["surfaceId"] == "quiz"
        assert "100.0" in json.dumps(quiz["a2ui_operations"])
        played = client.post("/training/roleplay")
        assert played.status_code == 200
        assert played.json() == roleplay()
        assert "a2ui_operations" not in played.json()
