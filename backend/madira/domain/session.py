"""Short-lived sessions for domain services."""

from __future__ import annotations

from contextlib import contextmanager

from madira.db import SessionLocal


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
