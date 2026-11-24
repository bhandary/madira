from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from madira.agents.presenters.training import with_briefing, with_quiz
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.training.lessons import approve_lesson, draft_lesson, edit_lesson, list_lessons
from madira.domain.training.quizzes import due_reviews, from_list, get_quiz, grade, progress
from madira.domain.training.service import briefing, roleplay
from madira.domain.training.standards import list_standards, reset_standard, update_standard
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter()


class DraftBody(BaseModel):
    position: str


class LessonPatch(BaseModel):
    title: str | None = None
    body: str | None = None
    position: str | None = None


class StandardBody(BaseModel):
    slug: str
    title: str
    body: str
    topic: str | None = None


class AttemptBody(BaseModel):
    answers: list[int] | str


def _raise(exc: Exception) -> None:
    if isinstance(exc, NotFound):
        raise HTTPException(404, exc.message) from exc
    if isinstance(exc, DraftFailed):
        raise HTTPException(exc.status, exc.message) from exc
    raise exc


@router.get("/training", dependencies=[require(Capability.TRAINING_LEARN)])
def training() -> dict[str, Any]:
    return with_briefing(briefing(active_venue_id()))


@router.get("/training/lessons", dependencies=[require(Capability.TRAINING_LEARN)])
def training_lessons() -> dict[str, Any]:
    try:
        return list_lessons(active_venue_id())
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/training/lessons/draft", dependencies=[require(Capability.TRAINING_AUTHOR)])
def training_draft(body: DraftBody) -> dict[str, Any]:
    try:
        return draft_lesson(active_venue_id(), body.position)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/training/lessons/{lesson_id}/approve", dependencies=[require(Capability.TRAINING_AUTHOR)])
def training_approve(lesson_id: uuid.UUID) -> dict[str, Any]:
    try:
        return approve_lesson(active_venue_id(), lesson_id)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.patch("/training/lessons/{lesson_id}", dependencies=[require(Capability.TRAINING_AUTHOR)])
def training_edit(lesson_id: uuid.UUID, body: LessonPatch) -> dict[str, Any]:
    try:
        return edit_lesson(
            active_venue_id(),
            lesson_id,
            title=body.title,
            body=body.body,
            position=body.position,
        )
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.get("/training/standards", dependencies=[require(Capability.TRAINING_LEARN)])
def training_standards() -> dict[str, Any]:
    try:
        return list_standards(active_venue_id())
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.put("/training/standards", dependencies=[require(Capability.TRAINING_AUTHOR)])
def training_standards_put(body: StandardBody) -> dict[str, Any]:
    try:
        return update_standard(
            active_venue_id(),
            body.slug,
            title=body.title,
            body=body.body,
            topic=body.topic,
        )
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/training/standards/{slug}/reset", dependencies=[require(Capability.TRAINING_AUTHOR)])
def training_standards_reset(slug: str) -> dict[str, Any]:
    try:
        return reset_standard(active_venue_id(), slug)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/training/quizzes/from-list", dependencies=[require(Capability.TRAINING_LEARN)])
def training_from_list() -> dict[str, Any]:
    try:
        return from_list(active_venue_id())
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.get("/training/quizzes/{quiz_id}", dependencies=[require(Capability.TRAINING_LEARN)])
def training_quiz(quiz_id: uuid.UUID) -> dict[str, Any]:
    try:
        return get_quiz(active_venue_id(), quiz_id)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/training/quizzes/{quiz_id}/attempts", dependencies=[require(Capability.TRAINING_LEARN)])
def training_attempt(quiz_id: uuid.UUID, body: AttemptBody) -> dict[str, Any]:
    try:
        return grade(active_venue_id(), quiz_id, body.answers)
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.get("/training/reviews/due", dependencies=[require(Capability.TRAINING_LEARN)])
def training_due() -> dict[str, Any]:
    try:
        return due_reviews(active_venue_id())
    except (NotFound, DraftFailed) as exc:
        _raise(exc)


@router.post("/training/roleplay", dependencies=[require(Capability.TRAINING_LEARN)])
def training_roleplay() -> dict[str, Any]:
    return roleplay()


@router.get("/training/progress", dependencies=[require(Capability.RECORDS)])
def training_progress() -> dict[str, Any]:
    return progress(active_venue_id())
