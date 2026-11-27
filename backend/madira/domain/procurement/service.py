"""Suppliers for the current venue."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from madira.domain.session import session_scope
from madira.models import Supplier


def list_suppliers(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        rows = session.scalars(select(Supplier).where(Supplier.venue_id == venue_id)).all()
        return {
            "suppliers": [
                {"id": row.id, "name": row.name, "kind": row.kind, "contact_email": row.contact_email, "notes": row.notes}
                for row in rows
            ]
        }
