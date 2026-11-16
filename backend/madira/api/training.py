from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from madira.agents.presenters.training import with_briefing, with_quiz
from madira.domain.training.service import briefing, grade, progress, roleplay
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter()


class QuizBody(BaseModel):
    answers: str
    staff_name: str = "Floor"


@router.get("/training", dependencies=[require(Capability.FLOOR)])
def training() -> dict[str, Any]:
    return with_briefing(briefing(active_venue_id()))


@router.post("/training/quiz", dependencies=[require(Capability.FLOOR)])
def training_quiz(body: QuizBody) -> dict[str, Any]:
    payload = grade(active_venue_id(), body.answers, staff_name=body.staff_name)
    if "error" in payload:
        return payload
    return with_quiz(payload)


@router.post("/training/roleplay", dependencies=[require(Capability.FLOOR)])
def training_roleplay() -> dict[str, Any]:
    return roleplay()


@router.get("/training/progress", dependencies=[require(Capability.RECORDS)])
def training_progress() -> dict[str, Any]:
    return progress(active_venue_id())
