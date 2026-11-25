"""Team progress for Owner, Sommelier, and Manager.

Every rate and average is computed here. The model does not supply a number.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.errors import DraftFailed
from madira.domain.session import session_scope
from madira.domain.team.certificates import due_certificates, venue_today
from madira.domain.training.access import actor
from madira.models import Briefing, BriefingAck, Lesson, Membership, Quiz, QuizAttempt, RoleplaySession, User
from madira.rbac import MATRIX, Capability
from madira.tenancy import active_venue_id


def _label_percent(basis: int | None) -> str:
    if basis is None:
        return "—"
    return f"{basis // 100}%"


def _label_roleplay(basis: int | None) -> str:
    if basis is None:
        return "—"
    return f"{basis // 100}.{basis % 100:02d}"


def _ack(session: Session, venue_id: uuid.UUID, user_id: uuid.UUID, start, end) -> dict:
    briefings = session.scalars(
        select(Briefing).where(
            Briefing.venue_id == venue_id,
            Briefing.status == "published",
            Briefing.service_date >= start,
            Briefing.service_date <= end,
        )
    ).all()
    published = len(briefings)
    acked = 0
    if briefings:
        ids = [row.id for row in briefings]
        acked = len(
            session.scalars(
                select(BriefingAck.id).where(
                    BriefingAck.venue_id == venue_id,
                    BriefingAck.user_id == user_id,
                    BriefingAck.briefing_id.in_(ids),
                )
            ).all()
        )
    rate_bp = None if published == 0 else (acked * 10000) // published
    return {"acked": acked, "published": published, "rate_bp": rate_bp, "label": f"{acked}/{published}"}


def _lessons_done(session: Session, venue_id: uuid.UUID, user_id: uuid.UUID) -> int:
    attempts = session.scalars(
        select(QuizAttempt.quiz_id).where(QuizAttempt.venue_id == venue_id, QuizAttempt.user_id == user_id)
    ).all()
    if not attempts:
        return 0
    quizzes = session.scalars(
        select(Quiz).where(Quiz.venue_id == venue_id, Quiz.id.in_(set(attempts)), Quiz.source == "lesson")
    ).all()
    lesson_ids = {row.lesson_id for row in quizzes if row.lesson_id is not None}
    if not lesson_ids:
        return 0
    lessons = session.scalars(
        select(Lesson.id).where(
            Lesson.venue_id == venue_id,
            Lesson.id.in_(lesson_ids),
            Lesson.source != "list",
            Lesson.slug != "list-quiz",
        )
    ).all()
    return len(set(lessons))


def _quiz_average(session: Session, venue_id: uuid.UUID, user_id: uuid.UUID) -> tuple[int | None, str]:
    scores = session.scalars(
        select(QuizAttempt.score_bp).where(QuizAttempt.venue_id == venue_id, QuizAttempt.user_id == user_id)
    ).all()
    if not scores:
        return None, "—"
    basis = sum(int(score) for score in scores) // len(scores)
    return basis, _label_percent(basis)


def _roleplay_average(session: Session, venue_id: uuid.UUID, user_id: uuid.UUID) -> tuple[int | None, str]:
    scores = session.scalars(
        select(RoleplaySession.score).where(
            RoleplaySession.venue_id == venue_id,
            RoleplaySession.user_id == user_id,
            RoleplaySession.status == "scored",
        )
    ).all()
    if not scores:
        return None, "—"
    basis = (sum(int(score) for score in scores) * 100) // len(scores)
    return basis, _label_roleplay(basis)


def _weak_topics(session: Session, venue_id: uuid.UUID) -> list[dict]:
    attempts = session.scalars(select(QuizAttempt).where(QuizAttempt.venue_id == venue_id)).all()
    if not attempts:
        return []
    quiz_ids = {row.quiz_id for row in attempts}
    quizzes = {
        row.id: row
        for row in session.scalars(select(Quiz).where(Quiz.venue_id == venue_id, Quiz.id.in_(quiz_ids))).all()
    }
    totals: dict[str, list[int]] = {}
    for attempt in attempts:
        quiz = quizzes.get(attempt.quiz_id)
        if quiz is None:
            continue
        questions = {item.get("id"): item for item in (quiz.questions or []) if isinstance(item, dict)}
        for answer in attempt.per_question or []:
            if not isinstance(answer, dict):
                continue
            question = questions.get(answer.get("id"))
            if question is None:
                continue
            topic = str(question.get("kind") or question.get("topic") or "general")
            bucket = totals.setdefault(topic, [0, 0])
            bucket[1] += 1
            if answer.get("ok") is True:
                bucket[0] += 1
    ranked = []
    for topic, (correct, total) in totals.items():
        if total <= 0:
            continue
        accuracy_bp = (correct * 10000) // total
        ranked.append(
            {
                "topic": topic,
                "correct": correct,
                "total": total,
                "accuracy_bp": accuracy_bp,
                "label": _label_percent(accuracy_bp),
            }
        )
    ranked.sort(key=lambda row: (row["accuracy_bp"], -row["total"], row["topic"]))
    return ranked


def progress() -> dict:
    ctx = actor()
    if ctx.role not in MATRIX[Capability.TEAM_VIEW]:
        raise DraftFailed("This role cannot do that.", 403)
    with session_scope() as session:
        venue_id = active_venue_id()
        today = venue_today(session, venue_id)
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        memberships = session.scalars(select(Membership).where(Membership.venue_id == venue_id)).all()
        user_ids = [row.user_id for row in memberships]
        users = {}
        if user_ids:
            users = {row.id: row for row in session.scalars(select(User).where(User.id.in_(user_ids))).all()}
        people = []
        for membership in memberships:
            user = users.get(membership.user_id)
            if user is None:
                continue
            quiz_bp, quiz_label = _quiz_average(session, venue_id, user.id)
            roleplay_bp, roleplay_label = _roleplay_average(session, venue_id, user.id)
            people.append(
                {
                    "user_id": str(user.id),
                    "name": user.name or "",
                    "email": user.email or "",
                    "role": membership.role,
                    "position": membership.position,
                    "briefing_ack": _ack(session, venue_id, user.id, start, end),
                    "lessons_done": _lessons_done(session, venue_id, user.id),
                    "quiz_average_bp": quiz_bp,
                    "quiz_average_label": quiz_label,
                    "roleplay_average_bp": roleplay_bp,
                    "roleplay_average_label": roleplay_label,
                }
            )
        people.sort(key=lambda row: (row["name"].casefold(), row["email"].casefold()))
        return {
            "week": {"start": start.isoformat(), "end": end.isoformat()},
            "people": people,
            "weak_topics": _weak_topics(session, venue_id),
            "expiring_certificates": due_certificates(session, venue_id),
        }
