"""Reminders for recorded license expiries and the existing certificate window.

Certificate membership comes from ``due_certificates``. License membership uses
the seeded rule's lead time. Acknowledgement and snooze stay in the app.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.compliance.service import DEMO_LICENSE_FILENAME, record_audit_event
from madira.domain.errors import NotFound
from madira.domain.session import session_scope
from madira.domain.team.certificates import REMINDER_DAYS, due_certificates, venue_today
from madira.models import Document, ReminderRule, ReminderState, Venue, VenueLicense
from madira.tenancy import current_request

LICENSE_LEAD_DAYS = 60
JURISDICTION = "US-CA"

_CA_RULES = (
    {
        "code": "abc_license",
        "title": "ABC license renewal",
        "detail": "The recorded license expiry is inside the reminder window.",
        "lead_days": LICENSE_LEAD_DAYS,
        "applies_to": "license",
    },
    {
        "code": "certificate_expiry",
        "title": "Staff certificate",
        "detail": "A staff certificate is inside its reminder window.",
        "lead_days": REMINDER_DAYS,
        "applies_to": "certificate",
    },
)


class ReminderError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _actor(venue_id: uuid.UUID) -> tuple[uuid.UUID | None, str]:
    ctx = current_request()
    if ctx is None or ctx.venue_id != venue_id:
        return None, ""
    return ctx.user_id, ctx.email or ""


def ensure_rules(session: Session, venue: Venue) -> list[ReminderRule]:
    if (venue.jurisdiction or "") != JURISDICTION:
        return list(
            session.scalars(select(ReminderRule).where(ReminderRule.venue_id == venue.id).order_by(ReminderRule.code)).all()
        )
    existing = {
        row.code: row
        for row in session.scalars(select(ReminderRule).where(ReminderRule.venue_id == venue.id)).all()
    }
    for spec in _CA_RULES:
        if spec["code"] in existing:
            continue
        row = ReminderRule(
            venue_id=venue.id,
            jurisdiction=JURISDICTION,
            code=spec["code"],
            title=spec["title"],
            detail=spec["detail"],
            lead_days=int(spec["lead_days"]),
            applies_to=spec["applies_to"],
        )
        session.add(row)
        existing[spec["code"]] = row
    session.flush()
    return [existing[spec["code"]] for spec in _CA_RULES if spec["code"] in existing]


def _rule_public(row: ReminderRule) -> dict:
    return {
        "code": row.code,
        "title": row.title,
        "detail": row.detail,
        "lead_days": int(row.lead_days),
        "applies_to": row.applies_to,
        "jurisdiction": row.jurisdiction,
    }


def _states(session: Session, venue_id: uuid.UUID) -> dict[tuple[str, str], ReminderState]:
    rows = session.scalars(select(ReminderState).where(ReminderState.venue_id == venue_id)).all()
    return {(row.source_type, str(row.source_id)): row for row in rows}


def _hidden(state: ReminderState | None, today: date) -> bool:
    if state is None:
        return False
    if state.status == "acknowledged":
        return True
    if state.status == "snoozed" and state.snooze_until is not None and state.snooze_until >= today:
        return True
    return False


def open_reminders(session: Session, venue_id: uuid.UUID) -> list[dict]:
    venue = _venue(session, venue_id)
    rules = {row.code: row for row in ensure_rules(session, venue)}
    today = venue_today(session, venue_id)
    states = _states(session, venue_id)
    found: list[dict] = []
    license_rule = rules.get("abc_license")
    if license_rule is not None and license_rule.applies_to == "license":
        horizon = today + timedelta(days=int(license_rule.lead_days))
        licenses = session.scalars(
            select(VenueLicense)
            .where(
                VenueLicense.venue_id == venue_id,
                VenueLicense.rule_code == license_rule.code,
                VenueLicense.expires_on <= horizon,
            )
            .order_by(VenueLicense.expires_on.asc(), VenueLicense.id.asc())
        ).all()
        for row in licenses:
            if _hidden(states.get(("license", str(row.id))), today):
                continue
            days_left = (row.expires_on - today).days
            found.append(
                {
                    "source_type": "license",
                    "source_id": str(row.id),
                    "rule_code": license_rule.code,
                    "title": license_rule.title,
                    "detail": f"{license_rule.detail} Recorded expiry {row.expires_on.isoformat()}.",
                    "due_on": row.expires_on.isoformat(),
                    "days_left": days_left,
                    "label": row.label,
                    "channel": "in_app",
                }
            )
    certificate_rule = rules.get("certificate_expiry")
    if certificate_rule is not None:
        for gap in due_certificates(session, venue_id):
            if _hidden(states.get(("certificate", gap["id"])), today):
                continue
            found.append(
                {
                    "source_type": "certificate",
                    "source_id": gap["id"],
                    "rule_code": certificate_rule.code,
                    "title": certificate_rule.title,
                    "detail": f"{certificate_rule.detail} {gap['status_label']}.",
                    "due_on": gap["expires_on"],
                    "days_left": gap["days_left"],
                    "label": gap["label"],
                    "channel": "in_app",
                }
            )
    return found


def list_reminders(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        rules = ensure_rules(session, venue)
        body = {
            "jurisdiction": venue.jurisdiction or "",
            "rules": [_rule_public(row) for row in rules],
            "reminders": open_reminders(session, venue_id),
            "channel": "in_app",
        }
        session.commit()
        return body


def record_license(
    venue_id: uuid.UUID,
    *,
    label: str,
    expires_on: date,
    rule_code: str = "abc_license",
    document_id: uuid.UUID | None = None,
) -> dict:
    cleaned = " ".join((label or "").split())
    if not cleaned or len(cleaned) > 200:
        raise ReminderError("A license label is required.")
    if not isinstance(expires_on, date):
        raise ReminderError("An expiry date is required.")
    code = (rule_code or "").strip()
    with session_scope() as session:
        venue = _venue(session, venue_id)
        rules = {row.code: row for row in ensure_rules(session, venue)}
        rule = rules.get(code)
        if rule is None or rule.applies_to != "license":
            raise ReminderError("That reminder rule is not available for this venue.")
        if document_id is not None:
            document = session.get(Document, document_id)
            if document is None or document.venue_id != venue_id or document.doc_type != "license":
                raise NotFound("license document not found")
        row = VenueLicense(
            venue_id=venue_id,
            document_id=document_id,
            rule_code=rule.code,
            label=cleaned,
            expires_on=expires_on,
        )
        session.add(row)
        session.flush()
        user_id, email = _actor(venue_id)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="license.recorded",
            entity_type="venue_license",
            entity_id=row.id,
            after={"label": row.label, "expires_on": row.expires_on.isoformat(), "rule_code": row.rule_code},
            actor_user_id=user_id,
            actor_email=email,
        )
        session.commit()
        return {
            "id": str(row.id),
            "label": row.label,
            "expires_on": row.expires_on.isoformat(),
            "rule_code": row.rule_code,
            "document_id": None if row.document_id is None else str(row.document_id),
        }


def decide(venue_id: uuid.UUID, source_type: str, source_id: uuid.UUID, action: str, snooze_days: int = 7) -> dict:
    kind = (source_type or "").strip()
    if kind not in {"license", "certificate"}:
        raise ReminderError("Reminder source must be license or certificate.")
    choice = (action or "").strip()
    if choice not in {"acknowledge", "snooze"}:
        raise ReminderError("Action must be acknowledge or snooze.")
    if choice == "snooze" and (isinstance(snooze_days, bool) or not isinstance(snooze_days, int) or snooze_days < 1 or snooze_days > 30):
        raise ReminderError("Snooze must be a whole number of days from 1 to 30.")
    with session_scope() as session:
        venue = _venue(session, venue_id)
        today = venue_today(session, venue_id)
        open_ids = {
            (row["source_type"], row["source_id"])
            for row in open_reminders(session, venue_id)
        }
        key = (kind, str(source_id))
        if key not in open_ids:
            raise NotFound("reminder not found")
        state = session.scalar(
            select(ReminderState).where(
                ReminderState.venue_id == venue_id,
                ReminderState.source_type == kind,
                ReminderState.source_id == source_id,
            )
        )
        user_id, email = _actor(venue_id)
        previous = None if state is None else state.status
        if state is None:
            state = ReminderState(
                venue_id=venue_id,
                source_type=kind,
                source_id=source_id,
                status="acknowledged",
                actor_user_id=user_id,
            )
            session.add(state)
        if choice == "acknowledge":
            state.status = "acknowledged"
            state.snooze_until = None
            audit_action = "reminder.acknowledged"
        else:
            state.status = "snoozed"
            state.snooze_until = today + timedelta(days=snooze_days)
            audit_action = "reminder.snoozed"
        state.actor_user_id = user_id
        session.flush()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=audit_action,
            entity_type="reminder_state",
            entity_id=state.id,
            before=None if previous is None else {"status": previous},
            after={
                "source_type": kind,
                "source_id": str(source_id),
                "status": state.status,
                "snooze_until": None if state.snooze_until is None else state.snooze_until.isoformat(),
                "channel": "in_app",
            },
            actor_user_id=user_id,
            actor_email=email,
        )
        session.commit()
        return {
            "source_type": kind,
            "source_id": str(source_id),
            "status": state.status,
            "snooze_until": None if state.snooze_until is None else state.snooze_until.isoformat(),
            "channel": "in_app",
        }


def ensure_demo_license(session: Session, ctx) -> None:
    """One ABC reminder inside the 60-day window, tied to the demo license file."""

    venue = session.get(Venue, ctx.venue_id)
    if venue is None or (venue.jurisdiction or "") != JURISDICTION:
        return
    ensure_rules(session, venue)
    existing = session.scalar(
        select(VenueLicense.id).where(VenueLicense.venue_id == venue.id, VenueLicense.rule_code == "abc_license").limit(1)
    )
    if existing is not None:
        return
    document = session.scalar(
        select(Document).where(
            Document.venue_id == venue.id,
            Document.filename == DEMO_LICENSE_FILENAME,
            Document.doc_type == "license",
        )
    )
    today = venue_today(session, venue.id)
    session.add(
        VenueLicense(
            venue_id=venue.id,
            document_id=None if document is None else document.id,
            rule_code="abc_license",
            label="ABC license",
            expires_on=today + timedelta(days=45),
        )
    )
    session.flush()
