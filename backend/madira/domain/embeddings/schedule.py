"""Enqueue an embedding after the catalog row commits.

The job runs in its own session, so it has to wait until the SKU or note is
visible. Demo and tests run that job inline, the same way the other jobs do.
"""

from __future__ import annotations

import uuid

from sqlalchemy import event
from sqlalchemy.orm import Session

_INSTALLED = False


def mark(session: Session, venue_id: uuid.UUID, organization_id: uuid.UUID, subject_type: str, subject_id: uuid.UUID) -> None:
    pending = session.info.setdefault("madira_embeds", {})
    pending[(str(venue_id), subject_type, str(subject_id))] = str(organization_id)


def _after_rollback(session: Session) -> None:
    session.info.pop("madira_embeds", None)


def _after_commit(session: Session) -> None:
    pending = session.info.pop("madira_embeds", None)
    if not pending:
        return
    from madira.jobs.queue import enqueue
    from madira.jobs.runner import inline_enabled, run_existing
    from madira.jobs.scope import bind_venue
    from madira.tenancy import current_request, reset

    actor = None
    ctx = current_request()
    if ctx is not None:
        actor = ctx.user_id
    grouped: dict[str, list[tuple[str, str, str]]] = {}
    for (venue_id, subject_type, subject_id), organization_id in pending.items():
        grouped.setdefault(venue_id, []).append((organization_id, subject_type, subject_id))
    for venue_id, items in grouped.items():
        organization_id = items[0][0]
        token = bind_venue(uuid.UUID(venue_id), actor)
        if token is None:
            continue
        reset(token)
        for _org, subject_type, subject_id in items:
            job_id = enqueue(
                kind="catalog.embed",
                venue_id=uuid.UUID(venue_id),
                organization_id=uuid.UUID(organization_id),
                args={"subject_type": subject_type, "subject_id": subject_id},
                actor_user_id=actor,
                max_attempts=1,
            )
            if not inline_enabled():
                continue
            status = run_existing(job_id, "inline")
            if status != "succeeded":
                from madira.jobs.queue import load_job

                job = load_job(job_id)
                detail = "" if job is None else job.last_error
                raise RuntimeError(detail or "The catalog embedding failed.")


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_rollback", _after_rollback)
    _INSTALLED = True


install()
