"""Bind a job to the same venue context a request would use."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.models import Membership, User, Venue
from madira.tenancy import OWNER, RequestContext, bind


def context_for(session: Session, venue_id: uuid.UUID, user_id: uuid.UUID | None) -> RequestContext | None:
    venue = session.get(Venue, venue_id)
    if venue is None:
        return None
    membership = None
    if user_id is not None:
        membership = session.scalar(
            select(Membership).where(Membership.user_id == user_id, Membership.venue_id == venue.id)
        )
    if membership is None:
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


def bind_venue(venue_id: uuid.UUID, user_id: uuid.UUID | None):
    from madira.db import SessionLocal

    session = SessionLocal()
    try:
        ctx = context_for(session, venue_id, user_id)
    finally:
        session.close()
    if ctx is None:
        return None
    return bind(ctx)
