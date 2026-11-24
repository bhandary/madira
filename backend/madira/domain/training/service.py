"""Lessons, quizzes, and the roleplay opener.

Scores and review dates are computed in the quiz service. The opener stays a
demo fixture until diner roleplay is replaced.
"""

from __future__ import annotations

import uuid

from madira.domain.errors import require_demo
from madira.domain.training.lessons import list_lessons
from madira.domain.training.quizzes import progress
from madira.tenancy import active_venue_id, demo_posture


def briefing(venue_id: uuid.UUID | None = None) -> dict:
    venue = active_venue_id()
    if venue_id is not None and venue_id != venue:
        return {"lessons": [], "quiz": None, "roleplay": None, "drafts": []}
    payload = list_lessons(venue)
    opener = None
    if demo_posture():
        from madira.agents.demo.fixtures import ROLEPLAY_OPENER

        opener = ROLEPLAY_OPENER
    return {
        "lessons": payload["lessons"],
        "drafts": payload["drafts"],
        "quiz": None,
        "roleplay": opener,
    }


def roleplay() -> dict:
    require_demo("Diner roleplay")
    from madira.agents.demo.fixtures import ROLEPLAY_OPENER

    return {
        "mode": "roleplay",
        "persona": "Skeptical diner, ordered the dry-aged ribeye",
        "opener": ROLEPLAY_OPENER,
        "first_line": "Hi — I ordered the ribeye. I don't really do wine lists. What are you going to try to sell me?",
    }


__all__ = ["briefing", "list_lessons", "progress", "roleplay"]
