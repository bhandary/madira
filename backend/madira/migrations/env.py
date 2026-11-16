"""Alembic environment for the Madira schema.

The database URL is the same one the app uses (`DATABASE_URL`, or the SQLite
file when that variable is unset). Models are imported so autogenerate and
`alembic check` compare against `Base.metadata`.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, event, pool

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from madira.config import DATABASE_URL  # noqa: E402
from madira.db import Base  # noqa: E402
import madira.models  # noqa: E402,F401

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _configure_context(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=DATABASE_URL.startswith("sqlite"),
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure_context(url=DATABASE_URL, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _connect():
    connect_args: dict = {}
    if DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(DATABASE_URL, poolclass=pool.NullPool, connect_args=connect_args)
    if DATABASE_URL.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def run_migrations_online() -> None:
    connectable = _connect()
    with connectable.connect() as connection:
        _configure_context(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
