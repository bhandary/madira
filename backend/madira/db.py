from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from madira.config import DATABASE_URL

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


class Base(DeclarativeBase):
    pass


connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(SessionLocal, "after_begin")
def _postgres_venue_setting(session, transaction, connection):
    """Apply SET LOCAL app.venue_id for Postgres row-level security.

    ``set_config(..., true)`` is local to the transaction. SQLite ignores it.
    The login role still has to be subject to RLS (a non-superuser, or a table
    owner with FORCE). Superusers bypass the policies.
    """

    if connection.dialect.name != "postgresql":
        return
    from madira.tenancy import current_request

    ctx = current_request()
    if ctx is None:
        return
    connection.execute(
        text("SELECT set_config('app.venue_id', :venue_id, true)"),
        {"venue_id": str(ctx.venue_id)},
    )
    connection.execute(
        text("SELECT set_config('app.organization_id', :organization_id, true)"),
        {"organization_id": str(ctx.organization_id)},
    )


def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    # Startup and tests keep their own logging. The Alembic CLI does not set this.
    cfg.attributes["configure_logging"] = False
    return cfg


def _schema_at_head() -> bool:
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    with engine.connect() as connection:
        if not inspect(connection).has_table("alembic_version"):
            return False
        current = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return current == head


def init_db() -> None:
    """Apply Alembic migrations through head."""
    if _schema_at_head():
        return
    from alembic import command

    try:
        command.upgrade(_alembic_config(), "head")
    except (OperationalError, ProgrammingError) as exc:
        if "already exists" in str(exc).lower():
            raise RuntimeError(
                "The database already has tables but no Alembic revision. "
                "This baseline starts from an empty database. "
                "For the default SQLite file, run `make clean` and start again."
            ) from exc
        raise
