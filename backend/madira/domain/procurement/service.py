"""Suppliers and draft tastings. The .ics text is built here and nothing is sent."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from madira.domain.errors import NotFound
from madira.domain.session import session_scope
from madira.models import Supplier, Tasting
from madira.timestamps import format_wall, parse_stamp


def build_ics(title: str, starts_at: str, ends_at: str, location: str, notes: str) -> str:
    def _compact(ts: str) -> str:
        return ts.replace("-", "").replace(":", "").replace(" ", "T")[:15]

    uid = f"{_compact(starts_at)}-madira@maison.local"
    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Maison Madira//Madira//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTART:{_compact(starts_at)}",
            f"DTEND:{_compact(ends_at)}",
            f"SUMMARY:{title}",
            f"LOCATION:{location}",
            f"DESCRIPTION:{notes} (draft only — not sent)",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )


def list_suppliers(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        rows = session.scalars(select(Supplier).where(Supplier.venue_id == venue_id)).all()
        return {
            "suppliers": [
                {"id": row.id, "name": row.name, "kind": row.kind, "contact_email": row.contact_email, "notes": row.notes}
                for row in rows
            ]
        }


def list_tastings(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        rows = session.scalars(select(Tasting).where(Tasting.venue_id == venue_id).order_by(Tasting.starts_at)).all()
        return {"tastings": [_tasting_row(row, include_ics=True) for row in rows]}


def ics_text(venue_id: uuid.UUID, tasting_id: uuid.UUID) -> str:
    with session_scope() as session:
        tasting = session.get(Tasting, tasting_id)
        if tasting is None or tasting.venue_id != venue_id:
            raise NotFound("tasting not found")
        return tasting.ics


def schedule(
    venue_id: uuid.UUID,
    supplier_name: str = "Kermit Lynch Wine Merchant",
    title: str = "New Loire releases tasting",
    starts_at: str = "",
    ends_at: str = "",
    location: str = "Maison Madira cellar",
    notes: str = "Draft hold — export .ics, do not send invites.",
) -> dict:
    with session_scope() as session:
        supplier = session.scalar(select(Supplier).where(Supplier.venue_id == venue_id, Supplier.name == supplier_name))
        if supplier is None:
            supplier = session.scalar(select(Supplier).where(Supplier.venue_id == venue_id).limit(1))
        if supplier is None:
            return {"error": "no supplier"}
        if not starts_at:
            start = datetime.now().replace(hour=15, minute=0, second=0, microsecond=0) + timedelta(days=7)
            starts_at = start.strftime("%Y-%m-%dT%H:%M")
            ends_at = (start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        if not ends_at:
            ends_at = starts_at
        ics = build_ics(title, starts_at, ends_at, location, notes)
        start_at = parse_stamp(starts_at)
        end_at = parse_stamp(ends_at)
        tasting = session.scalar(
            select(Tasting).where(
                Tasting.venue_id == venue_id,
                Tasting.title == title,
                Tasting.supplier_id == supplier.id,
            )
        )
        if tasting is None:
            tasting = Tasting(
                venue_id=venue_id,
                supplier_id=supplier.id,
                title=title,
                starts_at=start_at,
                ends_at=end_at,
                location=location,
                notes=notes,
                ics=ics,
            )
            session.add(tasting)
        else:
            tasting.starts_at = start_at
            tasting.ends_at = end_at
            tasting.location = location
            tasting.notes = notes
            tasting.ics = ics
        session.flush()
        draft = {
            "id": tasting.id,
            "title": title,
            "supplier": supplier.name,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "location": location,
            "notes": notes,
            "ics": ics,
            "sent": False,
        }
        session.commit()
        rows = session.scalars(select(Tasting).where(Tasting.venue_id == venue_id).order_by(Tasting.starts_at)).all()
        tastings = [_tasting_row(row, include_ics=False) for row in rows]
        return {"draft": draft, "tastings": tastings}


def _tasting_row(tasting: Tasting, *, include_ics: bool) -> dict:
    row = {
        "id": tasting.id,
        "title": tasting.title,
        "starts_at": format_wall(tasting.starts_at),
        "ends_at": format_wall(tasting.ends_at),
        "location": tasting.location,
        "notes": tasting.notes,
        "supplier": tasting.supplier.name if tasting.supplier else "",
    }
    if include_ics:
        row["ics"] = tasting.ics
    return row
