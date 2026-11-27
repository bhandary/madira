"""Roster and invites for the current venue.

An Owner invites any role. A Manager invites Staff only. Nothing is emailed.
A verified Google sign-in accepts a matching active invite.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.session import session_scope
from madira.domain.training.access import MEMBER_POSITIONS, actor
from madira.models import ROLES, Membership, User, Venue, VenueInvite
from madira.rbac import MATRIX, Capability
from madira.tenancy import MANAGER, OWNER, STAFF, RequestContext, active_venue_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _manage(ctx: RequestContext) -> None:
    if ctx.role not in MATRIX[Capability.TEAM_MANAGE]:
        raise DraftFailed("This role cannot do that.", 403)


def _view(ctx: RequestContext) -> None:
    if ctx.role not in MATRIX[Capability.TEAM_VIEW]:
        raise DraftFailed("This role cannot do that.", 403)


def _venue(session: Session) -> tuple[uuid.UUID, Venue]:
    venue_id = active_venue_id()
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue_id, venue


def _email(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if len(cleaned) > 320 or cleaned.count("@") != 1 or any(ch.isspace() for ch in cleaned):
        raise DraftFailed("Enter an email address.", 422)
    local, domain = cleaned.split("@", 1)
    if not local or not domain or "." not in domain:
        raise DraftFailed("Enter an email address.", 422)
    return cleaned


def _role(value: str) -> str:
    cleaned = (value or "").strip()
    for known in ROLES:
        if known.lower() == cleaned.lower():
            return known
    raise DraftFailed("Role must be Owner, Sommelier, Manager, Staff, or Auditor.", 422)


def _position(role: str, value: str | None) -> str | None:
    cleaned = (value or "").strip().lower()
    if role == STAFF:
        if cleaned not in MEMBER_POSITIONS:
            raise DraftFailed("Staff need a position: server, bartender, barback, or host.", 422)
        return cleaned
    if cleaned and cleaned not in MEMBER_POSITIONS:
        raise DraftFailed("Position must be server, bartender, barback, or host.", 422)
    return cleaned or None


def _manager_staff_only(ctx: RequestContext, role: str) -> None:
    if ctx.role == MANAGER and role != STAFF:
        raise DraftFailed("A manager can only invite staff.", 403)


def _owner_count(session: Session, venue_id: uuid.UUID) -> int:
    rows = session.scalars(
        select(Membership.id).where(Membership.venue_id == venue_id, Membership.role == OWNER)
    ).all()
    return len(rows)


def _member_dict(row: Membership, user: User) -> dict:
    return {
        "membership_id": str(row.id),
        "user_id": str(row.user_id),
        "name": user.name or "",
        "email": user.email or "",
        "role": row.role,
        "position": row.position,
    }


def _invite_dict(row: VenueInvite) -> dict:
    return {
        "id": str(row.id),
        "email": row.email,
        "role": row.role,
        "position": row.position,
        "invited_by_user_id": str(row.invited_by_user_id),
        "created_at": _iso(row.created_at),
        "accepted_at": _iso(row.accepted_at),
        "revoked_at": _iso(row.revoked_at),
    }


def _active_invites(session: Session, venue_id: uuid.UUID) -> list[VenueInvite]:
    return list(
        session.scalars(
            select(VenueInvite)
            .where(
                VenueInvite.venue_id == venue_id,
                VenueInvite.accepted_at.is_(None),
                VenueInvite.revoked_at.is_(None),
            )
            .order_by(VenueInvite.created_at.asc(), VenueInvite.email.asc())
        ).all()
    )


def roster() -> dict:
    ctx = actor()
    _view(ctx)
    with session_scope() as session:
        venue_id, _venue_row = _venue(session)
        memberships = session.scalars(
            select(Membership).where(Membership.venue_id == venue_id).order_by(Membership.role.asc(), Membership.id.asc())
        ).all()
        user_ids = [row.user_id for row in memberships]
        users = {}
        if user_ids:
            users = {row.id: row for row in session.scalars(select(User).where(User.id.in_(user_ids))).all()}
        members = []
        for row in memberships:
            user = users.get(row.user_id)
            if user is None:
                continue
            members.append(_member_dict(row, user))
        members.sort(key=lambda item: (item["name"].casefold(), item["email"].casefold()))
        payload = {"members": members, "invites": [_invite_dict(row) for row in _active_invites(session, venue_id)]}
        return payload


def invite(email: str, role: str, position: str | None = None) -> dict:
    ctx = actor()
    _manage(ctx)
    address = _email(email)
    assigned = _role(role)
    _manager_staff_only(ctx, assigned)
    floor = _position(assigned, position)
    with session_scope() as session:
        venue_id, venue = _venue(session)
        existing = session.scalar(
            select(VenueInvite).where(
                VenueInvite.venue_id == venue_id,
                VenueInvite.email == address,
                VenueInvite.accepted_at.is_(None),
                VenueInvite.revoked_at.is_(None),
            )
        )
        if existing is not None:
            raise DraftFailed("This person already has an active invite.", 409)
        row = VenueInvite(
            venue_id=venue_id,
            email=address,
            role=assigned,
            position=floor,
            invited_by_user_id=ctx.user_id,
            created_at=_now(),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            raise DraftFailed("This person already has an active invite.", 409) from exc
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="team.invite",
            entity_type="venue_invite",
            entity_id=row.id,
            after={"email": address, "role": assigned, "position": floor},
        )
        payload = _invite_dict(row)
        session.commit()
        return payload


def revoke_invite(invite_id: uuid.UUID) -> dict:
    ctx = actor()
    _manage(ctx)
    with session_scope() as session:
        venue_id, venue = _venue(session)
        row = session.get(VenueInvite, invite_id)
        if row is None or row.venue_id != venue_id:
            raise NotFound("invite not found")
        _manager_staff_only(ctx, row.role)
        if row.accepted_at is not None or row.revoked_at is not None:
            raise DraftFailed("This invite is no longer active.", 409)
        row.revoked_at = _now()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="team.invite.revoke",
            entity_type="venue_invite",
            entity_id=row.id,
            before={"email": row.email, "role": row.role, "position": row.position},
            after={"revoked_at": _iso(row.revoked_at)},
        )
        payload = _invite_dict(row)
        session.commit()
        return payload


def _membership(session: Session, venue_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    row = session.scalar(
        select(Membership).where(Membership.user_id == user_id, Membership.venue_id == venue_id)
    )
    if row is None:
        raise NotFound("member not found")
    return row


def update_membership(user_id: uuid.UUID, role: str, position: str | None = None) -> dict:
    ctx = actor()
    _manage(ctx)
    assigned = _role(role)
    floor = _position(assigned, position)
    with session_scope() as session:
        venue_id, venue = _venue(session)
        row = _membership(session, venue_id, user_id)
        if ctx.role == MANAGER and (row.role != STAFF or assigned != STAFF):
            raise DraftFailed("A manager can only assign staff.", 403)
        if row.role == OWNER and assigned != OWNER and _owner_count(session, venue_id) <= 1:
            raise DraftFailed("The venue needs an owner.", 409)
        before = {"role": row.role, "position": row.position}
        row.role = assigned
        row.position = floor
        user = session.get(User, user_id)
        if user is None:
            raise NotFound("member not found")
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="team.membership.update",
            entity_type="membership",
            entity_id=row.id,
            before=before,
            after={"role": assigned, "position": floor, "user_id": str(user_id)},
        )
        payload = _member_dict(row, user)
        session.commit()
        return payload


def remove_membership(user_id: uuid.UUID) -> dict:
    ctx = actor()
    _manage(ctx)
    if user_id == ctx.user_id:
        raise DraftFailed("You cannot remove your own membership.", 409)
    with session_scope() as session:
        venue_id, venue = _venue(session)
        row = _membership(session, venue_id, user_id)
        if ctx.role == MANAGER and row.role != STAFF:
            raise DraftFailed("A manager can only assign staff.", 403)
        if row.role == OWNER and _owner_count(session, venue_id) <= 1:
            raise DraftFailed("The venue needs an owner.", 409)
        user = session.get(User, user_id)
        before = {
            "user_id": str(user_id),
            "email": "" if user is None else user.email,
            "role": row.role,
            "position": row.position,
        }
        membership_id = row.id
        session.delete(row)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="team.membership.remove",
            entity_type="membership",
            entity_id=membership_id,
            before=before,
            after=None,
        )
        session.commit()
        return {"removed": True, "user_id": str(user_id)}


def _set_venue(session: Session, venue_id: uuid.UUID) -> None:
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT set_config('app.venue_id', :venue_id, true)"),
        {"venue_id": str(venue_id)},
    )


def accept_invites_for_user(session: Session, user: User) -> None:
    """Create memberships for active invites that match this verified email.

    ``MADIRA_OWNER_EMAIL`` is applied by the caller first. An existing
    membership is left as it is. This does not send email.
    """

    email = (user.email or "").strip().lower()
    if not email or "@" not in email:
        return
    if user.id is None:
        session.flush()
    venue_ids = list(session.scalars(select(Venue.id)).all())
    now = _now()
    for venue_id in venue_ids:
        _set_venue(session, venue_id)
        invites = session.scalars(
            select(VenueInvite).where(
                VenueInvite.venue_id == venue_id,
                VenueInvite.email == email,
                VenueInvite.accepted_at.is_(None),
                VenueInvite.revoked_at.is_(None),
            )
        ).all()
        if not invites:
            continue
        venue = session.get(Venue, venue_id)
        if venue is None:
            continue
        session.flush()
        membership = session.scalar(
            select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id)
        )
        for invite in invites:
            if membership is None:
                membership = Membership(
                    user_id=user.id,
                    venue_id=venue_id,
                    role=invite.role,
                    position=invite.position,
                )
                session.add(membership)
                session.flush()
            invite.accepted_at = now
            invite.accepted_user_id = user.id
            record_audit_event(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                action="team.invite.accept",
                entity_type="venue_invite",
                entity_id=invite.id,
                after={
                    "email": email,
                    "role": membership.role,
                    "position": membership.position,
                    "user_id": str(user.id),
                },
                actor_user_id=user.id,
                actor_email=email,
            )
