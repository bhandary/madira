"""Role checks for the section 8 capability matrix.

Every purchase order needs an Owner decision. There is no spend threshold and
no auto-approve. Sommelier may still draft on the original reorder route.
Approve and reject on the lifecycle routes use PO_DECIDE, which is Owner only.
"""

from __future__ import annotations

from enum import Enum

from fastapi import Depends, HTTPException, Request

from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, RequestContext, bind, resolve_request


class Capability(str, Enum):
    FLOOR = "floor"
    COUNT = "count"
    # Read the cellar, locations, bins, the stock ledger, counts, and par proposals.
    # Count writes, variance approval, and par decisions use COUNT (Owner, Sommelier, Manager).
    # Spend approval stays on APPROVE.
    INVENTORY_READ = "inventory_read"
    EDIT = "edit"
    APPROVE = "approve"
    RECORDS = "records"
    RECORDS_WRITE = "records_write"
    SETTINGS = "settings"
    AGENT = "agent"
    # Read suppliers and purchase orders. Staff is not included.
    PO_READ = "po_read"
    # Draft, send, close, and cancel. Not approve.
    PO_WRITE = "po_write"
    # Approve or reject a purchase order. Owner only, at every amount.
    PO_DECIDE = "po_decide"
    # Preview and download an audit pack, and read the gap report.
    # Auditor stays read-only: exporting writes an internal audit event, not a business record.
    AUDIT_PACK = "audit_pack"
    # Read approved lessons and take quizzes. Auditor is not included.
    TRAINING_LEARN = "training_learn"
    # Edit standards and draft or approve lessons. Owner and Sommelier.
    TRAINING_AUTHOR = "training_author"
    # Invite, change roles, remove memberships, and write certificates. Owner and Manager.
    TEAM_MANAGE = "team_manage"
    # Read the roster and team progress. Owner, Sommelier, and Manager.
    TEAM_VIEW = "team_view"
    # Submit a list version for publication. Owner and Sommelier.
    LIST_PUBLISH_SUBMIT = "list_publish_submit"
    # Approve or reject a list version. Owner only.
    LIST_PUBLISH_DECIDE = "list_publish_decide"


MATRIX: dict[Capability, frozenset[str]] = {
    Capability.FLOOR: frozenset({OWNER, SOMMELIER, MANAGER, STAFF}),
    Capability.COUNT: frozenset({OWNER, SOMMELIER, MANAGER}),
    Capability.INVENTORY_READ: frozenset({OWNER, SOMMELIER, MANAGER, AUDITOR}),
    Capability.EDIT: frozenset({OWNER, SOMMELIER}),
    Capability.APPROVE: frozenset({OWNER, SOMMELIER}),
    Capability.RECORDS: frozenset({OWNER, SOMMELIER, MANAGER, AUDITOR}),
    # Upload into the document vault. Retention changes stay on SETTINGS (Owner).
    Capability.RECORDS_WRITE: frozenset({OWNER, SOMMELIER}),
    Capability.SETTINGS: frozenset({OWNER}),
    Capability.AGENT: frozenset({OWNER, SOMMELIER, MANAGER, STAFF}),
    Capability.PO_READ: frozenset({OWNER, SOMMELIER, MANAGER, AUDITOR}),
    Capability.PO_WRITE: frozenset({OWNER, SOMMELIER, MANAGER}),
    Capability.PO_DECIDE: frozenset({OWNER}),
    Capability.AUDIT_PACK: frozenset({OWNER, MANAGER, AUDITOR}),
    Capability.TRAINING_LEARN: frozenset({OWNER, SOMMELIER, MANAGER, STAFF}),
    Capability.TRAINING_AUTHOR: frozenset({OWNER, SOMMELIER}),
    Capability.TEAM_MANAGE: frozenset({OWNER, MANAGER}),
    Capability.TEAM_VIEW: frozenset({OWNER, SOMMELIER, MANAGER}),
    Capability.LIST_PUBLISH_SUBMIT: frozenset({OWNER, SOMMELIER}),
    Capability.LIST_PUBLISH_DECIDE: frozenset({OWNER}),
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
