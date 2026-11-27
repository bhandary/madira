"""Venue service standards. Madira ships the defaults; an edit is the venue's text."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.auth import utcnow
from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.session import session_scope
from madira.domain.training.access import actor, require_author, require_learn
from madira.models import Standard, Venue

# Concise house service. Lessons quote these ids, then the venue's edited body.
DEFAULT_STANDARDS: tuple[dict[str, str], ...] = (
    {
        "slug": "opening-still",
        "topic": "opening still",
        "title": "Opening a still bottle",
        "body": (
            "Present the bottle to the host with the label facing them. State the producer, the place, and the vintage. "
            "Cut the capsule below the lip, wipe the lip, and draw the cork in one quiet pull. Wipe again. "
            "Pour a one-ounce taste for the host and wait."
        ),
    },
    {
        "slug": "opening-sparkling",
        "topic": "opening sparkling",
        "title": "Opening sparkling wine",
        "body": (
            "Keep the bottle at a 45-degree angle, pointed away from guests. Remove the foil and loosen the cage "
            "while a thumb stays on the cork. Turn the bottle, not the cork. Ease the cork out with a sigh, not a pop. "
            "Have a glass ready before the cork leaves the bottle."
        ),
    },
    {
        "slug": "presenting-pouring-order",
        "topic": "presenting and pouring order",
        "title": "Presenting and pouring order",
        "body": (
            "The host tastes first. Then pour the other guests, and the host last. When you know the table, "
            "older guests come before younger ones. Never wrap the bottle in a cloth that hides the label. "
            "Keep the label readable as you pour."
        ),
    },
    {
        "slug": "pour-sizes",
        "topic": "pour sizes",
        "title": "Pour sizes",
        "body": (
            "Still wine is about five ounces, no more than one-third of the glass. Sparkling fills a flute about "
            "three-quarters. A spirit pour on a pairing ticket is 25 to 60 millilitres, never a full cocktail. "
            "Sake follows the service card. Stop when a guest covers the glass."
        ),
    },
    {
        "slug": "decanting",
        "topic": "decanting",
        "title": "Decanting",
        "body": (
            "Decant young tannic reds and any bottle with sediment. Stand a sediment bottle upright for an hour, "
            "then pour slowly with a light behind the neck and stop before the sediment reaches the lip. "
            "Tell the guest how long the bottle has been open. Do not decant sparkling, or a fragile old wine, "
            "unless the service card says to."
        ),
    },
    {
        "slug": "glassware",
        "topic": "glassware",
        "title": "Glassware",
        "body": (
            "Use the glass on the service card. A larger bowl for reds that need air, a smaller bowl for aromatic "
            "whites and sparkling, a copita or similar for spirits, and the card's vessel for sake. "
            "Rinse a glass that held an oaky wine before sake or beer. Hold the stem, not the bowl."
        ),
    },
    {
        "slug": "serving-temperatures",
        "topic": "serving temperatures",
        "title": "Serving temperatures",
        "body": (
            "Serve at the temperature on the service card. Sparkling and sweet whites are colder than dry whites. "
            "Light reds are cooler than structured reds. Beer and sake follow their own cards. "
            "A warm glass undoes a cold bottle, so chill the glass when the card calls for it."
        ),
    },
    {
        "slug": "faulty-bottle",
        "topic": "faulty bottle",
        "title": "A faulty bottle",
        "body": (
            "If a guest says the wine is corked, cooked, or refermenting, take it away without debate. "
            "Do not taste it at the table to prove them wrong. Replace the bottle, or offer another pour from the list. "
            "Taste the returned bottle in the back and tell the sommelier what you found."
        ),
    },
    {
        "slug": "responsible-service",
        "topic": "responsible service",
        "title": "Responsible service",
        "body": (
            "Do not serve a guest who is drunk. Slow the pace, offer water and food, and refuse another round when you have to. "
            "Ask a manager before you cut someone off if you are unsure. Do not joke about it. "
            "A spirit on a pairing ticket stays at the measure the ticket names."
        ),
    },
)

_BY_SLUG = {row["slug"]: row for row in DEFAULT_STANDARDS}


def ensure_default_standards(session: Session, venue_id: uuid.UUID) -> None:
    """Insert any missing house standard. An edited row is left alone."""

    have = set(
        session.scalars(select(Standard.slug).where(Standard.venue_id == venue_id)).all()
    )
    now = utcnow()
    for row in DEFAULT_STANDARDS:
        if row["slug"] in have:
            continue
        session.add(
            Standard(
                venue_id=venue_id,
                slug=row["slug"],
                topic=row["topic"],
                title=row["title"],
                body=row["body"],
                version=1,
                is_default=True,
                updated_at=now,
            )
        )
    session.flush()


def _public(row: Standard) -> dict:
    return {
        "id": row.id,
        "slug": row.slug,
        "topic": row.topic,
        "title": row.title,
        "body": row.body,
        "version": row.version,
        "is_default": row.is_default,
        "updated_at": row.updated_at,
    }


def _ordered(session: Session, venue_id: uuid.UUID) -> list[Standard]:
    rows = session.scalars(select(Standard).where(Standard.venue_id == venue_id)).all()
    order = {row["slug"]: index for index, row in enumerate(DEFAULT_STANDARDS)}
    return sorted(rows, key=lambda row: (order.get(row.slug, 100), row.slug))


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _one(session: Session, venue_id: uuid.UUID, slug: str) -> Standard:
    row = session.scalar(select(Standard).where(Standard.venue_id == venue_id, Standard.slug == slug))
    if row is None:
        raise NotFound("standard not found")
    return row


def _clean(value: str, limit: int, label: str) -> str:
    text = (value or "").strip()
    if not text:
        raise DraftFailed(f"{label} is required.", 422)
    if len(text) > limit:
        raise DraftFailed(f"{label} is too long.", 422)
    return text


def list_standards(venue_id: uuid.UUID) -> dict:
    ctx = actor()
    require_learn(ctx)
    with session_scope() as session:
        ensure_default_standards(session, venue_id)
        payload = {
            "can_author": ctx.role in {"Owner", "Sommelier"},
            "standards": [_public(row) for row in _ordered(session, venue_id)],
        }
        session.commit()
        return payload


def update_standard(venue_id: uuid.UUID, slug: str, *, title: str, body: str, topic: str | None = None) -> dict:
    ctx = actor()
    require_author(ctx)
    title = _clean(title, 200, "Title")
    body = _clean(body, 8000, "Body")
    topic_text = _clean(topic, 80, "Topic") if topic is not None and topic.strip() else None
    with session_scope() as session:
        ensure_default_standards(session, venue_id)
        row = _one(session, venue_id, slug)
        before = _public(row)
        changed = row.title != title or row.body != body or (topic_text is not None and row.topic != topic_text)
        if changed:
            if topic_text is not None:
                row.topic = topic_text
            row.title = title
            row.body = body
            row.version = int(row.version) + 1
            row.is_default = False
            row.updated_by_user_id = ctx.user_id
            row.updated_at = utcnow()
            venue = _venue(session, venue_id)
            record_audit_event(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                action="training.standard.edit",
                entity_type="standard",
                entity_id=row.id,
                before=before,
                after=_public(row),
            )
        payload = _public(row)
        session.commit()
        return payload


def reset_standard(venue_id: uuid.UUID, slug: str) -> dict:
    ctx = actor()
    require_author(ctx)
    default = _BY_SLUG.get(slug)
    if default is None:
        raise NotFound("standard not found")
    with session_scope() as session:
        ensure_default_standards(session, venue_id)
        row = _one(session, venue_id, slug)
        before = _public(row)
        same = (
            row.topic == default["topic"]
            and row.title == default["title"]
            and row.body == default["body"]
            and row.is_default
        )
        if not same:
            row.topic = default["topic"]
            row.title = default["title"]
            row.body = default["body"]
            row.version = int(row.version) + 1
            row.is_default = True
            row.updated_by_user_id = ctx.user_id
            row.updated_at = utcnow()
            venue = _venue(session, venue_id)
            record_audit_event(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                action="training.standard.reset",
                entity_type="standard",
                entity_id=row.id,
                before=before,
                after=_public(row),
            )
        payload = _public(row)
        session.commit()
        return payload
