"""Par suggestions from trailing depletion.

    daily_rate = depletion_30d / 30
    proposed_par = max(1, ceil(daily_rate * (lead_time_days + safety_days)))

When the last 30 days show no depletion, the current par is kept and no
proposal is written. Accepting a proposal updates ``skus.par`` in the same
transaction as the audit event. The cellar reads par from the SKU.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import Rejected, as_qty, depletion_by_sku, public_qty
from madira.domain.session import session_scope
from madira.models import InventoryItem, ParProposal, Sku, Venue

ACTION_UPDATED = "par.updated"
ACTION_REJECTED = "par.rejected"


def _uuid(value, label: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise NotFound(f"{label} not found") from exc


def _actor(actor) -> tuple[uuid.UUID | None, str]:
    if actor is None:
        return None, ""
    return getattr(actor, "user_id", None), (getattr(actor, "email", "") or "")


def _days(value, label: str, default: int) -> int:
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise Rejected(f"{label} must be a whole number") from exc
    if number < 0:
        raise Rejected(f"{label} cannot be negative")
    if number > 365:
        raise Rejected(f"{label} is too large")
    return number


def suggested_par(depletion, current_par: int, lead_time_days: int = 7, safety_days: int = 4) -> tuple[int, str]:
    """Return the proposed integer par and a short rationale."""

    used = as_qty(depletion)
    current = int(current_par or 0)
    if used <= 0:
        return current, "No depletion in the last 30 days, so par stays at the current level."
    daily = used / Decimal(30)
    cover = Decimal(int(lead_time_days) + int(safety_days))
    proposed = int((daily * cover).to_integral_value(rounding=ROUND_CEILING))
    if proposed < 1:
        proposed = 1
    shown = public_qty(used)
    rationale = (
        f"30-day depletion {shown} over 30 days, with {lead_time_days} lead days "
        f"and {safety_days} safety days, proposes par {proposed}."
    )
    return proposed, rationale


def _name(stock: Sku) -> str:
    try:
        return stock.variant.product.name
    except Exception:
        return stock.barcode


def _public(row: ParProposal, stock: Sku) -> dict:
    return {
        "id": str(row.id),
        "venue_id": str(row.venue_id),
        "sku_id": str(row.sku_id),
        "sku": stock.barcode,
        "name": _name(stock),
        "current_par": int(row.current_par),
        "proposed_par": int(row.proposed_par),
        "depletion_30d": public_qty(row.depletion_30d),
        "lead_time_days": int(row.lead_time_days),
        "safety_days": int(row.safety_days),
        "rationale": row.rationale or "",
        "status": row.status,
        "proposed_by": row.proposed_by,
        "decided_by_user_id": None if row.decided_by_user_id is None else str(row.decided_by_user_id),
        "decided_at": None if row.decided_at is None else row.decided_at.isoformat(),
        "created_at": None if row.created_at is None else row.created_at.isoformat(),
    }


def _run(fn):
    with session_scope() as session:
        try:
            result = fn(session)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise


def list_par_proposals(venue_id: uuid.UUID, status: str | None = None) -> dict:
    venue_id = _uuid(venue_id, "venue")

    def read(session: Session) -> dict:
        stmt = (
            select(ParProposal, Sku)
            .join(Sku, Sku.id == ParProposal.sku_id)
            .where(ParProposal.venue_id == venue_id)
            .order_by(Sku.barcode, ParProposal.created_at.desc())
        )
        if status:
            cleaned = status.strip()
            if cleaned not in {"pending", "accepted", "rejected"}:
                raise Rejected("status must be pending, accepted, or rejected")
            stmt = stmt.where(ParProposal.status == cleaned)
        rows = session.execute(stmt).all()
        return {"proposals": [_public(row, stock) for row, stock in rows]}

    return _run(read)


def propose_par_changes(
    venue_id: uuid.UUID,
    lead_time_days: int = 7,
    safety_days: int = 4,
    proposed_by: str = "cellar-manager",
) -> dict:
    """Write a pending proposal for every SKU whose suggested par differs."""

    venue_id = _uuid(venue_id, "venue")
    lead = _days(lead_time_days, "lead_time_days", 7)
    safety = _days(safety_days, "safety_days", 4)
    author = (proposed_by or "cellar-manager").strip() or "cellar-manager"
    if len(author) > 80:
        raise Rejected("proposed_by is too long")

    def write(session: Session) -> dict:
        if session.get(Venue, venue_id) is None:
            raise NotFound("venue not found")
        items = session.scalars(select(InventoryItem).where(InventoryItem.venue_id == venue_id)).all()
        depletion = depletion_by_sku(session, venue_id)
        seen: set[uuid.UUID] = set()
        created: list[ParProposal] = []
        moment = datetime.now(timezone.utc)
        for item in items:
            if item.sku_id in seen:
                continue
            seen.add(item.sku_id)
            stock = session.get(Sku, item.sku_id)
            if stock is None or stock.venue_id != venue_id:
                continue
            current = int(stock.par or 0)
            used = depletion.get(item.sku_id, Decimal("0"))
            proposed, rationale = suggested_par(used, current, lead, safety)
            pending = session.scalars(
                select(ParProposal).where(
                    ParProposal.venue_id == venue_id,
                    ParProposal.sku_id == stock.id,
                    ParProposal.status == "pending",
                )
            ).all()
            for old in pending:
                old.status = "rejected"
                old.decided_at = moment
                note = (old.rationale or "").rstrip()
                old.rationale = f"{note} Superseded by a newer proposal.".strip()
            if proposed == current:
                continue
            row = ParProposal(
                venue_id=venue_id,
                sku_id=stock.id,
                current_par=current,
                proposed_par=proposed,
                depletion_30d=as_qty(used),
                lead_time_days=lead,
                safety_days=safety,
                rationale=rationale,
                status="pending",
                proposed_by=author,
                created_at=moment,
            )
            session.add(row)
            created.append(row)
        session.flush()
        stocks = {}
        for row in created:
            stocks[row.sku_id] = session.get(Sku, row.sku_id)
        proposals = [_public(row, stocks[row.sku_id]) for row in created]
        proposals.sort(key=lambda item: item["sku"])
        return {"proposals": proposals}

    return _run(write)


def decide_par_proposal(venue_id: uuid.UUID, proposal_id: uuid.UUID, decision: str, actor) -> dict:
    """Accept updates skus.par. Reject leaves par as it is. Both write an audit event."""

    venue_id = _uuid(venue_id, "venue")
    proposal_id = _uuid(proposal_id, "proposal")
    choice = (decision or "").strip().lower()
    if choice not in {"accept", "reject"}:
        raise Rejected("decision must be accept or reject")
    user_id, email = _actor(actor)

    def write(session: Session) -> dict:
        venue = session.get(Venue, venue_id)
        if venue is None:
            raise NotFound("venue not found")
        row = session.get(ParProposal, proposal_id)
        if row is None or row.venue_id != venue_id:
            raise NotFound("proposal not found")
        if row.status != "pending":
            raise Rejected("Proposal is not pending.", 409)
        stock = session.get(Sku, row.sku_id)
        if stock is None or stock.venue_id != venue_id:
            raise NotFound("proposal not found")
        current = int(stock.par or 0)
        moment = datetime.now(timezone.utc)
        row.decided_by_user_id = user_id
        row.decided_at = moment
        if choice == "accept":
            stock.par = int(row.proposed_par)
            row.status = "accepted"
            action = ACTION_UPDATED
            after = {"sku": stock.barcode, "par": int(row.proposed_par), "proposal_id": str(row.id)}
        else:
            row.status = "rejected"
            action = ACTION_REJECTED
            after = {"sku": stock.barcode, "par": current, "status": "rejected", "proposal_id": str(row.id)}
        session.flush()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=action,
            entity_type="sku",
            entity_id=stock.id,
            before={"sku": stock.barcode, "par": current, "proposed_par": int(row.proposed_par)},
            after=after,
            actor_user_id=user_id,
            actor_email=email,
        )
        return _public(row, stock)

    return _run(write)
