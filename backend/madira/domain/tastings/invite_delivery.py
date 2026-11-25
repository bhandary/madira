"""Invite delivery. The only driver writes a calendar file and an email draft.

Nothing is sent. A later change can add a driver that sends from a connected
account; this module refuses every other driver name, and the venue column
only allows ``draft_only``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import quote

from madira.domain.errors import NotFound
from madira.domain.tastings.service import TastingError, build_ics
from madira.models import Venue

DRAFT_ONLY = "draft_only"
_CLOSING = "This invite is a draft. Madira did not send it."


@dataclass(frozen=True)
class InvitePackage:
    invite_id: uuid.UUID
    title: str
    location: str
    starts_at: datetime
    ends_at: datetime
    agenda_note: str
    facts_text: str
    attendees: list[dict]
    to_email: str


@dataclass(frozen=True)
class InviteDraft:
    ics_text: str
    subject: str
    body: str
    mailto: str
    sent: bool
    driver: str


class InviteDelivery(Protocol):
    def deliver(self, package: InvitePackage) -> InviteDraft:
        """Turn an approved package into a downloadable draft. Do not send it."""


class DraftOnlyDelivery:
    """Build the .ics and the mailto draft on this machine. No network."""

    def deliver(self, package: InvitePackage) -> InviteDraft:
        subject = f"Tasting invite: {package.title}".strip()
        if len(subject) > 200:
            subject = subject[:200]
        body = "\n\n".join(part for part in (package.agenda_note.strip(), package.facts_text.strip(), _CLOSING) if part)
        ics = build_ics(
            title=package.title,
            starts_at=package.starts_at,
            ends_at=package.ends_at,
            location=package.location,
            notes=body,
            uid=f"invite-{package.invite_id}@maison.local",
            method="REQUEST",
            attendees=package.attendees,
        )
        mailto = ""
        if package.to_email:
            mailto = f"mailto:{package.to_email}?subject={quote(subject)}&body={quote(body)}"
        return InviteDraft(
            ics_text=ics,
            subject=subject,
            body=body,
            mailto=mailto,
            sent=False,
            driver=DRAFT_ONLY,
        )


def driver_name(venue: Venue) -> str:
    name = str(getattr(venue, "invite_delivery", "") or "").strip() or DRAFT_ONLY
    if name != DRAFT_ONLY:
        raise TastingError("Invite delivery only supports draft_only.", 422)
    return name


def get_invite_delivery(venue: Venue) -> InviteDelivery:
    driver_name(venue)
    return DraftOnlyDelivery()


def set_invite_delivery(venue_id: uuid.UUID, name: str) -> str:
    """Store the venue driver. The only accepted value is ``draft_only``."""

    from madira.domain.session import session_scope
    from madira.models import Venue as VenueModel

    cleaned = (name or "").strip()
    if cleaned != DRAFT_ONLY:
        raise TastingError("Invite delivery only supports draft_only.", 422)
    with session_scope() as session:
        venue = session.get(VenueModel, venue_id)
        if venue is None:
            raise NotFound("venue not found")
        venue.invite_delivery = cleaned
        session.commit()
    return cleaned
