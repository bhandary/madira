"""Lessons and quizzes for the current venue.

Scores and review dates are computed in the quiz service. Roleplay sessions
live in ``madira.domain.training.roleplay``.
"""

from __future__ import annotations

import uuid

from madira.domain.training.lessons import list_lessons
from madira.domain.training.quizzes import progress
from madira.tenancy import active_venue_id


def briefing(venue_id: uuid.UUID | None = None) -> dict:
    venue = active_venue_id()
    if venue_id is not None and venue_id != venue:
        return {"lessons": [], "quiz": None, "roleplay": None, "drafts": []}
    payload = list_lessons(venue)
    return {
        "lessons": payload["lessons"],
        "drafts": payload["drafts"],
        "quiz": None,
        "roleplay": None,
    }


__all__ = ["briefing", "list_lessons", "progress"]
