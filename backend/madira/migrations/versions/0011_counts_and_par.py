"""Count sessions, offline count lines, conflict resolutions, and par proposals.

Count lines point at ``skus`` the same way ``stock_movements`` does. Expected
quantity is filled in when a session is submitted. A conflict resolution stores
the quantity a person chose when two devices disagreed. Par lives on
``skus.par``; proposals only suggest a new integer.

Row level security matches ``0009_audit_and_vault`` and ``0010_stock_ledger``.
SQLite skips those statements.

Revision ID: 0011_counts_and_par
Revises: 0010_stock_ledger
Create Date: 2026-11-24

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_counts_and_par"
down_revision: Union[str, Sequence[str], None] = "0010_stock_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COUNT_STATUS = "('in_progress', 'submitted', 'approved', 'canceled')"
_PAR_STATUS = "('pending', 'accepted', 'rejected')"


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


def _create_tables() -> None:
    op.create_table(
        "count_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'in_progress'")),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.CheckConstraint(f"status IN {_COUNT_STATUS}", name="ck_count_sessions_status"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_count_sessions_venue_id"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], name="fk_count_sessions_location_id"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], name="fk_count_sessions_started_by"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], name="fk_count_sessions_submitted_by"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], name="fk_count_sessions_approved_by"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_count_sessions_venue_id", "count_sessions", ["venue_id"])
    op.create_index("ix_count_sessions_location_id", "count_sessions", ["location_id"])
    op.create_table(
        "count_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("bin_id", sa.Uuid(), nullable=True),
        sa.Column("counted_quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("expected_quantity", sa.Numeric(12, 2), nullable=True),
        sa.Column("device_id", sa.String(64), nullable=False, server_default=sa.text("'web'")),
        sa.Column("client_mutation_id", sa.String(120), nullable=False),
        sa.Column("counted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.CheckConstraint("counted_quantity >= 0", name="ck_count_lines_quantity"),
        sa.CheckConstraint("device_id <> ''", name="ck_count_lines_device"),
        sa.CheckConstraint("client_mutation_id <> ''", name="ck_count_lines_mutation"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_count_lines_venue_id"),
        sa.ForeignKeyConstraint(["session_id"], ["count_sessions.id"], name="fk_count_lines_session_id"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_count_lines_sku_id"),
        sa.ForeignKeyConstraint(["bin_id"], ["bins.id"], name="fk_count_lines_bin_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "client_mutation_id", name="uq_count_lines_session_mutation"),
    )
    op.create_index("ix_count_lines_venue_id", "count_lines", ["venue_id"])
    op.create_index("ix_count_lines_session_id", "count_lines", ["session_id"])
    op.create_index("ix_count_lines_sku_id", "count_lines", ["sku_id"])
    op.create_index("ix_count_lines_bin_id", "count_lines", ["bin_id"])
    op.create_table(
        "count_conflict_resolutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("resolved_quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("resolved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("resolved_quantity >= 0", name="ck_count_resolutions_quantity"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_count_resolutions_venue_id"),
        sa.ForeignKeyConstraint(["session_id"], ["count_sessions.id"], name="fk_count_resolutions_session_id"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_count_resolutions_sku_id"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], name="fk_count_resolutions_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sku_id", name="uq_count_resolutions_session_sku"),
    )
    op.create_index("ix_count_conflict_resolutions_venue_id", "count_conflict_resolutions", ["venue_id"])
    op.create_index("ix_count_conflict_resolutions_session_id", "count_conflict_resolutions", ["session_id"])
    op.create_index("ix_count_conflict_resolutions_sku_id", "count_conflict_resolutions", ["sku_id"])
    op.create_table(
        "par_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("current_par", sa.Integer(), nullable=False),
        sa.Column("proposed_par", sa.Integer(), nullable=False),
        sa.Column("depletion_30d", sa.Numeric(12, 2), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default=sa.text("7")),
        sa.Column("safety_days", sa.Integer(), nullable=False, server_default=sa.text("4")),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("proposed_by", sa.String(80), nullable=False, server_default=sa.text("'cellar-manager'")),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN {_PAR_STATUS}", name="ck_par_proposals_status"),
        sa.CheckConstraint("lead_time_days >= 0", name="ck_par_proposals_lead"),
        sa.CheckConstraint("safety_days >= 0", name="ck_par_proposals_safety"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_par_proposals_venue_id"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_par_proposals_sku_id"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], name="fk_par_proposals_decided_by"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_par_proposals_venue_id", "par_proposals", ["venue_id"])
    op.create_index("ix_par_proposals_sku_id", "par_proposals", ["sku_id"])


def _drop_tables() -> None:
    op.drop_index("ix_par_proposals_sku_id", table_name="par_proposals")
    op.drop_index("ix_par_proposals_venue_id", table_name="par_proposals")
    op.drop_table("par_proposals")
    op.drop_index("ix_count_conflict_resolutions_sku_id", table_name="count_conflict_resolutions")
    op.drop_index("ix_count_conflict_resolutions_session_id", table_name="count_conflict_resolutions")
    op.drop_index("ix_count_conflict_resolutions_venue_id", table_name="count_conflict_resolutions")
    op.drop_table("count_conflict_resolutions")
    op.drop_index("ix_count_lines_bin_id", table_name="count_lines")
    op.drop_index("ix_count_lines_sku_id", table_name="count_lines")
    op.drop_index("ix_count_lines_session_id", table_name="count_lines")
    op.drop_index("ix_count_lines_venue_id", table_name="count_lines")
    op.drop_table("count_lines")
    op.drop_index("ix_count_sessions_location_id", table_name="count_sessions")
    op.drop_index("ix_count_sessions_venue_id", table_name="count_sessions")
    op.drop_table("count_sessions")


def upgrade() -> None:
    _create_tables()
    _enable_rls("count_sessions")
    _enable_rls("count_lines")
    _enable_rls("count_conflict_resolutions")
    _enable_rls("par_proposals")


def downgrade() -> None:
    _disable_rls("par_proposals")
    _disable_rls("count_conflict_resolutions")
    _disable_rls("count_lines")
    _disable_rls("count_sessions")
    _drop_tables()
