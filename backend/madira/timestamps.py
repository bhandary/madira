"""Timezone-aware timestamps.

Postgres stores these as ``timestamptz``. SQLite has no such type; values are
written as UTC and read back with ``tzinfo`` attached so both backends round-trip
the same instant. Wall-clock strings such as ``2026-12-01T15:00`` keep their
digits: they are labeled UTC, not shifted.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def parse_stamp(value: datetime | str) -> datetime:
    """Parse a stored timestamp into an aware UTC datetime."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_wall(value: datetime) -> str:
    """``YYYY-MM-DDTHH:MM`` in UTC, the shape ``build_ics`` has always compacted."""

    clock = value.astimezone(timezone.utc) if value.tzinfo is not None else value
    return clock.strftime("%Y-%m-%dT%H:%M")


class AwareDateTime(TypeDecorator):
    """``timestamptz`` on Postgres. Aware UTC datetimes on every backend."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            return parse_stamp(value)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            return parse_stamp(value)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
