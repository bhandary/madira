"""Tasting invite proposals. Delivery runs only after an Owner or Manager approves.

Suggested times come from the venue briefing hour. Gaps and sample names come
from services. The model may phrase one agenda sentence and must not supply
counts. Demo mode uses the deterministic model. Live mode calls the real model
and fails when that call fails. The delivery driver writes a calendar file and
an email draft. It does not send either.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.session import session_scope
from madira.domain.tastings.invite_delivery import InvitePackage, get_invite_delivery
from madira.domain.tastings.service import TastingError, _actor, _owned_session, _venue
from madira.models import (
    Approval,
    Membership,
    Product,
    Sample,
    SourcingBrief,
    Supplier,
    SupplierContact,
    TastingInvite,
    TastingInviteAttendee,
    TastingInviteSlot,
    User,
    Venue,
    WantItem,
)
from madira.tenancy import MANAGER, OWNER, current_request, demo_posture
from madira.timestamps import format_wall, parse_stamp

_agenda_override = None
_SLOT_MINUTES = 90


def set_agenda_completer(fn) -> None:
    """Tests inject the agenda writer. Production leaves this unset."""

    global _agenda_override
    _agenda_override = fn


def suggested_slots(venue_id: uuid.UUID, session_id: uuid.UUID) -> list[dict]:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        tasting = _owned_session(session, venue_id, session_id)
        return _suggestions(venue, tasting.starts_at)


def desk(venue_id: uuid.UUID, session_id: uuid.UUID) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        tasting = _owned_session(session, venue_id, session_id)
        invite = _invite_for(session, venue_id, tasting.id)
        return _desk(session, venue, tasting, invite)


def propose(
    venue_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    slots: list[dict] | None = None,
    staff_user_ids: list[str] | None = None,
) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        tasting = _owned_session(session, venue_id, session_id)
        existing = _invite_for(session, venue_id, tasting.id)
        if existing is not None and existing.status == "ready":
            raise TastingError("This tasting invite is already ready.", 409)
        chosen = _suggestions(venue, tasting.starts_at) if slots is None else slots
        parsed = _parse_slots(chosen)
        facts = _agenda_facts(session, venue, tasting)
        people = _attendee_rows(session, venue, tasting, staff_user_ids)
    note = _agenda_sentence(facts)
    with session_scope() as session:
        venue = _venue(session, venue_id)
        tasting = _owned_session(session, venue_id, session_id)
        now = datetime.now(timezone.utc)
        invite = _invite_for(session, venue_id, tasting.id)
        created = invite is None
        if invite is None:
            actor = _actor()
            invite = TastingInvite(
                venue_id=venue.id,
                session_id=tasting.id,
                status="proposed",
                agenda_note=note,
                agenda_facts=facts,
                ics_text="",
                email_subject="",
                email_body="",
                email_mailto="",
                driver="",
                sent=False,
                created_by_user_id=None if actor is None else actor[0],
                created_at=now,
                updated_at=now,
            )
            session.add(invite)
            session.flush()
        else:
            session.execute(delete(TastingInviteSlot).where(TastingInviteSlot.invite_id == invite.id))
            session.execute(delete(TastingInviteAttendee).where(TastingInviteAttendee.invite_id == invite.id))
            invite.status = "proposed"
            invite.agenda_note = note
            invite.agenda_facts = facts
            invite.ics_text = ""
            invite.email_subject = ""
            invite.email_body = ""
            invite.email_mailto = ""
            invite.driver = ""
            invite.sent = False
            invite.updated_at = now
            session.flush()
        for index, (start, end, source) in enumerate(parsed):
            session.add(
                TastingInviteSlot(
                    venue_id=venue.id,
                    invite_id=invite.id,
                    position=index,
                    starts_at=start,
                    ends_at=end,
                    source=source,
                    chosen=index == 0,
                )
            )
        for index, person in enumerate(people):
            session.add(
                TastingInviteAttendee(
                    venue_id=venue.id,
                    invite_id=invite.id,
                    kind=person["kind"],
                    name=person["name"],
                    email=person["email"],
                    user_id=person["user_id"],
                    position=index,
                )
            )
        approval = None if invite.approval_id is None else session.get(Approval, invite.approval_id)
        if approval is None or approval.decision != "pending" or approval.venue_id != venue.id:
            approval = Approval(
                venue_id=venue.id,
                entity_type="tasting_invite",
                entity_id=invite.id,
                decision="pending",
                required_role="owner_or_manager",
                created_at=now,
            )
            session.add(approval)
            session.flush()
            invite.approval_id = approval.id
        actor = _actor()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            action="tasting_invite.proposed" if created else "tasting_invite.updated",
            entity_type="tasting_invite",
            entity_id=invite.id,
            after={"status": "proposed", "slots": len(parsed), "attendees": len(people)},
            actor_user_id=None if actor is None else actor[0],
            actor_email=None if actor is None else actor[1],
        )
        session.commit()
    return desk(venue_id, session_id)


def approve(
    venue_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    slot_index: int | None = None,
    comment: str = "",
) -> dict:
    _require_decider()
    with session_scope() as session:
        venue = _venue(session, venue_id)
        tasting = _owned_session(session, venue_id, session_id)
        invite = _require_invite(session, venue_id, tasting.id)
        if invite.status == "ready":
            return _desk(session, venue, tasting, invite)
        if invite.status != "proposed":
            raise TastingError("This tasting invite is not waiting for approval.", 409)
        slots = _slots(session, invite.id)
        if not slots:
            raise TastingError("Choose a time.", 422)
        chosen = _choose(slots, slot_index)
        for slot in slots:
            slot.chosen = slot.id == chosen.id
        attendees = _attendees(session, invite.id)
        package = InvitePackage(
            invite_id=invite.id,
            title=tasting.title or "Tasting",
            location=tasting.location or "",
            starts_at=chosen.starts_at,
            ends_at=chosen.ends_at,
            agenda_note=invite.agenda_note or "",
            facts_text=_facts_text(invite.agenda_facts or {}, chosen.starts_at, chosen.ends_at, attendees),
            attendees=[{"name": row.name, "email": row.email} for row in attendees],
            to_email=_rep_email(attendees),
        )
        draft = get_invite_delivery(venue).deliver(package)
        if draft.sent or draft.driver != "draft_only":
            raise TastingError("Invite delivery must not send.", 422)
        now = datetime.now(timezone.utc)
        invite.status = "ready"
        invite.ics_text = draft.ics_text
        invite.email_subject = draft.subject
        invite.email_body = draft.body
        invite.email_mailto = draft.mailto
        invite.driver = draft.driver
        invite.sent = False
        invite.updated_at = now
        approval = None if invite.approval_id is None else session.get(Approval, invite.approval_id)
        actor = _actor()
        if approval is not None and approval.venue_id == venue.id:
            approval.decision = "approved"
            approval.decided_at = now
            approval.comment = _comment(comment)
            approval.decided_by_user_id = None if actor is None else actor[0]
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            action="tasting_invite.approved",
            entity_type="tasting_invite",
            entity_id=invite.id,
            after={"status": "ready", "slot": format_wall(chosen.starts_at), "sent": False, "driver": draft.driver},
            actor_user_id=None if actor is None else actor[0],
            actor_email=None if actor is None else actor[1],
        )
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            action="tasting_invite.ready",
            entity_type="tasting_invite",
            entity_id=invite.id,
            after={"status": "ready", "sent": False},
            actor_user_id=None if actor is None else actor[0],
            actor_email=None if actor is None else actor[1],
        )
        session.commit()
        return _desk(session, venue, tasting, invite)


def reject(venue_id: uuid.UUID, session_id: uuid.UUID, *, comment: str = "") -> dict:
    _require_decider()
    with session_scope() as session:
        venue = _venue(session, venue_id)
        tasting = _owned_session(session, venue_id, session_id)
        invite = _require_invite(session, venue_id, tasting.id)
        if invite.status == "rejected":
            return _desk(session, venue, tasting, invite)
        if invite.status != "proposed":
            raise TastingError("This tasting invite is not waiting for approval.", 409)
        now = datetime.now(timezone.utc)
        invite.status = "rejected"
        invite.sent = False
        invite.updated_at = now
        approval = None if invite.approval_id is None else session.get(Approval, invite.approval_id)
        actor = _actor()
        if approval is not None and approval.venue_id == venue.id:
            approval.decision = "rejected"
            approval.decided_at = now
            approval.comment = _comment(comment)
            approval.decided_by_user_id = None if actor is None else actor[0]
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            action="tasting_invite.rejected",
            entity_type="tasting_invite",
            entity_id=invite.id,
            after={"status": "rejected", "sent": False},
            actor_user_id=None if actor is None else actor[0],
            actor_email=None if actor is None else actor[1],
        )
        session.commit()
        return _desk(session, venue, tasting, invite)


def ics_text(venue_id: uuid.UUID, session_id: uuid.UUID) -> str:
    with session_scope() as session:
        tasting = _owned_session(session, venue_id, session_id)
        invite = _require_invite(session, venue_id, tasting.id)
        if invite.status != "ready" or not invite.ics_text:
            raise TastingError("Approve the invite before downloading the calendar.", 409)
        return invite.ics_text


def _desk(session: Session, venue: Venue, tasting, invite: TastingInvite | None) -> dict:
    return {
        "suggestions": _suggestions(venue, tasting.starts_at),
        "staff": _staff(session, venue.id),
        "rep": _rep(session, venue, tasting),
        "can_decide": _can_decide(),
        "invite": None if invite is None else _public(session, tasting, invite),
    }


def _public(session: Session, tasting, invite: TastingInvite) -> dict:
    approval = None if invite.approval_id is None else session.get(Approval, invite.approval_id)
    slots = _slots(session, invite.id)
    chosen = next((slot for slot in slots if slot.chosen), None)
    ready = invite.status == "ready"
    supplier = "" if tasting.supplier is None else tasting.supplier.name
    return {
        "id": str(invite.id),
        "session_id": str(tasting.id),
        "title": tasting.title or "Tasting",
        "supplier": supplier,
        "status": invite.status,
        "agenda_note": invite.agenda_note or "",
        "agenda_facts": invite.agenda_facts or {"source": "gaps", "gaps": [], "samples": []},
        "slots": [
            {
                "position": slot.position,
                "starts_at": format_wall(slot.starts_at),
                "ends_at": format_wall(slot.ends_at),
                "source": slot.source,
                "chosen": bool(slot.chosen),
            }
            for slot in slots
        ],
        "attendees": [
            {"kind": row.kind, "name": row.name, "email": row.email, "user_id": None if row.user_id is None else str(row.user_id)}
            for row in _attendees(session, invite.id)
        ],
        "approval": None
        if approval is None
        else {
            "id": str(approval.id),
            "decision": approval.decision,
            "required_role": approval.required_role,
            "comment": approval.comment,
            "decided_at": None if approval.decided_at is None else format_wall(approval.decided_at),
        },
        "chosen_starts_at": "" if chosen is None else format_wall(chosen.starts_at),
        "email_subject": invite.email_subject if ready else "",
        "email_body": invite.email_body if ready else "",
        "email_mailto": invite.email_mailto if ready else "",
        "sent": False,
        "driver": invite.driver if ready else "",
        "ics_ready": ready and bool(invite.ics_text),
    }


def _suggestions(venue: Venue, starts_at: datetime) -> list[dict]:
    hour = int(venue.briefing_hour if venue.briefing_hour is not None else 15)
    hour = min(23, max(0, hour))
    base = parse_stamp(starts_at)
    slots = []
    for offset in (0, 1, 2):
        day = (base + timedelta(days=offset)).date()
        begins = datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc)
        ends = begins + timedelta(minutes=_SLOT_MINUTES)
        slots.append({"starts_at": format_wall(begins), "ends_at": format_wall(ends), "source": "service"})
    return slots


def _parse_slots(rows: list[dict]) -> list[tuple[datetime, datetime, str]]:
    if not isinstance(rows, list) or not 2 <= len(rows) <= 3:
        raise TastingError("Enter two or three times.", 422)
    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            raise TastingError("Enter two or three times.", 422)
        start = parse_stamp(str(row.get("starts_at") or ""))
        end_text = str(row.get("ends_at") or "").strip()
        end = parse_stamp(end_text) if end_text else start + timedelta(minutes=_SLOT_MINUTES)
        if end <= start:
            raise TastingError("Each slot needs an end after its start.", 422)
        source = "service" if row.get("source") == "service" else "entered"
        parsed.append((start, end, source))
    return parsed


def _agenda_facts(session: Session, venue: Venue, tasting) -> dict:
    brief = session.scalar(
        select(SourcingBrief)
        .where(SourcingBrief.venue_id == venue.id)
        .order_by(SourcingBrief.created_at.desc(), SourcingBrief.id.desc())
    )
    gaps = []
    source = "gaps"
    if brief is not None:
        items = session.scalars(
            select(WantItem).where(WantItem.brief_id == brief.id, WantItem.venue_id == venue.id).order_by(WantItem.position)
        ).all()
        if items:
            source = "want_list"
            gaps = [_gap_fact(item.category, item.style, item.price_band, item.quantity_hint, item.dishes) for item in items]
    if not gaps:
        from madira.domain.sourcing.service import _gap_rows

        source = "gaps"
        rows, _list_id = _gap_rows(session, venue)
        gaps = [_gap_fact(row["category"], row["style"], row["price_band"], row["quantity_hint"], row["dishes"]) for row in rows[:6]]
    samples = []
    for sample in session.scalars(
        select(Sample).where(Sample.venue_id == venue.id, Sample.session_id == tasting.id).order_by(Sample.created_at)
    ).all():
        product = None if sample.product_id is None else session.get(Product, sample.product_id)
        samples.append(
            {
                "sample_id": str(sample.id),
                "name": "Unmatched sample" if product is None else product.name,
            }
        )
    return {"source": source, "gaps": gaps, "samples": samples}


def _gap_fact(category: str, style: str, band: str, quantity: int, dishes) -> dict:
    names = []
    for dish in dishes or []:
        if isinstance(dish, dict):
            name = str(dish.get("name") or "").strip()
        else:
            name = str(dish or "").strip()
        if name:
            names.append({"name": name})
        if len(names) == 4:
            break
    return {
        "category": str(category or ""),
        "style": str(style or ""),
        "price_band": str(band or ""),
        "quantity_hint": int(quantity or 0),
        "dishes": names,
    }


def _attendee_rows(session: Session, venue: Venue, tasting, staff_user_ids: list[str] | None) -> list[dict]:
    rep = _rep(session, venue, tasting)
    people = [{"kind": "rep", "name": rep["name"] or rep["supplier"] or "Supplier rep", "email": rep["email"], "user_id": None}]
    wanted = _staff_ids(staff_user_ids)
    roster = {row["id"]: row for row in _staff(session, venue.id)}
    for user_id in wanted:
        row = roster.get(user_id)
        if row is None:
            raise TastingError("That person is not on this venue.", 422)
        people.append(
            {
                "kind": "staff",
                "name": row["name"],
                "email": row["email"],
                "user_id": uuid.UUID(user_id),
            }
        )
    return people


def _staff_ids(staff_user_ids: list[str] | None) -> list[str]:
    if staff_user_ids is None:
        actor = _actor()
        if actor is None:
            return []
        return [str(actor[0])]
    found = []
    for raw in staff_user_ids:
        text = str(raw or "").strip()
        if not text or text in found:
            continue
        try:
            uuid.UUID(text)
        except ValueError as exc:
            raise TastingError("That person is not on this venue.", 422) from exc
        found.append(text)
    return found


def _staff(session: Session, venue_id: uuid.UUID) -> list[dict]:
    rows = session.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.venue_id == venue_id)
        .order_by(User.name, User.id)
    ).all()
    return [
        {"id": str(user.id), "name": user.name or user.email, "email": user.email or "", "role": membership.role}
        for user, membership in rows
    ]


def _rep(session: Session, venue: Venue, tasting) -> dict:
    supplier = None if tasting.supplier_id is None else session.get(Supplier, tasting.supplier_id)
    name = ""
    email = ""
    supplier_name = ""
    if supplier is not None and supplier.venue_id == venue.id:
        supplier_name = supplier.name
        name = supplier.name
        email = (supplier.rep_email or supplier.contact_email or "").strip()
        contact = session.scalar(
            select(SupplierContact)
            .where(SupplierContact.supplier_id == supplier.id, SupplierContact.venue_id == venue.id)
            .order_by(SupplierContact.is_primary.desc(), SupplierContact.created_at)
        )
        if contact is not None and (contact.email or "").strip():
            email = contact.email.strip()
            if contact.name:
                name = contact.name
        elif contact is not None and contact.name:
            name = contact.name
    return {"supplier": supplier_name, "name": name, "email": email}


def _facts_text(facts: dict, start: datetime, end: datetime, attendees: list[TastingInviteAttendee]) -> str:
    lines = [f"Chosen time: {format_wall(start)} to {format_wall(end)}"]
    lines.append("Want list" if facts.get("source") == "want_list" else "Open gaps")
    gaps = facts.get("gaps") if isinstance(facts, dict) else []
    if not gaps:
        lines.append("- No open gaps")
    for gap in gaps or []:
        dishes = ", ".join(dish.get("name", "") for dish in gap.get("dishes") or [] if dish.get("name")) or "no linked dish"
        lines.append(
            f"- {gap.get('category', '')} / {gap.get('style', '')} / {gap.get('price_band', '')} / {int(gap.get('quantity_hint') or 0)} / {dishes}"
        )
    lines.append("Samples")
    samples = facts.get("samples") if isinstance(facts, dict) else []
    if not samples:
        lines.append("- No samples on this tasting yet")
    for sample in samples or []:
        lines.append(f"- {sample.get('name') or 'Unmatched sample'}")
    lines.append("Attendees")
    for person in attendees:
        lines.append(f"- {person.name} ({person.kind})")
    return "\n".join(lines)


def _agenda_sentence(facts: dict) -> str:
    styles = ", ".join(gap["style"] for gap in facts.get("gaps") or [] if gap.get("style")) or "the open styles"
    names = ", ".join(sample["name"] for sample in facts.get("samples") or [] if sample.get("name")) or "the samples on the table"
    prompt = (
        "Write one sentence for a tasting agenda. Use no digits, prices, or counts.\n"
        f"STYLES {styles}\n"
        f"SAMPLES {names}\n"
        'Return JSON {"agenda":"..."}'
    )
    raw = _call_agenda(prompt)
    cleaned = _without_digits(_parse_agenda(raw))
    return cleaned or "Please taste the open styles with us."


def demo_agenda(prompt: str) -> str:
    from langchain_core.messages import HumanMessage

    from madira.agents.demo.model import DemoChatModel

    message = DemoChatModel(role="invite-drafter").invoke([HumanMessage(content=prompt)])
    content = message.content
    return content if isinstance(content, str) else str(content)


def _call_agenda(prompt: str) -> str:
    try:
        if _agenda_override is not None:
            return _agenda_override(prompt)
        if demo_posture():
            return demo_agenda(prompt)
        from madira.domain.sourcing.service import live_complete

        return live_complete(prompt, kind="tasting invite")
    except DraftFailed:
        raise
    except Exception as exc:
        raise DraftFailed(f"The tasting invite could not be written ({type(exc).__name__}).", 502) from exc


def _parse_agenda(raw: str) -> str:
    text = raw or ""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return ""
    try:
        blob = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return ""
    if not isinstance(blob, dict):
        return ""
    return str(blob.get("agenda") or "")


def _without_digits(value: str) -> str:
    return " ".join(re.sub(r"\d+", "", value or "").split())[:400]


def _invite_for(session: Session, venue_id: uuid.UUID, session_id: uuid.UUID) -> TastingInvite | None:
    return session.scalar(
        select(TastingInvite).where(TastingInvite.venue_id == venue_id, TastingInvite.session_id == session_id)
    )


def _require_invite(session: Session, venue_id: uuid.UUID, session_id: uuid.UUID) -> TastingInvite:
    invite = _invite_for(session, venue_id, session_id)
    if invite is None:
        raise NotFound("tasting invite not found")
    return invite


def _slots(session: Session, invite_id: uuid.UUID) -> list[TastingInviteSlot]:
    return list(
        session.scalars(select(TastingInviteSlot).where(TastingInviteSlot.invite_id == invite_id).order_by(TastingInviteSlot.position)).all()
    )


def _attendees(session: Session, invite_id: uuid.UUID) -> list[TastingInviteAttendee]:
    return list(
        session.scalars(
            select(TastingInviteAttendee).where(TastingInviteAttendee.invite_id == invite_id).order_by(TastingInviteAttendee.position)
        ).all()
    )


def _choose(slots: list[TastingInviteSlot], slot_index: int | None) -> TastingInviteSlot:
    if slot_index is None:
        return next((slot for slot in slots if slot.chosen), slots[0])
    if slot_index < 0 or slot_index >= len(slots):
        raise TastingError("Choose a time.", 422)
    return slots[slot_index]


def _rep_email(attendees: list[TastingInviteAttendee]) -> str:
    for row in attendees:
        if row.kind == "rep" and row.email:
            return row.email
    return ""


def _comment(comment: str) -> str | None:
    text = " ".join(str(comment or "").split())
    return text or None


def _can_decide() -> bool:
    ctx = current_request()
    if ctx is None:
        return False
    return ctx.role in {OWNER, MANAGER}


def _require_decider() -> None:
    ctx = current_request()
    if ctx is None:
        return
    if ctx.role not in {OWNER, MANAGER}:
        raise TastingError("Only an Owner or a Manager can approve a tasting invite.", 403)
