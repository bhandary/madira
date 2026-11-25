"""Spend caps, a database request limit, and per-run metering.

The limiter counts ``agent_runs`` rows in the last 60 seconds. That works in
one process on SQLite and on Postgres without another service. Two app
processes that share a database see the same rows, so the count still holds.
A restart keeps the window. The trade-off is a write and a count on every
run, and requests that have not committed yet can overlap inside that write.
An in-memory limiter would be cheaper and would miss every other process and
every restart.

Demo runs store token estimates and a cost of zero labeled ``demo``. Live
runs price tokens from ``pricing.py``. Nothing is billed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from madira.db import SessionLocal
from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import NotFound
from madira.domain.usage.pricing import estimate_cost
from madira.llm_runtime import resolve_runtime
from madira.models import AgentRun, AgentUsage, Organization, Venue
from madira.tenancy import OWNER, current_request

CAP_BLOCKED = "usage.cap_blocked"
RATE_BLOCKED = "usage.rate_blocked"
LIMITS_UPDATED = "usage.limits_updated"
MICRO_PER_CENT = 10_000
MAX_RPM = 600


class UsageError(Exception):
    def __init__(self, message: str, status: int = 429) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _org(session: Session, organization_id: uuid.UUID) -> Organization:
    org = session.get(Organization, organization_id)
    if org is None:
        raise NotFound("organization not found")
    return org


def _actor(venue_id: uuid.UUID) -> tuple[uuid.UUID | None, str]:
    ctx = current_request()
    if ctx is None or ctx.venue_id != venue_id:
        return None, ""
    return ctx.user_id, ctx.email or ""


def _zone(venue: Venue) -> ZoneInfo:
    try:
        return ZoneInfo(venue.timezone or "America/Los_Angeles")
    except Exception:
        return ZoneInfo("America/Los_Angeles")


def _month_start(venue: Venue, now: datetime) -> datetime:
    local = now.astimezone(_zone(venue))
    return datetime(local.year, local.month, 1, tzinfo=_zone(venue)).astimezone(timezone.utc)


def _spent_micro(session: Session, organization_id: uuid.UUID, start: datetime) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(AgentUsage.cost_micro_usd), 0)).where(
            AgentUsage.organization_id == organization_id,
            AgentUsage.created_at >= start,
        )
    )
    return int(total or 0)


def _recent_runs(session: Session, organization_id: uuid.UUID, now: datetime) -> int:
    cutoff = now - timedelta(seconds=60)
    total = session.scalar(
        select(func.count()).select_from(AgentRun).where(
            AgentRun.organization_id == organization_id,
            AgentRun.created_at >= cutoff,
        )
    )
    return int(total or 0)


def _enforce(session: Session, venue: Venue, now: datetime) -> None:
    org = _org(session, venue.organization_id)
    actor_id, email = _actor(venue.id)
    cap = org.monthly_spend_cap_cents
    if cap is not None:
        spent = _spent_micro(session, org.id, _month_start(venue, now)) // MICRO_PER_CENT
        if spent >= int(cap):
            record_audit_event(
                session,
                org_id=org.id,
                venue_id=venue.id,
                action=CAP_BLOCKED,
                entity_type="organization",
                entity_id=org.id,
                after={"spent_cents": spent, "cap_cents": int(cap)},
                actor_user_id=actor_id,
                actor_email=email,
            )
            session.commit()
            raise UsageError(
                "This month's usage is at the cap. An Owner can raise it on the usage page."
            )
    rpm = org.requests_per_minute
    if rpm is not None:
        used = _recent_runs(session, org.id, now)
        if used >= int(rpm):
            record_audit_event(
                session,
                org_id=org.id,
                venue_id=venue.id,
                action=RATE_BLOCKED,
                entity_type="organization",
                entity_id=org.id,
                after={"requests_this_minute": used, "requests_per_minute": int(rpm)},
                actor_user_id=actor_id,
                actor_email=email,
            )
            session.commit()
            raise UsageError("Too many requests in the last minute. Wait a moment and try again.")


def begin_run(venue_id: uuid.UUID, message: str, *, now: datetime | None = None) -> uuid.UUID:
    """Refuse a run that is at the cap or over the request limit, then record it."""

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    session = SessionLocal()
    try:
        venue = _venue(session, venue_id)
        _enforce(session, venue, moment)
        run = AgentRun(
            venue_id=venue.id,
            organization_id=venue.organization_id,
            message=(message or "")[:2000],
            reply="",
            delegated=[],
            created_at=moment,
        )
        session.add(run)
        session.commit()
        return run.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _tokens(text: str) -> int:
    cleaned = text or ""
    if not cleaned.strip():
        return 0
    return max(1, len(cleaned) // 4)


def _split(total: int, parts: int) -> list[int]:
    if parts <= 0:
        return []
    base, extra = divmod(max(int(total), 0), parts)
    return [base + (1 if index < extra else 0) for index in range(parts)]


def finish_run(
    run_id: uuid.UUID,
    *,
    reply: str,
    delegated: list[str],
    latency_ms: int,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
) -> None:
    """Write one usage row per subagent. Demo cost is zero."""

    runtime = resolve_runtime()
    demo = bool(runtime.demo_mode)
    model = "madira-demo-fixtures" if demo else (runtime.model or "")
    incoming = 0 if tokens_in is None else max(int(tokens_in), 0)
    outgoing = _tokens(reply) if tokens_out is None else max(int(tokens_out), 0)
    names = [name.strip() for name in delegated if (name or "").strip()]
    if not names:
        names = ["head-sommelier"]
    shares_in = _split(incoming, len(names))
    shares_out = _split(outgoing, len(names))
    waited = max(int(latency_ms), 0)
    session = SessionLocal()
    try:
        run = session.get(AgentRun, run_id)
        if run is None or run.organization_id is None:
            return
        run.reply = (reply or "")[:4000]
        run.delegated = names
        for name, part_in, part_out in zip(names, shares_in, shares_out):
            micro, label = estimate_cost(model, part_in, part_out, demo=demo)
            session.add(
                AgentUsage(
                    organization_id=run.organization_id,
                    venue_id=run.venue_id,
                    agent_run_id=run.id,
                    subagent=name[:64],
                    model=model[:120],
                    tokens_in=part_in,
                    tokens_out=part_out,
                    cost_micro_usd=micro,
                    cost_label=label,
                    latency_ms=waited,
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _status_text(cap: int | None, spent_cents: int, rpm: int | None, used: int) -> str:
    if cap is None:
        cap_line = "No monthly cap."
    else:
        cap_line = f"Cap {int(cap)} cents. Spent {int(spent_cents)} cents."
    if rpm is None:
        rate_line = "No request limit."
    else:
        rate_line = f"Limit {int(rpm)} requests per minute. {int(used)} used."
    return f"{cap_line} {rate_line}"


def usage_report(venue_id: uuid.UUID, *, now: datetime | None = None) -> dict:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    session = SessionLocal()
    try:
        venue = _venue(session, venue_id)
        org = _org(session, venue.organization_id)
        start = _month_start(venue, moment)
        spent_micro = _spent_micro(session, org.id, start)
        spent_cents = spent_micro // MICRO_PER_CENT
        used = _recent_runs(session, org.id, moment)
        rows = session.scalars(
            select(AgentUsage)
            .where(AgentUsage.organization_id == org.id, AgentUsage.created_at >= start)
            .order_by(AgentUsage.created_at.asc(), AgentUsage.id.asc())
        ).all()
        by_sub: dict[str, dict] = {}
        by_day: dict[str, dict] = {}
        local_zone = _zone(venue)
        for row in rows:
            bucket = by_sub.setdefault(
                row.subagent,
                {"subagent": row.subagent, "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_micro_usd": 0},
            )
            bucket["calls"] += 1
            bucket["tokens_in"] += int(row.tokens_in)
            bucket["tokens_out"] += int(row.tokens_out)
            bucket["cost_micro_usd"] += int(row.cost_micro_usd)
            day = row.created_at.astimezone(local_zone).date().isoformat()
            day_bucket = by_day.setdefault(day, {"day": day, "calls": 0, "cost_micro_usd": 0})
            day_bucket["calls"] += 1
            day_bucket["cost_micro_usd"] += int(row.cost_micro_usd)
        ctx = current_request()
        return {
            "month": start.astimezone(local_zone).strftime("%Y-%m"),
            "monthly_spend_cap_cents": None if org.monthly_spend_cap_cents is None else int(org.monthly_spend_cap_cents),
            "spent_cents": spent_cents,
            "spent_micro_usd": spent_micro,
            "requests_per_minute": None if org.requests_per_minute is None else int(org.requests_per_minute),
            "requests_this_minute": used,
            "by_subagent": list(by_sub.values()),
            "by_day": list(by_day.values()),
            "cap_status": _status_text(org.monthly_spend_cap_cents, spent_cents, org.requests_per_minute, used),
            "can_edit": ctx is not None and ctx.role == OWNER and ctx.venue_id == venue.id,
            "demo": bool(resolve_runtime().demo_mode),
        }
    finally:
        session.close()


def update_limits(
    venue_id: uuid.UUID,
    *,
    monthly_spend_cap_cents: int | None,
    requests_per_minute: int | None,
) -> dict:
    if monthly_spend_cap_cents is not None and (
        isinstance(monthly_spend_cap_cents, bool) or not isinstance(monthly_spend_cap_cents, int) or monthly_spend_cap_cents < 0
    ):
        raise UsageError("The monthly cap is a whole number of cents, or empty to turn it off.", 422)
    if requests_per_minute is not None and (
        isinstance(requests_per_minute, bool)
        or not isinstance(requests_per_minute, int)
        or requests_per_minute < 1
        or requests_per_minute > MAX_RPM
    ):
        raise UsageError("The request limit is a whole number from 1 to 600, or empty to turn it off.", 422)
    session = SessionLocal()
    try:
        venue = _venue(session, venue_id)
        org = _org(session, venue.organization_id)
        before = {
            "monthly_spend_cap_cents": org.monthly_spend_cap_cents,
            "requests_per_minute": org.requests_per_minute,
        }
        org.monthly_spend_cap_cents = monthly_spend_cap_cents
        org.requests_per_minute = requests_per_minute
        actor_id, email = _actor(venue.id)
        record_audit_event(
            session,
            org_id=org.id,
            venue_id=venue.id,
            action=LIMITS_UPDATED,
            entity_type="organization",
            entity_id=org.id,
            before=before,
            after={
                "monthly_spend_cap_cents": monthly_spend_cap_cents,
                "requests_per_minute": requests_per_minute,
            },
            actor_user_id=actor_id,
            actor_email=email,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return usage_report(venue_id)
