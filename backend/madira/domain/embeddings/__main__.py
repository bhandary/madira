"""Backfill catalog embeddings for every venue.

Demo and tests finish the jobs before this process exits. A live worker
picks up the queued rows when inline mode is off.

    python -m madira.domain.embeddings
"""

from __future__ import annotations

from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.jobs.runner import JobError, accept
from madira.jobs.scope import bind_venue
from madira.models import Venue
from madira.seed import seed
from madira.tenancy import demo_posture, reset


def main() -> int:
    init_db()
    if demo_posture():
        seed()
    session = SessionLocal()
    try:
        venue_ids = list(session.scalars(select(Venue.id).order_by(Venue.id)).all())
    finally:
        session.close()
    done = 0
    failed = 0
    for venue_id in venue_ids:
        token = bind_venue(venue_id, None)
        if token is None:
            continue
        try:
            accept("catalog.embed_backfill", {}, max_attempts=1)
            done += 1
        except JobError:
            failed += 1
        finally:
            reset(token)
    print(f"embedded {done} venues, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
