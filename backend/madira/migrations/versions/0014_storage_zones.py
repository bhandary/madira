"""Storage zones, condition readings, and excursion alerts.

A zone names the temperature and humidity a cellar or cold box should hold.
A reading outside that band opens an excursion for the bottles in the zone's
bins. Postgres gets row level security on the three new venue-scoped tables,
matching ``0009`` through ``0013``. SQLite skips those statements.

Revision ID: 0014_storage_zones
Revises: 0013_receiving_invoices
Create Date: 2026-11-24

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_storage_zones"
down_revision: Union[str, Sequence[str], None] = "0013_receiving_invoices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_METRICS = "('temp_high', 'temp_low', 'humidity_high', 'humidity_low', 'temp_and_humidity')"
_STATUS = "('open', 'acknowledged')"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table: str) -> None:
    if not _is_postgres():
        return
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS venue_isolation ON {table}")
    op.execute(
        f"""
        CREATE POLICY venue_isolation ON {table}
        USING (venue_id = NULLIF(current_setting('app.venue_id', true), '')::uuid)
        WITH CHECK (venue_id = NULLIF(current_setting('app.venue_id', true), '')::uuid)
        """
    )


def _disable_rls(table: str) -> None:
    if not _is_postgres():
        return
    op.execute(f"DROP POLICY IF EXISTS venue_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "storage_zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("target_temp_min_c", sa.Numeric(5, 2), nullable=False),
        sa.Column("target_temp_max_c", sa.Numeric(5, 2), nullable=False),
        sa.Column("target_humidity_min_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("target_humidity_max_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_storage_zones_venue_id"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], name="fk_storage_zones_location_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "name", name="uq_storage_zones_venue_name"),
    )
    op.create_index("ix_storage_zones_venue_id", "storage_zones", ["venue_id"])
    op.create_index("ix_storage_zones_location_id", "storage_zones", ["location_id"])

    op.create_table(
        "condition_readings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column("temp_c", sa.Numeric(5, 2), nullable=False),
        sa.Column("humidity_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_condition_readings_venue_id"),
        sa.ForeignKeyConstraint(["zone_id"], ["storage_zones.id"], name="fk_condition_readings_zone_id"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], name="fk_condition_readings_recorded_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_condition_readings_venue_id", "condition_readings", ["venue_id"])
    op.create_index("ix_condition_readings_zone_id", "condition_readings", ["zone_id"])
    op.create_index("ix_condition_readings_recorded_at", "condition_readings", ["recorded_at"])

    op.create_table(
        "condition_excursions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column("reading_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("measured_temp_c", sa.Numeric(5, 2), nullable=False),
        sa.Column("measured_humidity_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("affected_skus", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'open'")),
        sa.Column("acknowledged_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"metric IN {_METRICS}", name="ck_condition_excursions_metric"),
        sa.CheckConstraint(f"status IN {_STATUS}", name="ck_condition_excursions_status"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_condition_excursions_venue_id"),
        sa.ForeignKeyConstraint(["zone_id"], ["storage_zones.id"], name="fk_condition_excursions_zone_id"),
        sa.ForeignKeyConstraint(["reading_id"], ["condition_readings.id"], name="fk_condition_excursions_reading_id"),
        sa.ForeignKeyConstraint(
            ["acknowledged_by_user_id"],
            ["users.id"],
            name="fk_condition_excursions_acknowledged_by_user_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_condition_excursions_venue_id", "condition_excursions", ["venue_id"])
    op.create_index("ix_condition_excursions_zone_id", "condition_excursions", ["zone_id"])
    op.create_index("ix_condition_excursions_reading_id", "condition_excursions", ["reading_id"])

    _enable_rls("storage_zones")
    _enable_rls("condition_readings")
    _enable_rls("condition_excursions")


def downgrade() -> None:
    _disable_rls("condition_excursions")
    _disable_rls("condition_readings")
    _disable_rls("storage_zones")

    op.drop_index("ix_condition_excursions_reading_id", table_name="condition_excursions")
    op.drop_index("ix_condition_excursions_zone_id", table_name="condition_excursions")
    op.drop_index("ix_condition_excursions_venue_id", table_name="condition_excursions")
    op.drop_table("condition_excursions")

    op.drop_index("ix_condition_readings_recorded_at", table_name="condition_readings")
    op.drop_index("ix_condition_readings_zone_id", table_name="condition_readings")
    op.drop_index("ix_condition_readings_venue_id", table_name="condition_readings")
    op.drop_table("condition_readings")

    op.drop_index("ix_storage_zones_location_id", table_name="storage_zones")
    op.drop_index("ix_storage_zones_venue_id", table_name="storage_zones")
    op.drop_table("storage_zones")
