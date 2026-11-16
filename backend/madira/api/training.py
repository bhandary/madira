from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from madira.agents.tools import get_training_briefing, grade_quiz, start_roleplay
from madira.db import SessionLocal
from madira.models import QuizAttempt
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter()


class QuizBody(BaseModel):
    answers: str
    staff_name: str = "Floor"


@router.get("/training", dependencies=[require(Capability.FLOOR)])
def training() -> dict[str, Any]:
    return json.loads(get_training_briefing())


@router.post("/training/quiz", dependencies=[require(Capability.FLOOR)])
def training_quiz(body: QuizBody) -> dict[str, Any]:
    return json.loads(grade_quiz(body.answers, staff_name=body.staff_name))


@router.post("/training/roleplay", dependencies=[require(Capability.FLOOR)])
def training_roleplay() -> dict[str, Any]:
    return json.loads(start_roleplay())


@router.get("/training/progress", dependencies=[require(Capability.RECORDS)])
def training_progress() -> dict[str, Any]:
    session = SessionLocal()
    try:
        attempts = session.scalars(
            select(QuizAttempt)
            .where(QuizAttempt.venue_id == active_venue_id())
            .order_by(QuizAttempt.created_at.desc(), QuizAttempt.id.desc())
        ).all()
        return {
            "attempts": [
                {"id": a.id, "staff_name": a.staff_name, "score": a.score, "answers": a.answers}
                for a in attempts
            ]
        }
    finally:
        session.close()
