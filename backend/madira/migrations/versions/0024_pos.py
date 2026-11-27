"""POS connections, item mappings, the sales ledger, and sync runs.

Square access tokens live in ``pos_credentials`` as Fernet ciphertext.
``pos_connections.credential_id`` points at that row. Postgres gets row level
security on each venue-scoped table, matching ``0014``. SQLite skips those
statements. Downgrade drops the children before the credential table.

Revision ID: 0024_pos
Revises: 0023_tasting_invites
Create Date: 2026-11-25

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024_pos"
down_revision: Union[str, Sequence[str], None] = "0023_tasting_invites"
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
    op.create_table(
        "pos_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_last4", sa.String(length=8), server_default=sa.text("''"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pos_credentials_venue_id", "pos_credentials", ["venue_id"])
    _enable_rls("pos_credentials")

    op.create_table(
        "pos_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("location_id", sa.String(length=64), server_default=sa.text("''"), nullable=False),
        sa.Column("location_name", sa.String(length=200), server_default=sa.text("''"), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cursor", sa.String(length=512), server_default=sa.text("''"), nullable=False),
        sa.Column("watermark", sa.String(length=64), server_default=sa.text("''"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("provider IN ('square', 'demo')", name="ck_pos_connections_provider"),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'disconnected', 'error')",
            name="ck_pos_connections_status",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["credential_id"], ["pos_credentials.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "provider", name="uq_pos_connections_venue_provider"),
    )
    op.create_index("ix_pos_connections_venue_id", "pos_connections", ["venue_id"])
    _enable_rls("pos_connections")

    op.create_table(
        "pos_item_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("item_id", sa.String(length=128), server_default=sa.text("''"), nullable=False),
        sa.Column("variation_id", sa.String(length=128), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("pour_ml", sa.Integer(), nullable=True),
        sa.Column("units_per_sale", sa.Numeric(12, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("units_per_sale > 0", name="ck_pos_item_mappings_units"),
        sa.CheckConstraint("pour_ml IS NULL OR pour_ml > 0", name="ck_pos_item_mappings_pour"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "provider", "variation_id", name="uq_pos_item_mappings_variation"),
    )
    op.create_index("ix_pos_item_mappings_venue_id", "pos_item_mappings", ["venue_id"])
    _enable_rls("pos_item_mappings")

    op.create_table(
        "pos_sales",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("external_line_id", sa.String(length=200), nullable=False),
        sa.Column("order_id", sa.String(length=128), server_default=sa.text("''"), nullable=False),
        sa.Column("variation_id", sa.String(length=128), server_default=sa.text("''"), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("movement_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["movement_id"], ["stock_movements.id"]),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "provider", "external_line_id", name="uq_pos_sales_line"),
    )
    op.create_index("ix_pos_sales_venue_id", "pos_sales", ["venue_id"])
    _enable_rls("pos_sales")

    op.create_table(
        "pos_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'running'"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_pos_sync_runs_status"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["pos_connections.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pos_sync_runs_venue_id", "pos_sync_runs", ["venue_id"])
    _enable_rls("pos_sync_runs")


def downgrade() -> None:
    _disable_rls("pos_sync_runs")
    op.drop_index("ix_pos_sync_runs_venue_id", table_name="pos_sync_runs")
    op.drop_table("pos_sync_runs")
    _disable_rls("pos_sales")
    op.drop_index("ix_pos_sales_venue_id", table_name="pos_sales")
    op.drop_table("pos_sales")
    _disable_rls("pos_item_mappings")
    op.drop_index("ix_pos_item_mappings_venue_id", table_name="pos_item_mappings")
    op.drop_table("pos_item_mappings")
    _disable_rls("pos_connections")
    op.drop_index("ix_pos_connections_venue_id", table_name="pos_connections")
    op.drop_table("pos_connections")
    _disable_rls("pos_credentials")
    op.drop_index("ix_pos_credentials_venue_id", table_name="pos_credentials")
    op.drop_table("pos_credentials")
