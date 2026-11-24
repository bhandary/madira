"""Who may read or write training, and which floor position a lesson is for."""

from __future__ import annotations

from madira.domain.errors import DraftFailed
from madira.tenancy import MANAGER, OWNER, SOMMELIER, STAFF, RequestContext, current_request, demo_posture

POSITIONS = ("server", "bartender", "barback", "host", "all")
MEMBER_POSITIONS = ("server", "bartender", "barback", "host")
LEARN_ROLES = frozenset({OWNER, SOMMELIER, MANAGER, STAFF})
AUTHOR_ROLES = frozenset({OWNER, SOMMELIER})


def actor() -> RequestContext:
    ctx = current_request()
    if ctx is not None:
        return ctx
    if demo_posture():
        from madira.tenancy import ensure_demo_tenant

        return ensure_demo_tenant()
    raise DraftFailed("Sign in required.", 401)


def require_learn(ctx: RequestContext) -> None:
    if ctx.role not in LEARN_ROLES:
        raise DraftFailed("This role cannot do that.", 403)


def require_author(ctx: RequestContext) -> None:
    if ctx.role not in AUTHOR_ROLES:
        raise DraftFailed("This role cannot do that.", 403)


def check_position(position: str) -> str:
    cleaned = (position or "").strip().lower()
    if cleaned not in POSITIONS:
        raise DraftFailed("Position must be server, bartender, barback, host, or all.", 422)
    return cleaned
