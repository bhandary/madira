"""Decide whether this database can store a pgvector column.

SQLite never can. Postgres can when ``CREATE EXTENSION vector`` succeeds.
A managed server that does not ship the extension raises, and the migration
keeps going with the JSON column alone.
"""

from __future__ import annotations

from sqlalchemy import text


def vector_extension_available(connection) -> bool:
    if getattr(getattr(connection, "dialect", None), "name", "") != "postgresql":
        return False
    try:
        nested = connection.begin_nested()
    except Exception:
        return False
    try:
        with nested:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            found = connection.execute(text("SELECT 1 FROM pg_type WHERE typname = 'vector'")).scalar()
        return bool(found)
    except Exception:
        return False
