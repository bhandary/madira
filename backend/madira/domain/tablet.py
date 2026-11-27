"""Shared-tablet PIN switch.

An Owner or Manager who is signed in normally can mark this browser as the
venue tablet. Staff who already belong to that venue take a turn by entering
a personal PIN. The PIN is stored as scrypt. The acting session is idle-limited
and cannot perform Owner-only actions. Wrong PINs lock the membership and the
tablet. Nothing here logs the PIN, the hash, or the device token.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from madira.db import SessionLocal
from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.session import session_scope
from madira.models import Membership, SharedTablet, TabletActor, User, Venue
from madira.tenancy import MANAGER, OWNER, STAFF, RequestContext, current_request

logger = logging.getLogger("madira.tablet")

TABLET_COOKIE = "madira_tablet"
ACTOR_COOKIE = "madira_actor"
WRONG = "That PIN is wrong."
LOCKED = "This tablet is locked. Try again later."
UNLOCK = "Unlock the tablet."
FAILURES = 5
LOCKOUT_SECONDS = 15 * 60
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_OPEN = {
    ("GET", "/tablet"),
    ("POST", "/tablet/unlock"),
    ("POST", "/tablet/lock"),
    ("POST", "/tablet/disable"),
}


@dataclass
class TabletResult:
    body: dict
    tablet_token: str | None = None
    actor_token: str | None = None
    clear_tablet: bool = False
    clear_actor: bool = False


def idle_seconds() -> int:
    """How long a PIN session lasts without activity. Default is 15 minutes."""

    raw = os.environ.get("MADIRA_TABLET_IDLE_SECONDS", "").strip()
    default = 15 * 60
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 30 or value > 24 * 60 * 60:
        return default
    return value


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        pin.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
        maxmem=64 * 1024 * 1024,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_pin(pin: str, stored: str | None) -> bool:
    if not stored or stored.count("$") != 5:
        return False
    kind, n_raw, r_raw, p_raw, salt_b64, digest_b64 = stored.split("$")
    if kind != "scrypt":
        return False
    try:
        salt = _b64d(salt_b64)
        expected = _b64d(digest_b64)
        got = hashlib.scrypt(
            pin.encode("utf-8"),
            salt=salt,
            n=int(n_raw),
            r=int(r_raw),
            p=int(p_raw),
            dklen=len(expected),
            maxmem=64 * 1024 * 1024,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


def overlay_tablet(request: Request, host: RequestContext) -> RequestContext:
    """Use the PIN actor while this browser is a shared tablet.

    A locked tablet keeps the host only for the picker, unlock, lock, and
    disable routes. Every other route waits until someone enters a PIN.
    """

    raw = request.cookies.get(TABLET_COOKIE) or ""
    if not raw:
        return host
    session = SessionLocal()
    try:
        tablet = _tablet_for(session, raw, host.venue_id)
        if tablet is None:
            return host
        actor = _live_actor(session, tablet, request.cookies.get(ACTOR_COOKIE) or "")
        if actor is not None:
            return _as_user(session, actor.user_id, tablet, pin_session=True)
        if (_method(request), _path(request)) in _OPEN:
            return _as_user(session, tablet.host_user_id, tablet, pin_session=False)
        raise HTTPException(status_code=423, detail=UNLOCK)
    finally:
        session.close()


def tablet_state(request: Request) -> dict:
    ctx = _ctx()
    with session_scope() as session:
        tablet, actor = _device(session, request, ctx)
        return _body(session, ctx, tablet, actor)


def set_pin(pin: str) -> dict:
    ctx = _real()
    cleaned = _pin(pin)
    with session_scope() as session:
        row = _membership(session, ctx.venue_id, ctx.user_id)
        row.pin_hash = hash_pin(cleaned)
        row.pin_failures = 0
        row.pin_locked_until = None
        session.commit()
        return {"ok": True, "has_pin": True}


def clear_pin(user_id: uuid.UUID) -> dict:
    ctx = _real()
    if ctx.role not in {OWNER, MANAGER}:
        raise DraftFailed("This role cannot do that.", 403)
    with session_scope() as session:
        venue = _venue(session, ctx.venue_id)
        row = _membership(session, ctx.venue_id, user_id)
        if ctx.role == MANAGER and row.role != STAFF:
            raise DraftFailed("A manager can only clear a staff PIN.", 403)
        if not row.pin_hash:
            raise NotFound("member not found")
        row.pin_hash = None
        row.pin_failures = 0
        row.pin_locked_until = None
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            action="tablet.pin.clear",
            entity_type="membership",
            entity_id=row.id,
            after={"user_id": str(user_id), "role": row.role},
        )
        session.commit()
        return {"ok": True, "has_pin": False}


def enable_tablet() -> TabletResult:
    ctx = _real()
    if ctx.role not in {OWNER, MANAGER}:
        raise DraftFailed("This role cannot do that.", 403)
    with session_scope() as session:
        venue = _venue(session, ctx.venue_id)
        host = _membership(session, ctx.venue_id, ctx.user_id)
        if not host.pin_hash:
            raise DraftFailed("Set your PIN before sharing this tablet.", 422)
        raw, digest = _token()
        tablet = SharedTablet(
            organization_id=venue.organization_id,
            venue_id=venue.id,
            host_user_id=ctx.user_id,
            token_hash=digest,
            enabled=True,
            pin_failures=0,
            created_at=_now(),
        )
        session.add(tablet)
        session.flush()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            action="tablet.enable",
            entity_type="shared_tablet",
            entity_id=tablet.id,
            after={"host_user_id": str(ctx.user_id)},
        )
        body = _body(session, ctx, tablet, None)
        session.commit()
        return TabletResult(body=body, tablet_token=raw, clear_actor=True)


def disable_tablet(request: Request, pin: str) -> TabletResult:
    ctx = _ctx()
    cleaned = _pin(pin)
    with session_scope() as session:
        tablet, _actor = _device(session, request, ctx)
        if tablet is None:
            raise NotFound("tablet not found")
        host = _membership(session, tablet.venue_id, tablet.host_user_id)
        if host.role not in {OWNER, MANAGER}:
            raise DraftFailed("Sign in to do that.", 403)
        if _locked(host) or _locked(tablet):
            raise DraftFailed(LOCKED, 423)
        if not verify_pin(cleaned, host.pin_hash):
            locked = _fail(session, tablet, host, tablet.venue_id, host.user_id)
            session.commit()
            raise DraftFailed(LOCKED if locked else WRONG, 423 if locked else 401)
        tablet.enabled = False
        tablet.disabled_at = _now()
        tablet.pin_failures = 0
        tablet.pin_locked_until = None
        host.pin_failures = 0
        host.pin_locked_until = None
        session.execute(delete(TabletActor).where(TabletActor.tablet_id == tablet.id))
        venue = _venue(session, tablet.venue_id)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            action="tablet.disable",
            entity_type="shared_tablet",
            entity_id=tablet.id,
            after={"host_user_id": str(tablet.host_user_id)},
        )
        host_ctx = _as_user(session, tablet.host_user_id, tablet, pin_session=False)
        body = _body(session, host_ctx, None, None)
        session.commit()
        return TabletResult(body=body, clear_tablet=True, clear_actor=True)


def unlock_tablet(request: Request, user_id: uuid.UUID, pin: str) -> TabletResult:
    ctx = _ctx()
    cleaned = _pin(pin)
    with session_scope() as session:
        tablet, _actor = _device(session, request, ctx)
        if tablet is None:
            raise NotFound("tablet not found")
        if _locked(tablet):
            raise DraftFailed(LOCKED, 423)
        member = session.scalar(
            select(Membership).where(Membership.user_id == user_id, Membership.venue_id == tablet.venue_id)
        )
        if member is None:
            _fail_tablet(session, tablet, tablet.venue_id)
            session.commit()
            raise NotFound("That person is not on this tablet.")
        if _locked(member):
            raise DraftFailed(LOCKED, 423)
        if not member.pin_hash or not verify_pin(cleaned, member.pin_hash):
            logger.info("tablet pin rejected user=%s", user_id)
            locked = _fail(session, tablet, member, tablet.venue_id, user_id)
            session.commit()
            raise DraftFailed(LOCKED if locked else WRONG, 423 if locked else 401)
        member.pin_failures = 0
        member.pin_locked_until = None
        tablet.pin_failures = 0
        tablet.pin_locked_until = None
        session.execute(delete(TabletActor).where(TabletActor.tablet_id == tablet.id))
        raw, digest = _token()
        expires = _now() + timedelta(seconds=idle_seconds())
        actor = TabletActor(
            tablet_id=tablet.id,
            organization_id=tablet.organization_id,
            venue_id=tablet.venue_id,
            user_id=member.user_id,
            token_hash=digest,
            expires_at=expires,
            created_at=_now(),
        )
        session.add(actor)
        session.flush()
        switched = _as_user(session, member.user_id, tablet, pin_session=True)
        body = _body(session, switched, tablet, actor)
        session.commit()
        return TabletResult(body=body, actor_token=raw)


def lock_tablet(request: Request) -> TabletResult:
    ctx = _ctx()
    with session_scope() as session:
        tablet, _actor = _device(session, request, ctx)
        if tablet is None:
            raise NotFound("tablet not found")
        session.execute(delete(TabletActor).where(TabletActor.tablet_id == tablet.id))
        host = _as_user(session, tablet.host_user_id, tablet, pin_session=False)
        body = _body(session, host, tablet, None)
        session.commit()
        return TabletResult(body=body, clear_actor=True)


def touch_tablet(request: Request) -> TabletResult:
    ctx = _ctx()
    if not ctx.pin_session:
        raise DraftFailed(UNLOCK, 423)
    raw = request.cookies.get(ACTOR_COOKIE) or ""
    if not raw:
        raise DraftFailed(UNLOCK, 423)
    with session_scope() as session:
        tablet, actor = _device(session, request, ctx)
        if tablet is None or actor is None:
            raise DraftFailed(UNLOCK, 423)
        actor.expires_at = _now() + timedelta(seconds=idle_seconds())
        body = _body(session, ctx, tablet, actor)
        session.commit()
        return TabletResult(body=body, actor_token=raw)


def _ctx() -> RequestContext:
    ctx = current_request()
    if ctx is None:
        raise DraftFailed("Sign in required.", 401)
    return ctx


def _real() -> RequestContext:
    ctx = _ctx()
    if ctx.pin_session:
        raise DraftFailed("Sign in to do that.", 403)
    return ctx


def _pin(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned.isdigit() or not 4 <= len(cleaned) <= 6:
        raise DraftFailed("Use a 4 to 6 digit PIN.", 422)
    return cleaned


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _locked(row: Membership | SharedTablet) -> bool:
    until = _aware(row.pin_locked_until)
    return until is not None and until > _now()


def _expire_lock(row: Membership | SharedTablet) -> None:
    until = _aware(row.pin_locked_until)
    if until is not None and until <= _now():
        row.pin_locked_until = None
        row.pin_failures = 0


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _membership(session: Session, venue_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    row = session.scalar(select(Membership).where(Membership.user_id == user_id, Membership.venue_id == venue_id))
    if row is None:
        raise NotFound("member not found")
    return row


def _token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, _digest(raw)


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(data: str) -> bytes:
    return urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _path(request: Request) -> str:
    path = request.url.path
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


def _method(request: Request) -> str:
    return request.method.upper()


def _tablet_for(session: Session, raw: str, venue_id: uuid.UUID) -> SharedTablet | None:
    if not raw:
        return None
    return session.scalar(
        select(SharedTablet).where(
            SharedTablet.token_hash == _digest(raw),
            SharedTablet.venue_id == venue_id,
            SharedTablet.enabled.is_(True),
        )
    )


def _live_actor(session: Session, tablet: SharedTablet, raw: str) -> TabletActor | None:
    if not raw:
        return None
    row = session.scalar(
        select(TabletActor).where(
            TabletActor.token_hash == _digest(raw),
            TabletActor.tablet_id == tablet.id,
            TabletActor.venue_id == tablet.venue_id,
        )
    )
    if row is None:
        return None
    expires = _aware(row.expires_at)
    if expires is None or expires <= _now():
        return None
    return row


def _as_user(session: Session, user_id: uuid.UUID, tablet: SharedTablet, *, pin_session: bool) -> RequestContext:
    user = session.get(User, user_id)
    venue = session.get(Venue, tablet.venue_id)
    membership = session.scalar(
        select(Membership).where(Membership.user_id == user_id, Membership.venue_id == tablet.venue_id)
    )
    if user is None or venue is None or membership is None:
        raise HTTPException(status_code=403, detail="No venue membership.")
    return RequestContext(
        user_id=user.id,
        email=user.email,
        name=user.name,
        venue_id=venue.id,
        organization_id=venue.organization_id,
        role=membership.role,
        pin_session=pin_session,
    )


def _device(
    session: Session, request: Request, ctx: RequestContext
) -> tuple[SharedTablet | None, TabletActor | None]:
    tablet = _tablet_for(session, request.cookies.get(TABLET_COOKIE) or "", ctx.venue_id)
    if tablet is None:
        return None, None
    return tablet, _live_actor(session, tablet, request.cookies.get(ACTOR_COOKIE) or "")


def _person(user: User, membership: Membership) -> dict:
    return {
        "user_id": str(user.id),
        "name": user.name or "",
        "role": membership.role,
        "position": membership.position,
    }


def _body(session: Session, ctx: RequestContext, tablet: SharedTablet | None, actor: TabletActor | None) -> dict:
    self_row = session.scalar(
        select(Membership).where(Membership.user_id == ctx.user_id, Membership.venue_id == ctx.venue_id)
    )
    can_manage = ctx.role in {OWNER, MANAGER} and not ctx.pin_session
    people = _candidates(session, ctx.venue_id) if tablet is not None and actor is None else []
    clearable = _clearable(session, ctx) if can_manage and tablet is None else []
    actor_person = None
    expires = None
    if actor is not None:
        user = session.get(User, actor.user_id)
        member = session.scalar(
            select(Membership).where(Membership.user_id == actor.user_id, Membership.venue_id == actor.venue_id)
        )
        if user is not None and member is not None:
            actor_person = _person(user, member)
        moment = _aware(actor.expires_at)
        expires = None if moment is None else moment.isoformat()
    return {
        "enabled": tablet is not None,
        "locked": tablet is not None and actor is None,
        "idle_seconds": idle_seconds(),
        "expires_at": expires,
        "pin_session": bool(ctx.pin_session),
        "can_manage": can_manage,
        "self_has_pin": bool(self_row and self_row.pin_hash),
        "actor": actor_person,
        "candidates": people,
        "clearable": clearable,
    }


def _candidates(session: Session, venue_id: uuid.UUID) -> list[dict]:
    rows = session.scalars(
        select(Membership).where(Membership.venue_id == venue_id, Membership.pin_hash.is_not(None))
    ).all()
    people = []
    for row in rows:
        user = session.get(User, row.user_id)
        if user is None:
            continue
        people.append(_person(user, row))
    people.sort(key=lambda item: (item["name"].casefold(), item["user_id"]))
    return people


def _clearable(session: Session, ctx: RequestContext) -> list[dict]:
    rows = session.scalars(
        select(Membership).where(Membership.venue_id == ctx.venue_id, Membership.pin_hash.is_not(None))
    ).all()
    people = []
    for row in rows:
        if ctx.role == MANAGER and row.role != STAFF:
            continue
        user = session.get(User, row.user_id)
        if user is None:
            continue
        people.append(_person(user, row))
    people.sort(key=lambda item: (item["name"].casefold(), item["user_id"]))
    return people


def _fail(session: Session, tablet: SharedTablet, member: Membership, venue_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    _expire_lock(tablet)
    _expire_lock(member)
    tablet_hit = _bump(tablet)
    member_hit = _bump(member)
    tripped = tablet_hit or member_hit
    if tripped:
        venue = _venue(session, venue_id)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            action="tablet.pin.lockout",
            entity_type="shared_tablet",
            entity_id=tablet.id,
            after={"user_id": str(user_id)},
        )
        logger.info("tablet pin lockout user=%s", user_id)
    return tripped


def _fail_tablet(session: Session, tablet: SharedTablet, venue_id: uuid.UUID) -> None:
    _expire_lock(tablet)
    if _bump(tablet):
        venue = _venue(session, venue_id)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            action="tablet.pin.lockout",
            entity_type="shared_tablet",
            entity_id=tablet.id,
            after={"user_id": ""},
        )
        logger.info("tablet pin lockout user=%s", "")


def _bump(row: Membership | SharedTablet) -> bool:
    row.pin_failures = int(row.pin_failures or 0) + 1
    if row.pin_failures < FAILURES:
        return False
    row.pin_locked_until = _now() + timedelta(seconds=LOCKOUT_SECONDS)
    return True
