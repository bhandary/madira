"""Run one claimed job inside its venue scope."""

from __future__ import annotations

import os
import uuid

from fastapi.encoders import jsonable_encoder

from madira.jobs.handlers import HANDLERS
from madira.jobs.queue import claim_one, enqueue, load_job, mark_failed, mark_succeeded
from madira.jobs.scope import bind_venue
from madira.tenancy import current_request, demo_posture, reset


class JobError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ResultUnstored(Exception):
    def __init__(self) -> None:
        super().__init__("The job result could not be stored.")
        self.message = "The job result could not be stored."


def inline_enabled() -> bool:
    """Demo and tests run the job before the response. A worker is not required.

    ``MADIRA_JOBS_INLINE=0`` leaves the row queued. ``MADIRA_JOBS_INLINE=1``
    runs it even when the model is live.
    """

    raw = os.environ.get("MADIRA_JOBS_INLINE", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return demo_posture()


def _actor_id(payload: dict) -> uuid.UUID | None:
    raw = payload.get("actor_user_id")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def _storeable(result: dict) -> dict:
    try:
        encoded = jsonable_encoder(result)
    except (TypeError, ValueError) as exc:
        raise ResultUnstored() from exc
    if not isinstance(encoded, dict):
        raise ResultUnstored()
    return encoded


def perform(job_id: uuid.UUID, worker: str) -> None:
    job = load_job(job_id)
    if job is None or job.status != "running" or job.locked_by != worker:
        return
    handler = HANDLERS.get(job.kind)
    token = bind_venue(job.venue_id, _actor_id(job.payload or {}))
    try:
        if token is None:
            raise JobError("This venue has no member.")
        if handler is None:
            raise JobError("This job kind is not registered.")
        result = handler((job.payload or {}).get("args") or {})
        stored = _storeable(result if isinstance(result, dict) else {"value": result})
    except Exception as exc:
        mark_failed(job_id, worker, exc)
        raise
    else:
        mark_succeeded(job_id, worker, stored)
    finally:
        if token is not None:
            reset(token)


def accept(kind: str, args: dict, *, max_attempts: int) -> dict:
    """Enqueue the caller's venue and, in inline mode, finish before returning."""

    ctx = current_request()
    if ctx is None:
        raise JobError("This venue has no member.")
    job_id = enqueue(
        kind=kind,
        venue_id=ctx.venue_id,
        organization_id=ctx.organization_id,
        args=args,
        actor_user_id=ctx.user_id,
        max_attempts=max_attempts,
    )
    if not inline_enabled():
        return {"job_id": str(job_id), "job_status": "queued"}
    if not claim_one(job_id, "inline"):
        job = load_job(job_id)
        status = job.status if job is not None else "queued"
        return {"job_id": str(job_id), "job_status": status}
    perform(job_id, "inline")
    job = load_job(job_id)
    if job is None or job.status != "succeeded":
        status = job.status if job is not None else "failed"
        detail = "" if job is None else job.last_error
        raise JobError(detail or "The job failed.")
    body = dict(job.result or {})
    body["job_id"] = str(job.id)
    return body


def run_existing(job_id: uuid.UUID, worker: str = "inline") -> str:
    if not claim_one(job_id, worker):
        job = load_job(job_id)
        return job.status if job is not None else "missing"
    try:
        perform(job_id, worker)
    except Exception:
        job = load_job(job_id)
        return job.status if job is not None else "failed"
    job = load_job(job_id)
    return job.status if job is not None else "missing"
