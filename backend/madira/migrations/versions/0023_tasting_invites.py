"""Tasting invites, proposed slots, and attendees.

A venue setting ``invite_delivery`` only allows ``draft_only``. Postgres gets
row level security on the three new venue-scoped tables, matching ``0014``,
and the check constraint. SQLite skips those statements and adds the column
in place. The service rejects every other driver on both engines.

Revision ID: 0023_tasting_invites
Revises: 0022_sourcing
Create Date: 2026-11-25

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023_tasting_invites"
down_revision: Union[str, Sequence[str], None] = "0022_sourcing"
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
    # A new column is an in-place ALTER. Rebuilding venues fails on SQLite
    # because the rest of the schema references it. Postgres also gets the
    # check constraint; both engines reject any other driver in the service.
    op.add_column(
        "venues",
        sa.Column(
            "invite_delivery",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'draft_only'"),
        ),
    )
    if _is_postgres():
        op.create_check_constraint("ck_venues_invite_delivery", "venues", "invite_delivery IN ('draft_only')")

    op.create_table(
        "tasting_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'proposed'")),
        sa.Column("agenda_note", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("agenda_facts", sa.JSON(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("ics_text", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("email_subject", sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column("email_body", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("email_mailto", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("driver", sa.String(16), nullable=False, server_default=sa.text("''")),
        sa.Column("sent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed', 'ready', 'rejected')",
            name="ck_tasting_invites_status",
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["tasting_sessions.id"]),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_tasting_invites_session"),
    )
    op.create_index("ix_tasting_invites_venue_id", "tasting_invites", ["venue_id"])
    op.create_index("ix_tasting_invites_approval_id", "tasting_invites", ["approval_id"])

    op.create_table(
        "tasting_invite_slots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("invite_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default=sa.text("'entered'")),
        sa.Column("chosen", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["invite_id"], ["tasting_invites.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_id", "position", name="uq_tasting_invite_slots_position"),
    )
    op.create_index("ix_tasting_invite_slots_venue", "tasting_invite_slots", ["venue_id", "invite_id"])

    op.create_table(
        "tasting_invite_attendees",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("invite_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column("email", sa.String(320), nullable=False, server_default=sa.text("''")),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["invite_id"], ["tasting_invites.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tasting_invite_attendees_venue",
        "tasting_invite_attendees",
        ["venue_id", "invite_id"],
    )

    _enable_rls("tasting_invites")
    _enable_rls("tasting_invite_slots")
    _enable_rls("tasting_invite_attendees")


def downgrade() -> None:
    _disable_rls("tasting_invite_attendees")
    _disable_rls("tasting_invite_slots")
    _disable_rls("tasting_invites")
    op.drop_index("ix_tasting_invite_attendees_venue", table_name="tasting_invite_attendees")
    op.drop_table("tasting_invite_attendees")
    op.drop_index("ix_tasting_invite_slots_venue", table_name="tasting_invite_slots")
    op.drop_table("tasting_invite_slots")
    op.drop_index("ix_tasting_invites_approval_id", table_name="tasting_invites")
    op.drop_index("ix_tasting_invites_venue_id", table_name="tasting_invites")
    op.drop_table("tasting_invites")
    if _is_postgres():
        op.drop_constraint("ck_venues_invite_delivery", "venues", type_="check")
    op.drop_column("venues", "invite_delivery")
