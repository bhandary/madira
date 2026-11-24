"""Role checks for the section 8 capability matrix.

Sommelier approval is not spend-limited yet: there is no limit to enforce, so
Sommelier may draft purchase orders. A later purchasing change can add the cap.
"""

from __future__ import annotations

from enum import Enum

from fastapi import Depends, HTTPException, Request

from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, RequestContext, bind, resolve_request


class Capability(str, Enum):
    FLOOR = "floor"
    COUNT = "count"
    EDIT = "edit"
    APPROVE = "approve"
    RECORDS = "records"
    RECORDS_WRITE = "records_write"
    SETTINGS = "settings"
    AGENT = "agent"


MATRIX: dict[Capability, frozenset[str]] = {
    Capability.FLOOR: frozenset({OWNER, SOMMELIER, MANAGER, STAFF}),
    Capability.COUNT: frozenset({OWNER, SOMMELIER, MANAGER}),
    Capability.EDIT: frozenset({OWNER, SOMMELIER}),
    Capability.APPROVE: frozenset({OWNER, SOMMELIER}),
    Capability.RECORDS: frozenset({OWNER, SOMMELIER, MANAGER, AUDITOR}),
    # Upload into the document vault. Retention changes stay on SETTINGS (Owner).
    Capability.RECORDS_WRITE: frozenset({OWNER, SOMMELIER}),
    Capability.SETTINGS: frozenset({OWNER}),
    Capability.AGENT: frozenset({OWNER, SOMMELIER, MANAGER, STAFF}),
}


def require(capability: Capability):
    def dependency(request: Request) -> RequestContext:
        ctx = getattr(request.state, "context", None)
        if not isinstance(ctx, RequestContext):
            ctx = resolve_request(request)
            request.state.context = ctx
        if ctx.role not in MATRIX[capability]:
            raise HTTPException(status_code=403, detail="This role cannot do that.")
        # Sync handlers run in a worker thread. Bind again so that copy sees the venue.
        bind(ctx)
        return ctx

    return Depends(dependency)
