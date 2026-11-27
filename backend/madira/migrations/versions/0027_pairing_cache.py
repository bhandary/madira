"""Cache deterministic pairing assignments per venue and dish.

The row stores the slot assignment, not model copy. ``cache_key`` is a hash
of the dish version, published list versions, and the bottles, stock, notes,
and pins the scorer reads. Postgres RLS uses the 0014 venue helper. SQLite
skips it. Downgrade drops the policy and the table.

Revision ID: 0027_pairing_cache
Revises: 0026_usage_metering
Create Date: 2026-11-27

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027_pairing_cache"
down_revision: Union[str, Sequence[str], None] = "0026_usage_metering"
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
        "pairing_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("dish_id", sa.Uuid(), nullable=False),
        sa.Column("menu_version_id", sa.Uuid(), nullable=False),
        sa.Column("list_version_id", sa.Uuid(), nullable=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["list_version_id"], ["list_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["menu_version_id"], ["menu_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "dish_id", name="uq_pairing_cache_venue_dish"),
    )
    op.create_index("ix_pairing_cache_venue_id", "pairing_cache", ["venue_id"])
    op.create_index("ix_pairing_cache_dish_id", "pairing_cache", ["dish_id"])
    op.create_index("ix_pairing_cache_menu_version_id", "pairing_cache", ["menu_version_id"])
    op.create_index("ix_pairing_cache_list_version_id", "pairing_cache", ["list_version_id"])
    _enable_rls("pairing_cache")


def downgrade() -> None:
    _disable_rls("pairing_cache")
    op.drop_index("ix_pairing_cache_list_version_id", table_name="pairing_cache")
    op.drop_index("ix_pairing_cache_menu_version_id", table_name="pairing_cache")
    op.drop_index("ix_pairing_cache_dish_id", table_name="pairing_cache")
    op.drop_index("ix_pairing_cache_venue_id", table_name="pairing_cache")
    op.drop_table("pairing_cache")
