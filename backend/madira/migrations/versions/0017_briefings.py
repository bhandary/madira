"""Daily briefings, acknowledgements, and the 86 flag.

A briefing is one row per venue and local service date. Acknowledgements are
one row per person. Postgres gets row level security on the two new
venue-scoped tables, matching ``0014``. SQLite skips those statements.

Revision ID: 0017_briefings
Revises: 0016_training_content
Create Date: 2026-11-24

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_briefings"
down_revision: Union[str, Sequence[str], None] = "0016_training_content"
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
        sa.Column(
            "timezone",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'America/Los_Angeles'"),
        ),
    )
    op.add_column(
        "venues",
        sa.Column("briefing_hour", sa.Integer(), nullable=False, server_default=sa.text("15")),
    )
    op.add_column("skus", sa.Column("eighty_sixed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("skus", sa.Column("eighty_sixed_by_user_id", sa.Uuid(), nullable=True))
    if _is_postgres():
        op.create_foreign_key(
            "fk_skus_eighty_sixed_by_user_id",
            "skus",
            "users",
            ["eighty_sixed_by_user_id"],
            ["id"],
        )
    op.create_index("ix_skus_eighty_sixed_by_user_id", "skus", ["eighty_sixed_by_user_id"])
    op.add_column(
        "dishes",
        sa.Column("is_special", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )

    op.create_table(
        "briefings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("intro", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("cards", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("push_sku_id", sa.Uuid(), nullable=True),
        sa.Column("due_review_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("built_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_briefings_status"),
        sa.CheckConstraint("due_review_count >= 0", name="ck_briefings_due_reviews"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_briefings_venue_id"),
        sa.ForeignKeyConstraint(["push_sku_id"], ["skus.id"], name="fk_briefings_push_sku_id"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], name="fk_briefings_published_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "service_date", name="uq_briefings_venue_date"),
    )
    op.create_index("ix_briefings_venue_id", "briefings", ["venue_id"])
    op.create_index("ix_briefings_push_sku_id", "briefings", ["push_sku_id"])
    op.create_index("ix_briefings_published_by_user_id", "briefings", ["published_by_user_id"])

    op.create_table(
        "briefing_acks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("briefing_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("seconds_to_ack", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("seconds_to_ack >= 0", name="ck_briefing_acks_seconds"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_briefing_acks_venue_id"),
        sa.ForeignKeyConstraint(["briefing_id"], ["briefings.id"], name="fk_briefing_acks_briefing_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_briefing_acks_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("briefing_id", "user_id", name="uq_briefing_acks_briefing_user"),
    )
    op.create_index("ix_briefing_acks_venue_id", "briefing_acks", ["venue_id"])
    op.create_index("ix_briefing_acks_briefing_id", "briefing_acks", ["briefing_id"])
    op.create_index("ix_briefing_acks_user_id", "briefing_acks", ["user_id"])

    _enable_rls("briefings")
    _enable_rls("briefing_acks")


def downgrade() -> None:
    _disable_rls("briefing_acks")
    _disable_rls("briefings")

    op.drop_index("ix_briefing_acks_user_id", table_name="briefing_acks")
    op.drop_index("ix_briefing_acks_briefing_id", table_name="briefing_acks")
    op.drop_index("ix_briefing_acks_venue_id", table_name="briefing_acks")
    op.drop_table("briefing_acks")

    op.drop_index("ix_briefings_published_by_user_id", table_name="briefings")
    op.drop_index("ix_briefings_push_sku_id", table_name="briefings")
    op.drop_index("ix_briefings_venue_id", table_name="briefings")
    op.drop_table("briefings")

    op.drop_column("dishes", "is_special")
    op.drop_index("ix_skus_eighty_sixed_by_user_id", table_name="skus")
    if _is_postgres():
        op.drop_constraint("fk_skus_eighty_sixed_by_user_id", "skus", type_="foreignkey")
    op.drop_column("skus", "eighty_sixed_by_user_id")
    op.drop_column("skus", "eighty_sixed_at")
    op.drop_column("venues", "briefing_hour")
    op.drop_column("venues", "timezone")
