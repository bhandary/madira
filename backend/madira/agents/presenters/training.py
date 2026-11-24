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

LESSON_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["card"]},
    {"id": "card", "component": "LessonCard", "lesson": {"path": "/lesson"}},
]


def quiz_surface(title: str, quiz: dict) -> list[dict[str, Any]]:
    return surface("quiz", QUIZ_SCHEMA, {"title": title, "quiz": quiz})


def briefing_surface(title: str, lessons: list[dict]) -> list[dict[str, Any]]:
    return surface("briefing", BRIEFING_SCHEMA, {"title": title, "lessons": lessons})


TONIGHT_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "cards"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "cards", "component": "BriefingCards", "briefing": {"path": "/briefing"}},
]

LOOKUP_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "results"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "results", "component": "FloorLookup", "lookup": {"path": "/lookup"}},
]


def tonight_surface(briefing: dict) -> list[dict[str, Any]]:
    return surface("tonight-briefing", TONIGHT_SCHEMA, {"title": "Tonight", "briefing": briefing})


def lookup_surface(payload: dict) -> list[dict[str, Any]]:
    return surface("floor-lookup", LOOKUP_SCHEMA, {"title": "Floor lookup", "lookup": payload})


def with_tonight_briefing(payload: dict) -> dict:
    briefing = payload.get("briefing") or {
        "id": "",
        "service_date": payload.get("service_date") or "",
        "status": "none",
        "intro": "The briefing opens later today.",
        "cards": [],
        "due_review_count": 0,
        "acknowledged": False,
        "seconds_to_ack": None,
    }
    body = dict(payload)
    body["a2ui_operations"] = tonight_surface(briefing)
    return body


def with_lookup(payload: dict) -> dict:
    body = dict(payload)
    body["a2ui_operations"] = lookup_surface(payload)
    return body


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
    title = payload["title"] if payload.get("score") is None else f"Quiz result · {payload['score']}%"
    body["a2ui_operations"] = quiz_surface(title, dict(payload))
    return body


def lesson_surface(lesson: dict, surface_id: str) -> list[dict[str, Any]]:
    return surface(surface_id, LESSON_SCHEMA, {"lesson": lesson})


def with_lessons(payload: dict) -> dict:
    operations: list[dict[str, Any]] = []
    for index, lesson in enumerate(payload.get("lessons") or []):
        operations.extend(lesson_surface(lesson, f"lesson-{index}"))
    if not operations:
        operations = briefing_surface("Lessons", [])
    body = dict(payload)
    body["a2ui_operations"] = operations
    return body


def with_lesson(payload: dict) -> dict:
    body = dict(payload)
    body["a2ui_operations"] = lesson_surface(payload, "lesson-draft")
    return body
