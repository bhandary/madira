"""Build each venue's briefing for the local service date.

Run: python -m madira.workers.briefings
"""

from __future__ import annotations

from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.domain.training.briefing import build
from madira.models import Membership, User, Venue
from madira.seed import seed
from madira.tenancy import OWNER, RequestContext, bind, demo_posture, reset


def _context(session, venue: Venue) -> RequestContext | None:
    membership = session.scalar(
        select(Membership)
        .where(Membership.venue_id == venue.id, Membership.role == OWNER)
        .order_by(Membership.id)
        .limit(1)
    )
    if membership is None:
        membership = session.scalar(
            select(Membership).where(Membership.venue_id == venue.id).order_by(Membership.id).limit(1)
        )
    if membership is None:
        return None
    user = session.get(User, membership.user_id)
    if user is None:
        return None
    return RequestContext(
        user_id=user.id,
        email=user.email,
        name=user.name,
        venue_id=venue.id,
        organization_id=venue.organization_id,
        role=membership.role,
    )


def main() -> int:
    init_db()
    if demo_posture():
        seed()
    session = SessionLocal()
    try:
        venues = list(session.scalars(select(Venue).order_by(Venue.name, Venue.id)).all())
        contexts = [(venue.id, _context(session, venue)) for venue in venues]
    finally:
        session.close()
    for _venue_id, ctx in contexts:
        if ctx is None:
            continue
        token = bind(ctx)
        try:
            build()
        finally:
            reset(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
