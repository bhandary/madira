"""Venue invites, roleplay sessions, and staff certificates.

Postgres gets row level security on the three new venue-scoped tables,
matching ``0014``. SQLite skips those statements. An active invite is one
that is neither accepted nor revoked, and a venue can have only one of
those per email.

Revision ID: 0018_team_roleplay_certificates
Revises: 0017_briefings
Create Date: 2026-11-24

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_team_roleplay_certificates"
down_revision: Union[str, Sequence[str], None] = "0017_briefings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLES = "('Owner', 'Sommelier', 'Manager', 'Staff', 'Auditor')"
_POSITIONS = "('server', 'bartender', 'barback', 'host')"
_PERSONAS = "('skeptic', 'budget-conscious', 'connoisseur', 'celebration')"
_KINDS = "('responsible_service', 'food_handler', 'other')"


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
        "venue_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("position", sa.String(16), nullable=True),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"role IN {_ROLES}", name="ck_venue_invites_role"),
        sa.CheckConstraint(
            f"position IS NULL OR position IN {_POSITIONS}",
            name="ck_venue_invites_position",
        ),
        sa.CheckConstraint(
            "(accepted_at IS NULL AND accepted_user_id IS NULL) OR "
            "(accepted_at IS NOT NULL AND accepted_user_id IS NOT NULL)",
            name="ck_venue_invites_acceptance",
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_venue_invites_venue_id"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], name="fk_venue_invites_invited_by_user_id"),
        sa.ForeignKeyConstraint(["accepted_user_id"], ["users.id"], name="fk_venue_invites_accepted_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venue_invites_venue_id", "venue_invites", ["venue_id"])
    op.create_index("ix_venue_invites_invited_by_user_id", "venue_invites", ["invited_by_user_id"])
    op.create_index("ix_venue_invites_accepted_user_id", "venue_invites", ["accepted_user_id"])
    op.create_index("ix_venue_invites_email", "venue_invites", ["email"])
    op.create_index(
        "uq_venue_invites_active_email",
        "venue_invites",
        ["venue_id", "email"],
        unique=True,
        sqlite_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )

    op.create_table(
        "roleplay_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("persona", sa.String(32), nullable=False),
        sa.Column("dish_id", sa.Uuid(), nullable=True),
        sa.Column("transcript", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("rubric", sa.JSON(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'open'")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"persona IN {_PERSONAS}", name="ck_roleplay_sessions_persona"),
        sa.CheckConstraint("status IN ('open', 'scored')", name="ck_roleplay_sessions_status"),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 4)", name="ck_roleplay_sessions_score_range"),
        sa.CheckConstraint(
            "(status = 'open' AND score IS NULL AND scored_at IS NULL) OR "
            "(status = 'scored' AND score IS NOT NULL AND scored_at IS NOT NULL)",
            name="ck_roleplay_sessions_scored",
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_roleplay_sessions_venue_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_roleplay_sessions_user_id"),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], name="fk_roleplay_sessions_dish_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_roleplay_sessions_venue_id", "roleplay_sessions", ["venue_id"])
    op.create_index("ix_roleplay_sessions_user_id", "roleplay_sessions", ["user_id"])
    op.create_index("ix_roleplay_sessions_dish_id", "roleplay_sessions", ["dish_id"])

    op.create_table(
        "certificates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"kind IN {_KINDS}", name="ck_certificates_kind"),
        sa.CheckConstraint("expires_on >= issued_on", name="ck_certificates_dates"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_certificates_venue_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_certificates_user_id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_certificates_document_id"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_certificates_created_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_certificates_venue_id", "certificates", ["venue_id"])
    op.create_index("ix_certificates_user_id", "certificates", ["user_id"])
    op.create_index("ix_certificates_document_id", "certificates", ["document_id"])
    op.create_index("ix_certificates_created_by_user_id", "certificates", ["created_by_user_id"])
    op.create_index("ix_certificates_expires_on", "certificates", ["expires_on"])

    _enable_rls("venue_invites")
    _enable_rls("roleplay_sessions")
    _enable_rls("certificates")


def downgrade() -> None:
    _disable_rls("certificates")
    _disable_rls("roleplay_sessions")
    _disable_rls("venue_invites")

    op.drop_index("ix_certificates_expires_on", table_name="certificates")
    op.drop_index("ix_certificates_created_by_user_id", table_name="certificates")
    op.drop_index("ix_certificates_document_id", table_name="certificates")
    op.drop_index("ix_certificates_user_id", table_name="certificates")
    op.drop_index("ix_certificates_venue_id", table_name="certificates")
    op.drop_table("certificates")

    op.drop_index("ix_roleplay_sessions_dish_id", table_name="roleplay_sessions")
    op.drop_index("ix_roleplay_sessions_user_id", table_name="roleplay_sessions")
    op.drop_index("ix_roleplay_sessions_venue_id", table_name="roleplay_sessions")
    op.drop_table("roleplay_sessions")

    op.drop_index("uq_venue_invites_active_email", table_name="venue_invites")
    op.drop_index("ix_venue_invites_email", table_name="venue_invites")
    op.drop_index("ix_venue_invites_accepted_user_id", table_name="venue_invites")
    op.drop_index("ix_venue_invites_invited_by_user_id", table_name="venue_invites")
    op.drop_index("ix_venue_invites_venue_id", table_name="venue_invites")
    op.drop_table("venue_invites")
