"""Sensors, CSV review, license expiries, and in-app reminder state.

Postgres gets row level security on each venue-scoped table, matching
``0014``. The webhook looks a sensor up by its key before a session venue
exists, so ``sensors`` also has a SELECT policy that matches
``app.sensor_key``. SQLite skips both. ``venues.jurisdiction`` is added in
place and defaults to ``US-CA``. Downgrade drops the policy, the tables, and
the column.

Revision ID: 0025_sensors_reminders
Revises: 0024_pos
Create Date: 2026-11-25

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025_sensors_reminders"
down_revision: Union[str, Sequence[str], None] = "0024_pos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    op.add_column(
        "venues",
        sa.Column("jurisdiction", sa.String(16), nullable=False, server_default=sa.text("'US-CA'")),
    )

    op.create_table(
        "sensors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("sensor_key", sa.String(80), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_last4", sa.String(8), server_default=sa.text("''"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["zone_id"], ["storage_zones.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "external_id", name="uq_sensors_venue_external"),
        sa.UniqueConstraint("sensor_key", name="uq_sensors_key"),
        sa.CheckConstraint("metric IN ('temperature_c', 'humidity_pct')", name="ck_sensors_metric"),
    )
    op.create_index("ix_sensors_venue_id", "sensors", ["venue_id"])
    op.create_index("ix_sensors_zone_id", "sensors", ["zone_id"])
    _enable_rls("sensors")
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS sensor_webhook ON sensors")
        op.execute(
            """
            CREATE POLICY sensor_webhook ON sensors
            FOR SELECT
            USING (sensor_key = NULLIF(current_setting('app.sensor_key', true), ''))
            """
        )

    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("sensor_id", sa.Uuid(), nullable=False),
        sa.Column("condition_reading_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("value", sa.Numeric(8, 2), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["sensor_id"], ["sensors.id"]),
        sa.ForeignKeyConstraint(["condition_reading_id"], ["condition_readings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sensor_id", "recorded_at", name="uq_sensor_readings_sensor_at"),
        sa.CheckConstraint("metric IN ('temperature_c', 'humidity_pct')", name="ck_sensor_readings_metric"),
    )
    op.create_index("ix_sensor_readings_venue_id", "sensor_readings", ["venue_id"])
    op.create_index("ix_sensor_readings_sensor_id", "sensor_readings", ["sensor_id"])
    op.create_index("ix_sensor_readings_condition_reading_id", "sensor_readings", ["condition_reading_id"])
    _enable_rls("sensor_readings")

    op.create_table(
        "sensor_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(200), server_default=sa.text("''"), nullable=False),
        sa.Column("status", sa.String(32), server_default=sa.text("'pending_review'"), nullable=False),
        sa.Column("rows_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending_review', 'applied', 'rejected')",
            name="ck_sensor_imports_status",
        ),
    )
    op.create_index("ix_sensor_imports_venue_id", "sensor_imports", ["venue_id"])
    _enable_rls("sensor_imports")

    op.create_table(
        "venue_licenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venue_licenses_venue_id", "venue_licenses", ["venue_id"])
    op.create_index("ix_venue_licenses_document_id", "venue_licenses", ["document_id"])
    _enable_rls("venue_licenses")

    op.create_table(
        "reminder_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("jurisdiction", sa.String(16), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False),
        sa.Column("applies_to", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "code", name="uq_reminder_rules_venue_code"),
        sa.CheckConstraint("lead_days >= 1 AND lead_days <= 365", name="ck_reminder_rules_lead"),
        sa.CheckConstraint("applies_to IN ('license', 'certificate')", name="ck_reminder_rules_applies"),
    )
    op.create_index("ix_reminder_rules_venue_id", "reminder_rules", ["venue_id"])
    _enable_rls("reminder_rules")

    op.create_table(
        "reminder_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("snooze_until", sa.Date(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "source_type", "source_id", name="uq_reminder_states_source"),
        sa.CheckConstraint("source_type IN ('license', 'certificate')", name="ck_reminder_states_source"),
        sa.CheckConstraint("status IN ('acknowledged', 'snoozed')", name="ck_reminder_states_status"),
    )
    op.create_index("ix_reminder_states_venue_id", "reminder_states", ["venue_id"])
    op.create_index("ix_reminder_states_source_id", "reminder_states", ["source_id"])
    _enable_rls("reminder_states")


def downgrade() -> None:
    _disable_rls("reminder_states")
    op.drop_index("ix_reminder_states_source_id", table_name="reminder_states")
    op.drop_index("ix_reminder_states_venue_id", table_name="reminder_states")
    op.drop_table("reminder_states")

    _disable_rls("reminder_rules")
    op.drop_index("ix_reminder_rules_venue_id", table_name="reminder_rules")
    op.drop_table("reminder_rules")

    _disable_rls("venue_licenses")
    op.drop_index("ix_venue_licenses_document_id", table_name="venue_licenses")
    op.drop_index("ix_venue_licenses_venue_id", table_name="venue_licenses")
    op.drop_table("venue_licenses")

    _disable_rls("sensor_imports")
    op.drop_index("ix_sensor_imports_venue_id", table_name="sensor_imports")
    op.drop_table("sensor_imports")

    _disable_rls("sensor_readings")
    op.drop_index("ix_sensor_readings_condition_reading_id", table_name="sensor_readings")
    op.drop_index("ix_sensor_readings_sensor_id", table_name="sensor_readings")
    op.drop_index("ix_sensor_readings_venue_id", table_name="sensor_readings")
    op.drop_table("sensor_readings")

    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS sensor_webhook ON sensors")
    _disable_rls("sensors")
    op.drop_index("ix_sensors_zone_id", table_name="sensors")
    op.drop_index("ix_sensors_venue_id", table_name="sensors")
    op.drop_table("sensors")

    op.drop_column("venues", "jurisdiction")
