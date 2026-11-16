"""Lessons, quiz scores, and the roleplay opener. The score is computed here."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select

from madira.domain.session import session_scope
from madira.fixtures_data import ROLEPLAY_OPENER
from madira.models import Lesson, Quiz, QuizAttempt


def briefing(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        lessons = [
            {
                "id": lesson.id,
                "slug": lesson.slug,
                "title": lesson.title,
                "role": lesson.role,
                "category": lesson.category,
                "body": lesson.body,
            }
            for lesson in session.scalars(select(Lesson).where(Lesson.venue_id == venue_id)).all()
        ]
        quiz = session.scalar(select(Quiz).where(Quiz.venue_id == venue_id).limit(1))
        quiz_payload = None
        if quiz:
            quiz_payload = {
                "id": quiz.id,
                "title": quiz.title,
                "questions": [{key: value for key, value in question.items() if key != "answer"} for question in quiz.questions],
            }
        return {"lessons": lessons, "quiz": quiz_payload, "roleplay": ROLEPLAY_OPENER}


def grade(venue_id: uuid.UUID, answers: str, staff_name: str = "Floor") -> dict:
    with session_scope() as session:
        quiz = session.scalar(select(Quiz).where(Quiz.venue_id == venue_id).limit(1))
        if quiz is None:
            return {"error": "no quiz seeded"}
        parsed = [int(part.strip()) for part in re.split(r"[,\s]+", answers.strip()) if part.strip() != ""]
        correct = 0
        review = []
        for idx, question in enumerate(quiz.questions):
            choice = parsed[idx] if idx < len(parsed) else -1
            ok = choice == question["answer"]
            correct += int(ok)
            review.append(
                {
                    "id": question["id"],
                    "prompt": question["prompt"],
                    "selected": choice,
                    "correct": question["answer"],
                    "ok": ok,
                    "explain": question["explain"],
                }
            )
        score = round(100 * correct / max(len(quiz.questions), 1), 1)
        session.add(QuizAttempt(venue_id=venue_id, quiz_id=quiz.id, staff_name=staff_name, answers=parsed, score=score))
        payload = {
            "id": quiz.id,
            "title": quiz.title,
            "questions": [{key: value for key, value in question.items() if key != "answer"} for question in quiz.questions],
            "score": score,
            "correct": correct,
            "total": len(quiz.questions),
            "review": review,
            "staff_name": staff_name,
        }
        session.commit()
        return payload


def roleplay() -> dict:
    return {
        "mode": "roleplay",
        "persona": "Skeptical diner, ordered the dry-aged ribeye",
        "opener": ROLEPLAY_OPENER,
        "first_line": "Hi — I ordered the ribeye. I don't really do wine lists. What are you going to try to sell me?",
    }


def progress(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        attempts = session.scalars(
            select(QuizAttempt)
            .where(QuizAttempt.venue_id == venue_id)
            .order_by(QuizAttempt.created_at.desc(), QuizAttempt.id.desc())
        ).all()
        return {
            "attempts": [
                {"id": attempt.id, "staff_name": attempt.staff_name, "score": attempt.score, "answers": attempt.answers}
                for attempt in attempts
            ]
        }
