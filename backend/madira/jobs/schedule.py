"""Enqueue the nightly jobs. The worker calls this on its own timer.

``python -m madira.worker schedule`` runs the same tick once and does not
execute the rows. One long-running worker both enqueues and claims, so a
second scheduler process is not required.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from madira.db import SessionLocal
from madira.jobs.handlers import SCHEDULED_ATTEMPTS
from madira.jobs.queue import enqueue, enqueue_if_absent
from madira.jobs.runner import run_existing
from madira.models import Membership, PosConnection, Venue


def _venues() -> list[tuple[uuid.UUID, uuid.UUID]]:
    session = SessionLocal()
    try:
        rows = session.scalars(select(Venue).order_by(Venue.name, Venue.id)).all()
        found = []
        for venue in rows:
            member = session.scalar(select(Membership.id).where(Membership.venue_id == venue.id).limit(1))
            if member is None:
                continue
            found.append((venue.id, venue.organization_id))
        return found
    finally:
        session.close()


def _pos_venues() -> list[tuple[uuid.UUID, uuid.UUID]]:
    session = SessionLocal()
    try:
        rows = session.scalars(
            select(PosConnection).where(PosConnection.status == "active").order_by(PosConnection.id)
        ).all()
        found = []
        for row in rows:
            venue = session.get(Venue, row.venue_id)
            if venue is None:
                continue
            found.append((venue.id, venue.organization_id))
        return found
    finally:
        session.close()


def enqueue_briefings() -> list[uuid.UUID]:
    ids = []
    for venue_id, organization_id in _venues():
        ids.append(
            enqueue(
                kind="briefing.build",
                venue_id=venue_id,
                organization_id=organization_id,
                max_attempts=SCHEDULED_ATTEMPTS,
            )
        )
    return ids


def enqueue_pos() -> list[uuid.UUID]:
    ids = []
    for venue_id, organization_id in _pos_venues():
        ids.append(
            enqueue(
                kind="pos.sync",
                venue_id=venue_id,
                organization_id=organization_id,
                max_attempts=SCHEDULED_ATTEMPTS,
            )
        )
    return ids


def schedule_due() -> list[uuid.UUID]:
    """Queue briefing, reminder refresh, and POS sync where one is not already waiting."""

    created: list[uuid.UUID] = []
    for venue_id, organization_id in _venues():
        for kind in ("briefing.build", "reminders.refresh"):
            job_id = enqueue_if_absent(
                kind=kind,
                venue_id=venue_id,
                organization_id=organization_id,
                max_attempts=SCHEDULED_ATTEMPTS,
            )
            if job_id is not None:
                created.append(job_id)
    for venue_id, organization_id in _pos_venues():
        job_id = enqueue_if_absent(
            kind="pos.sync",
            venue_id=venue_id,
            organization_id=organization_id,
            max_attempts=SCHEDULED_ATTEMPTS,
        )
        if job_id is not None:
            created.append(job_id)
    return created


def run_ids(ids: list[uuid.UUID]) -> int:
    failures = 0
    for job_id in ids:
        status = run_existing(job_id)
        if status not in {"succeeded", "running"}:
            failures += 1
    return failures
