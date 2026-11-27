"""Request tenancy: the signed-in user, their venue, and their role.

The venue is stored on a context variable before a handler or tool runs. It is
not a tool argument. On Postgres, the same value is applied as
``SELECT set_config('app.venue_id', ..., true)`` (SET LOCAL) at the start of
each transaction so row-level security can see it. SQLite has no RLS; queries
still filter on ``venue_id``.
"""

from __future__ import annotations

import os
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.auth import SESSION_COOKIE, session_subject, utcnow
from madira.csrf import reject as reject_csrf
from madira.db import SessionLocal
from madira.models import ROLES, Membership, Organization, User, Venue

DEMO_ORG_SLUG = "maison-madira"
DEMO_VENUE_SLUG = "maison-madira"
DEMO_USER_SUB = "madira-demo-owner"
DEMO_USER_EMAIL = "owner@maison-madira.demo"
DEMO_USER_NAME = "Demo Owner"
DEMO_PERSONA_COOKIE = "madira_demo_persona"

OWNER = "Owner"
SOMMELIER = "Sommelier"
MANAGER = "Manager"
STAFF = "Staff"
AUDITOR = "Auditor"

# Demo floor users. The cookie is honored only while demo_posture() is true.
_DEMO_PERSONAS = (
    ("ana", "madira-demo-ana", "ana@maison-madira.demo", "Ana", STAFF, "server"),
    ("ben", "madira-demo-ben", "ben@maison-madira.demo", "Ben", STAFF, "bartender"),
    ("mia", "madira-demo-mia", "mia@maison-madira.demo", "Mia", MANAGER, None),
    ("lea", "madira-demo-lea", "lea@maison-madira.demo", "Lea", SOMMELIER, None),
)

_request: ContextVar[RequestContext | None] = ContextVar("madira_request_context", default=None)


@dataclass(frozen=True)
class RequestContext:
    user_id: uuid.UUID
    email: str
    name: str
    venue_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    # True when this request is a PIN switch on a shared tablet, not a Google sign-in.
    pin_session: bool = False


def current_request() -> RequestContext | None:
    return _request.get()


def bind(ctx: RequestContext) -> Token:
    return _request.set(ctx)


def reset(token: Token) -> None:
    _request.reset(token)


def demo_posture() -> bool:
    """True only while the model itself is in demo mode.

    This is ``resolve_runtime().demo_mode``: no environment provider key, no
    usable saved credential, and ``MADIRA_DEMO_MODE`` is not false.
    ``MADIRA_DEMO_MODE=true`` still forces the fixture demo. A saved key, an
    environment key, or ``MADIRA_DEMO_MODE=false`` makes the model live and
    turns this fallback off, so a request with no session is 401.
    """

    from madira.llm_runtime import resolve_runtime

    return resolve_runtime().demo_mode


def _context_from(user: User, membership: Membership, venue: Venue) -> RequestContext:
    if membership.role not in ROLES:
        raise HTTPException(status_code=403, detail="This role cannot do that.")
    return RequestContext(
        user_id=user.id,
        email=user.email,
        name=user.name,
        venue_id=venue.id,
        organization_id=venue.organization_id,
        role=membership.role,
    )


def ensure_demo_tenant(session: Session | None = None) -> RequestContext:
    """Create the demo organization, venue, and Owner if they are missing."""

    own = session is None
    if session is None:
        session = SessionLocal()
    try:
        org = session.scalar(select(Organization).where(Organization.slug == DEMO_ORG_SLUG))
        if org is None:
            org = Organization(name="Maison Madira", slug=DEMO_ORG_SLUG)
            session.add(org)
            session.flush()
        venue = session.scalar(
            select(Venue).where(Venue.organization_id == org.id, Venue.slug == DEMO_VENUE_SLUG)
        )
        if venue is None:
            venue = Venue(organization_id=org.id, name="Maison Madira", slug=DEMO_VENUE_SLUG)
            session.add(venue)
            session.flush()
        user = session.scalar(select(User).where(User.google_sub == DEMO_USER_SUB))
        now = utcnow()
        if user is None:
            user = User(
                google_sub=DEMO_USER_SUB,
                email=DEMO_USER_EMAIL,
                name=DEMO_USER_NAME,
                picture="",
                created_at=now,
                last_login_at=now,
            )
            session.add(user)
            session.flush()
        membership = session.scalar(
            select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue.id)
        )
        if membership is None:
            membership = Membership(user_id=user.id, venue_id=venue.id, role=OWNER)
            session.add(membership)
            session.flush()
        elif membership.role != OWNER:
            membership.role = OWNER
        _ensure_demo_personas(session, venue, now)
        ctx = _context_from(user, membership, venue)
        session.commit()
        return ctx
    except Exception:
        session.rollback()
        raise
    finally:
        if own:
            session.close()


def default_venue(session: Session) -> Venue | None:
    venue = session.scalar(select(Venue).where(Venue.slug == DEMO_VENUE_SLUG).order_by(Venue.id))
    if venue is not None:
        return venue
    return session.scalar(select(Venue).order_by(Venue.id))


def grant_configured_owner(session: Session, user: User) -> None:
    """Give ``MADIRA_OWNER_EMAIL`` the Owner role on the default venue."""

    expected = os.environ.get("MADIRA_OWNER_EMAIL", "").strip().lower()
    email = (user.email or "").strip().lower()
    if not expected or email != expected:
        return
    venue = default_venue(session)
    if venue is None:
        return
    if user.id is None:
        session.flush()
    membership = session.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue.id)
    )
    if membership is None:
        session.add(Membership(user_id=user.id, venue_id=venue.id, role=OWNER))
    else:
        membership.role = OWNER


def _ensure_user(session: Session, *, sub: str, email: str, name: str, now) -> User:
    user = session.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = User(google_sub=sub, email=email, name=name, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
        return user
    if user.name != name:
        user.name = name
    if user.email != email:
        user.email = email
    return user


def _ensure_demo_personas(session: Session, venue: Venue, now) -> None:
    for _slug, sub, email, name, role, position in _DEMO_PERSONAS:
        user = _ensure_user(session, sub=sub, email=email, name=name, now=now)
        membership = session.scalar(
            select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue.id)
        )
        if membership is None:
            session.add(Membership(user_id=user.id, venue_id=venue.id, role=role, position=position))
            continue
        membership.role = role
        membership.position = position
    session.flush()


def persona_context(session: Session, slug: str) -> RequestContext | None:
    """The demo persona for a cookie value, or None when the slug is not one of them."""

    slug = (slug or "").strip().lower()
    spec = next((row for row in _DEMO_PERSONAS if row[0] == slug), None)
    if spec is None:
        return None
    _slug, sub, _email, _name, _role, _position = spec
    user = session.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        return None
    venue = session.scalar(select(Venue).where(Venue.slug == DEMO_VENUE_SLUG).order_by(Venue.id))
    if venue is None:
        return None
    membership = session.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue.id)
    )
    if membership is None:
        return None
    return _context_from(user, membership, venue)


def demo_persona_catalog() -> list[dict]:
    """Names and roles for the demo switcher. Empty unless the model is in demo mode."""

    if not demo_posture():
        return []
    ensure_demo_tenant()
    session = SessionLocal()
    try:
        catalog = [
            {"slug": "owner", "name": DEMO_USER_NAME, "role": OWNER, "position": None, "email": DEMO_USER_EMAIL}
        ]
        for slug, sub, email, name, role, position in _DEMO_PERSONAS:
            user = session.scalar(select(User).where(User.google_sub == sub))
            catalog.append(
                {
                    "slug": slug,
                    "name": user.name if user is not None else name,
                    "role": role,
                    "position": position,
                    "email": email,
                }
            )
        return catalog
    finally:
        session.close()


def _as_uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def active_venue_id() -> uuid.UUID:
    ctx = _request.get()
    if ctx is not None:
        return ctx.venue_id
    try:
        from langchain_core.runnables.config import var_child_runnable_config

        config = var_child_runnable_config.get(None)
    except Exception:
        config = None
    if isinstance(config, dict):
        raw = (config.get("configurable") or {}).get("madira_venue_id")
        if raw:
            return _as_uuid(raw)
    if demo_posture():
        return ensure_demo_tenant().venue_id
    raise RuntimeError("No venue in the run context.")


def current_organization_id() -> uuid.UUID:
    ctx = _request.get()
    if ctx is not None:
        return ctx.organization_id
    # Health and startup resolve a saved key with no request. That row belongs
    # to the default organization. Data routes never reach here: they bind first.
    return ensure_demo_tenant().organization_id


def scoped_get(session: Session, model, pk: uuid.UUID):
    row = session.get(model, pk)
    if row is None or getattr(row, "venue_id", None) != active_venue_id():
        return None
    return row


def resolve_request(request: Request) -> RequestContext:
    sub = session_subject(request.cookies.get(SESSION_COOKIE))
    session = SessionLocal()
    try:
        if sub:
            user = session.scalar(select(User).where(User.google_sub == sub))
            if user is None:
                raise HTTPException(status_code=401, detail="Sign in required.")
            membership = session.scalar(
                select(Membership).where(Membership.user_id == user.id).order_by(Membership.id)
            )
            if membership is None:
                raise HTTPException(status_code=403, detail="No venue membership.")
            venue = session.get(Venue, membership.venue_id)
            if venue is None:
                raise HTTPException(status_code=403, detail="No venue membership.")
            host = _context_from(user, membership, venue)
        elif demo_posture():
            host = ensure_demo_tenant(session)
            # A real session already returned above. This cookie is demo-only.
            slug = (request.cookies.get(DEMO_PERSONA_COOKIE) or "").strip().lower()
            if slug and slug != "owner":
                switched = persona_context(session, slug)
                if switched is not None:
                    host = switched
        else:
            raise HTTPException(status_code=401, detail="Sign in required.")
    finally:
        session.close()
    from madira.domain.tablet import overlay_tablet

    return overlay_tablet(request, host)


_EXEMPT = {"/health", "/status", "/fixtures/sample-menu", "/docs", "/redoc", "/openapi.json"}


def _exempt(path: str) -> bool:
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if path in _EXEMPT or path.startswith("/auth"):
        return True
    # The guest list is a projection. It does not use a venue session.
    if path.startswith("/public/lists/"):
        return True
    # Signed by the sensor secret. There is no session, and the venue comes from the sensor row.
    if path.startswith("/sensors/webhook/"):
        return True
    return False


class TenancyMiddleware:
    """Resolve the caller before the handler. Health, auth, and the sample menu stay open."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        path = request.url.path
        blocked = reject_csrf(request)
        if blocked is not None:
            await blocked(scope, receive, send)
            return
        if _exempt(path):
            await self.app(scope, receive, send)
            return
        try:
            ctx = resolve_request(request)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            await response(scope, receive, send)
            return
        if path == "/ag-ui" or path.startswith("/ag-ui/"):
            from madira.rbac import MATRIX, Capability

            if ctx.role not in MATRIX[Capability.AGENT]:
                response = JSONResponse({"detail": "This role cannot do that."}, status_code=403)
                await response(scope, receive, send)
                return
        request.state.context = ctx
        token = bind(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            reset(token)
