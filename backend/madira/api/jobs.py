"""Read one job. The payload stays in the table."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from madira.jobs.handlers import KIND_CAPABILITY
from madira.jobs.queue import job_for_venue, public_job
from madira.rbac import MATRIX
from madira.tenancy import RequestContext, resolve_request

router = APIRouter(tags=["jobs"])


def _context(request: Request) -> RequestContext:
    ctx = getattr(request.state, "context", None)
    if isinstance(ctx, RequestContext):
        return ctx
    return resolve_request(request)


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, request: Request) -> dict[str, Any]:
    ctx = _context(request)
    job = job_for_venue(job_id, ctx.venue_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    capability = KIND_CAPABILITY.get(job.kind)
    if capability is None or ctx.role not in MATRIX[capability]:
        raise HTTPException(403, "This role cannot do that.")
    return public_job(job)
