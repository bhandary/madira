"""Training surfaces. Quiz scores come from the training service."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

QUIZ_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "quiz"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "quiz", "component": "QuizCard", "quiz": {"path": "/quiz"}},
]

BRIEFING_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "cards"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "cards", "component": "LessonCards", "lessons": {"path": "/lessons"}},
]


def quiz_surface(title: str, quiz: dict) -> list[dict[str, Any]]:
    return surface("quiz", QUIZ_SCHEMA, {"title": title, "quiz": quiz})


def briefing_surface(title: str, lessons: list[dict]) -> list[dict[str, Any]]:
    return surface("briefing", BRIEFING_SCHEMA, {"title": title, "lessons": lessons})


def with_briefing(payload: dict) -> dict:
    operations = briefing_surface("Staff briefing", payload["lessons"])
    if payload["quiz"]:
        operations = [*operations, *quiz_surface(payload["quiz"]["title"], payload["quiz"])]
    return {
        "lessons": payload["lessons"],
        "quiz": payload["quiz"],
        "roleplay": payload["roleplay"],
        "a2ui_operations": operations,
    }


def with_quiz(payload: dict) -> dict:
    body = dict(payload)
    body["a2ui_operations"] = quiz_surface(f"Quiz result · {payload['score']}%", dict(payload))
    return body
