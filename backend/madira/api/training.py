from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from madira.agents.tools import get_training_briefing, grade_quiz, start_roleplay
from madira.db import SessionLocal
from madira.models import QuizAttempt

router = APIRouter()


class QuizBody(BaseModel):
    answers: str
    staff_name: str = "Floor"


@router.get("/training")
def training() -> dict[str, Any]:
    return json.loads(get_training_briefing())


@router.post("/training/quiz")
def training_quiz(body: QuizBody) -> dict[str, Any]:
    return json.loads(grade_quiz(body.answers, staff_name=body.staff_name))


@router.post("/training/roleplay")
def training_roleplay() -> dict[str, Any]:
    return json.loads(start_roleplay())


@router.get("/training/progress")
def training_progress() -> dict[str, Any]:
    session = SessionLocal()
    try:
        attempts = session.scalars(select(QuizAttempt).order_by(QuizAttempt.id.desc())).all()
        return {
            "attempts": [
                {"id": a.id, "staff_name": a.staff_name, "score": a.score, "answers": a.answers}
                for a in attempts
            ]
        }
    finally:
        session.close()
