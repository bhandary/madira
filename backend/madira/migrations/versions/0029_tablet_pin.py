"""Shared-tablet PIN hashes and device rows.

Memberships gain a scrypt PIN hash and a lockout counter. ``shared_tablets``
marks one signed-in browser as the shared device for a venue. ``tablet_actors``
is the short-lived person using that device. Postgres RLS matches ``0014``.
SQLite skips those statements. Downgrade drops the policies, the tables, and
the columns.

Revision ID: 0029_tablet_pin
Revises: 0028_jobs
Create Date: 2026-11-27

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0029_tablet_pin"
down_revision: Union[str, Sequence[str], None] = "0028_jobs"
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
    with op.batch_alter_table("memberships") as batch:
        batch.add_column(sa.Column("pin_hash", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("pin_failures", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("pin_locked_until", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "shared_tablets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("host_user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("pin_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pin_locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("pin_failures >= 0", name="ck_shared_tablets_pin_failures"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["host_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_shared_tablets_token"),
    )
    op.create_index("ix_shared_tablets_organization_id", "shared_tablets", ["organization_id"])
    op.create_index("ix_shared_tablets_venue_id", "shared_tablets", ["venue_id"])
    op.create_index("ix_shared_tablets_host_user_id", "shared_tablets", ["host_user_id"])
    _enable_rls("shared_tablets")

    op.create_table(
        "tablet_actors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tablet_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tablet_id"], ["shared_tablets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_tablet_actors_token"),
    )
    op.create_index("ix_tablet_actors_tablet_id", "tablet_actors", ["tablet_id"])
    op.create_index("ix_tablet_actors_organization_id", "tablet_actors", ["organization_id"])
    op.create_index("ix_tablet_actors_venue_id", "tablet_actors", ["venue_id"])
    op.create_index("ix_tablet_actors_user_id", "tablet_actors", ["user_id"])
    _enable_rls("tablet_actors")


def downgrade() -> None:
    _disable_rls("tablet_actors")
    op.drop_index("ix_tablet_actors_user_id", table_name="tablet_actors")
    op.drop_index("ix_tablet_actors_venue_id", table_name="tablet_actors")
    op.drop_index("ix_tablet_actors_organization_id", table_name="tablet_actors")
    op.drop_index("ix_tablet_actors_tablet_id", table_name="tablet_actors")
    op.drop_table("tablet_actors")
    _disable_rls("shared_tablets")
    op.drop_index("ix_shared_tablets_host_user_id", table_name="shared_tablets")
    op.drop_index("ix_shared_tablets_venue_id", table_name="shared_tablets")
    op.drop_index("ix_shared_tablets_organization_id", table_name="shared_tablets")
    op.drop_table("shared_tablets")
    with op.batch_alter_table("memberships") as batch:
        batch.drop_column("pin_locked_until")
        batch.drop_column("pin_failures")
        batch.drop_column("pin_hash")
