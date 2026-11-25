"""List versions, snapshot rows, and the guest list projection.

Postgres gets row level security on the two venue-scoped tables, matching
``0014``. The guest projection has no venue column and no RLS: the anonymous
route reads only that table. SQLite skips the RLS statements.

Revision ID: 0019_list_versions
Revises: 0018_team_roleplay_certificates
Create Date: 2026-11-25

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_list_versions"
down_revision: Union[str, Sequence[str], None] = "0018_team_roleplay_certificates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS = "('draft', 'pending_approval', 'published', 'superseded', 'rejected')"


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
        "list_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("public_token", sa.String(128), nullable=True),
        sa.Column("public_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN {_STATUS}", name="ck_list_versions_status"),
        sa.CheckConstraint("number >= 1", name="ck_list_versions_number"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_list_versions_venue_id"),
        sa.ForeignKeyConstraint(["list_id"], ["beverage_lists.id"], name="fk_list_versions_list_id"),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], name="fk_list_versions_approval_id"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], name="fk_list_versions_submitted_by_user_id"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], name="fk_list_versions_published_by_user_id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_list_versions_document_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("list_id", "number", name="uq_list_versions_list_number"),
        sa.UniqueConstraint("public_token", name="uq_list_versions_public_token"),
    )
    op.create_index("ix_list_versions_venue_id", "list_versions", ["venue_id"])
    op.create_index("ix_list_versions_list_id", "list_versions", ["list_id"])
    op.create_index("ix_list_versions_approval_id", "list_versions", ["approval_id"])

    op.create_table(
        "list_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("section_name", sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("bottle_price_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("glass_price_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("display_name", sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column("display_detail", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.CheckConstraint("position >= 0", name="ck_list_entries_position"),
        sa.CheckConstraint("bottle_price_cents >= 0", name="ck_list_entries_bottle_price"),
        sa.CheckConstraint("glass_price_cents >= 0", name="ck_list_entries_glass_price"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_list_entries_venue_id"),
        sa.ForeignKeyConstraint(["version_id"], ["list_versions.id"], name="fk_list_entries_version_id"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_list_entries_sku_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_list_entries_venue_id", "list_entries", ["venue_id"])
    op.create_index("ix_list_entries_version_id", "list_entries", ["version_id"])
    op.create_index("ix_list_entries_sku_id", "list_entries", ["sku_id"])

    op.create_table(
        "public_list_snapshots",
        sa.Column("token", sa.String(128), nullable=False),
        sa.Column("venue_name", sa.String(200), nullable=False),
        sa.Column("rendered", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("token"),
    )

    _enable_rls("list_versions")
    _enable_rls("list_entries")


def downgrade() -> None:
    op.drop_table("public_list_snapshots")

    _disable_rls("list_entries")
    op.drop_index("ix_list_entries_sku_id", table_name="list_entries")
    op.drop_index("ix_list_entries_version_id", table_name="list_entries")
    op.drop_index("ix_list_entries_venue_id", table_name="list_entries")
    op.drop_table("list_entries")

    _disable_rls("list_versions")
    op.drop_index("ix_list_versions_approval_id", table_name="list_versions")
    op.drop_index("ix_list_versions_list_id", table_name="list_versions")
    op.drop_index("ix_list_versions_venue_id", table_name="list_versions")
    op.drop_table("list_versions")
