"""A2UI surfaces for domains that have not moved to agents/presenters yet."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import (
    create_surface,
    parse_operations,
    render,
    surface,
    update_components,
    update_data_model,
)

__all__ = [
    "create_surface",
    "parse_operations",
    "render",
    "surface",
    "update_components",
    "update_data_model",
    "quiz_surface",
    "briefing_surface",
    "tasting_surface",
]

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

TASTING_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "form", "cal"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "form", "component": "ScheduleForm", "draft": {"path": "/draft"}},
    {"id": "cal", "component": "TastingCalendar", "tastings": {"path": "/tastings"}},
]


def quiz_surface(title: str, quiz: dict) -> list[dict[str, Any]]:
    return surface("quiz", QUIZ_SCHEMA, {"title": title, "quiz": quiz})


def briefing_surface(title: str, lessons: list[dict]) -> list[dict[str, Any]]:
    return surface("briefing", BRIEFING_SCHEMA, {"title": title, "lessons": lessons})


def tasting_surface(title: str, draft: dict, tastings: list[dict]) -> list[dict[str, Any]]:
    return surface("tasting", TASTING_SCHEMA, {"title": title, "draft": draft, "tastings": tastings})
