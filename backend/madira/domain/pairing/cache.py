"""Venue-scoped cache of a deterministic pairing assignment.

A database row is shared by every app process and survives a restart. The
cost is one read on a repeat and one write on a miss. An in-process LRU would
be cheaper inside one process and would forget the assignment on restart, and
a second process would score the same dish again.

The lookup always filters on ``venue_id``. Another venue's row is not a hit.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.models import PairingCache


def digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def read_result(session: Session, venue_id: uuid.UUID, dish_id: uuid.UUID, cache_key: str) -> list | None:
    row = session.scalar(
        select(PairingCache).where(
            PairingCache.venue_id == venue_id,
            PairingCache.dish_id == dish_id,
            PairingCache.cache_key == cache_key,
        )
    )
    if row is None or not isinstance(row.result, list):
        return None
    return row.result


def write_result(
    session: Session,
    *,
    venue_id: uuid.UUID,
    dish_id: uuid.UUID,
    menu_version_id: uuid.UUID,
    list_version_id: uuid.UUID | None,
    cache_key: str,
    result: list,
) -> None:
    row = session.scalar(
        select(PairingCache).where(
            PairingCache.venue_id == venue_id,
            PairingCache.dish_id == dish_id,
        )
    )
    if row is None:
        session.add(
            PairingCache(
                venue_id=venue_id,
                dish_id=dish_id,
                menu_version_id=menu_version_id,
                list_version_id=list_version_id,
                cache_key=cache_key,
                result=result,
            )
        )
        return
    row.menu_version_id = menu_version_id
    row.list_version_id = list_version_id
    row.cache_key = cache_key
    row.result = result
