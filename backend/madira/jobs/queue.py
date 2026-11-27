"""Claim and finish jobs.

Postgres claims with ``SELECT ... FOR UPDATE SKIP LOCKED`` inside one UPDATE.
SQLite claims with one conditional UPDATE. A second connection cannot take the
same row because the write lock covers that statement. Both sit in
``claim_next``.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, or_, select, text, update
from sqlalchemy.orm import Session

from madira.db import SessionLocal
from madira.models import Job

logger = logging.getLogger("madira.jobs")

_SECRET = re.compile(r"(sk-|api[_-]?key|bearer\s|authorization)", re.I)

POSTGRES_CLAIM = """
UPDATE jobs
SET status = 'running',
    locked_by = :worker,
    locked_until = :locked_until,
    attempts = attempts + 1,
    started_at = :now,
    updated_at = :now,
    finished_at = NULL
WHERE id = (
    SELECT id FROM jobs
    WHERE attempts < max_attempts
      AND (
        (status IN ('queued', 'failed') AND run_at <= :now)
        OR (status = 'running' AND locked_until IS NOT NULL AND locked_until < :now)
      )
    ORDER BY run_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id
"""

SQLITE_CLAIM = """
UPDATE jobs
SET status = 'running',
    locked_by = :worker,
    locked_until = :locked_until,
    attempts = attempts + 1,
    started_at = :now,
    updated_at = :now,
    finished_at = NULL
WHERE id = (
    SELECT id FROM jobs
    WHERE attempts < max_attempts
      AND (
        (status IN ('queued', 'failed') AND run_at <= :now)
        OR (status = 'running' AND locked_until IS NOT NULL AND locked_until < :now)
      )
    ORDER BY run_at, id
    LIMIT 1
)
RETURNING id
"""


def current_time() -> datetime:
    return datetime.now(timezone.utc)


def lease_seconds() -> int:
    raw = os.environ.get("MADIRA_JOB_LEASE_SECONDS", "").strip()
    if not raw:
        return 60
    try:
        value = int(raw)
    except ValueError:
        return 60
    if value < 1:
        return 1
    return min(value, 3600)


def backoff_seconds(attempts: int) -> int:
    power = max(int(attempts) - 1, 0)
    return min(300, 2**power)


def next_poll_delay(current: float, *, found: bool, floor: float = 0.25, cap: float = 5.0) -> float:
    if found:
        return floor
    return min(max(current, floor) * 2, cap)


def public_error(exc: Exception) -> str:
    message = getattr(exc, "message", None)
    if not isinstance(message, str) or not message.strip():
        message = ""
    text_value = " ".join(message.split())
    if not text_value:
        text_value = f"The job failed ({type(exc).__name__})."
    if _SECRET.search(text_value):
        return "The job failed."
    return text_value[:300]


def claim_sql(dialect: str) -> str:
    if dialect == "postgresql":
        return POSTGRES_CLAIM
    return SQLITE_CLAIM


def _bound(session: Session, column: str, value):
    col = Job.__table__.c[column]
    dialect = session.get_bind().dialect
    processor = col.type.bind_processor(dialect)
    if processor is None or value is None:
        return value
    return processor(value)


def _uuid(session: Session, value) -> uuid.UUID | None:
    if value is None:
        return None
    col = Job.__table__.c.id
    dialect = session.get_bind().dialect
    processor = col.type.result_processor(dialect, None)
    parsed = processor(value) if processor is not None else value
    return parsed if isinstance(parsed, uuid.UUID) else uuid.UUID(str(parsed))


def _worker_scope(session: Session) -> None:
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    session.execute(text("SELECT set_config('app.job_worker', '1', true)"))


def _open() -> Session:
    session = SessionLocal()
    _worker_scope(session)
    return session


def enqueue(
    *,
    kind: str,
    venue_id: uuid.UUID,
    organization_id: uuid.UUID,
    args: dict | None = None,
    actor_user_id: uuid.UUID | None = None,
    max_attempts: int = 3,
    run_at: datetime | None = None,
) -> uuid.UUID:
    now = current_time()
    payload = {"args": args or {}}
    if actor_user_id is not None:
        payload["actor_user_id"] = str(actor_user_id)
    session = _open()
    try:
        job = Job(
            organization_id=organization_id,
            venue_id=venue_id,
            kind=kind[:64],
            payload=payload,
            status="queued",
            attempts=0,
            max_attempts=max(1, int(max_attempts)),
            run_at=run_at or now,
            last_error="",
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.commit()
        return job.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def enqueue_if_absent(
    *,
    kind: str,
    venue_id: uuid.UUID,
    organization_id: uuid.UUID,
    args: dict | None = None,
    max_attempts: int = 3,
) -> uuid.UUID | None:
    session = _open()
    try:
        existing = session.scalar(
            select(Job.id).where(
                Job.venue_id == venue_id,
                Job.kind == kind,
                Job.status.in_(("queued", "running", "failed")),
            )
        )
        if existing is not None:
            return None
    finally:
        session.close()
    return enqueue(
        kind=kind,
        venue_id=venue_id,
        organization_id=organization_id,
        args=args,
        max_attempts=max_attempts,
    )


def _retire_expired(session: Session, now: datetime) -> None:
    blank = or_(Job.last_error == "", Job.last_error.is_(None))
    session.execute(
        update(Job)
        .where(
            Job.status == "running",
            Job.locked_until.is_not(None),
            Job.locked_until < now,
            Job.attempts >= Job.max_attempts,
        )
        .values(
            status="dead",
            locked_by=None,
            locked_until=None,
            finished_at=now,
            updated_at=now,
            last_error=case((blank, "The lock expired."), else_=Job.last_error),
        )
    )


CLAIM_ONE = """
UPDATE jobs
SET status = 'running',
    locked_by = :worker,
    locked_until = :locked_until,
    attempts = attempts + 1,
    started_at = :now,
    updated_at = :now,
    finished_at = NULL
WHERE id = :id
  AND status IN ('queued', 'failed')
  AND run_at <= :now
  AND attempts < max_attempts
RETURNING id
"""


def claim_one(job_id: uuid.UUID, worker: str, *, lease: int | None = None) -> bool:
    """Claim one known row with a single conditional UPDATE."""

    now = current_time()
    hold = now + timedelta(seconds=lease if lease is not None else lease_seconds())
    session = _open()
    try:
        found = session.execute(
            text(CLAIM_ONE),
            {
                "id": _bound(session, "id", job_id),
                "worker": (worker or "worker")[:120],
                "locked_until": _bound(session, "locked_until", hold),
                "now": _bound(session, "run_at", now),
            },
        ).scalar_one_or_none()
        session.commit()
        return found is not None
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def claim_next(worker: str, *, lease: int | None = None, kind: str | None = None) -> uuid.UUID | None:
    """Take one due job. The claim itself is a single UPDATE."""

    now = current_time()
    hold = now + timedelta(seconds=lease if lease is not None else lease_seconds())
    name = (worker or "worker")[:120]
    session = _open()
    try:
        dialect = session.get_bind().dialect.name
        _retire_expired(session, now)
        params = {
            "worker": name,
            "locked_until": _bound(session, "locked_until", hold),
            "now": _bound(session, "run_at", now),
        }
        statement = POSTGRES_CLAIM if dialect == "postgresql" else SQLITE_CLAIM
        if kind:
            statement = statement.replace("ORDER BY run_at, id", "AND kind = :kind\n    ORDER BY run_at, id")
            params["kind"] = kind[:64]
        job_id = _uuid(session, session.execute(text(statement), params).scalar_one_or_none())
        session.commit()
        return job_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def load_job(job_id: uuid.UUID) -> Job | None:
    session = _open()
    try:
        job = session.get(Job, job_id)
        if job is not None:
            session.expunge(job)
        return job
    finally:
        session.close()


def mark_succeeded(job_id: uuid.UUID, worker: str, result: dict) -> bool:
    now = current_time()
    session = _open()
    try:
        changed = session.execute(
            update(Job)
            .where(Job.id == job_id, Job.locked_by == worker, Job.status == "running")
            .values(
                status="succeeded",
                result=result,
                last_error="",
                locked_by=None,
                locked_until=None,
                finished_at=now,
                updated_at=now,
            )
        )
        session.commit()
        return bool(changed.rowcount)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def mark_failed(job_id: uuid.UUID, worker: str, exc: Exception) -> str:
    now = current_time()
    message = public_error(exc)
    session = _open()
    try:
        job = session.get(Job, job_id)
        if job is None or job.locked_by != worker or job.status != "running":
            session.rollback()
            return message
        job.last_error = message
        job.locked_by = None
        job.locked_until = None
        job.updated_at = now
        if job.attempts >= job.max_attempts:
            job.status = "dead"
            job.finished_at = now
            outcome = "dead"
        else:
            job.status = "failed"
            job.run_at = now + timedelta(seconds=backoff_seconds(job.attempts))
            job.finished_at = None
            outcome = "failed"
        kind = job.kind
        attempts = job.attempts
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    logger.warning("job %s id=%s kind=%s attempts=%s", outcome, job_id, kind, attempts)
    return message


def public_job(job: Job) -> dict:
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": job.status,
        "attempts": int(job.attempts),
        "max_attempts": int(job.max_attempts),
        "run_at": job.run_at.isoformat(),
        "last_error": job.last_error or "",
        "result": job.result,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "started_at": "" if job.started_at is None else job.started_at.isoformat(),
        "finished_at": "" if job.finished_at is None else job.finished_at.isoformat(),
    }


def job_for_venue(job_id: uuid.UUID, venue_id: uuid.UUID) -> Job | None:
    session = SessionLocal()
    try:
        job = session.scalar(select(Job).where(Job.id == job_id, Job.venue_id == venue_id))
        if job is not None:
            session.expunge(job)
        return job
    finally:
        session.close()
