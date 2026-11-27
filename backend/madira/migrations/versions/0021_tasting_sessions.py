"""Tasting sessions and samples, replacing the tastings table.

Existing tasting rows move into tasting_sessions with the same id. The stored
ics text is dropped; the calendar file is built when it is downloaded. Postgres
gets row level security on the two new venue-scoped tables, matching ``0014``.
SQLite skips those statements. The copy runs only after the old policy is
removed, so a forced venue policy cannot hide rows from the migration.

Revision ID: 0021_tasting_sessions
Revises: 0020_supplier_offers
Create Date: 2026-11-25

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_tasting_sessions"
down_revision: Union[str, Sequence[str], None] = "0020_supplier_offers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUSES = "('planned', 'held', 'closed')"
_DECISIONS = "('undecided', 'buy', 'list', 'pass')"


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


def _legacy_ics(title, starts, ends, location, notes) -> str:
    def compact(value) -> str:
        text = value.isoformat() if hasattr(value, "isoformat") else str(value or "")
        return text.replace("-", "").replace(":", "").replace(" ", "T").replace("+", "")[:15]

    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Maison Madira//Madira//EN",
            "BEGIN:VEVENT",
            f"DTSTART:{compact(starts)}",
            f"DTEND:{compact(ends)}",
            f"SUMMARY:{title or ''}",
            f"LOCATION:{location or ''}",
            f"DESCRIPTION:{notes or ''}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )


def upgrade() -> None:
    op.create_table(
        "tasting_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN {_STATUSES}", name="ck_tasting_sessions_status"),
        sa.CheckConstraint("ends_at >= starts_at", name="ck_tasting_sessions_window"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_tasting_sessions_venue_id"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_tasting_sessions_supplier_id"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_tasting_sessions_created_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasting_sessions_venue_id", "tasting_sessions", ["venue_id"])
    op.create_index("ix_tasting_sessions_supplier_id", "tasting_sessions", ["supplier_id"])
    op.create_index("ix_tasting_sessions_created_by_user_id", "tasting_sessions", ["created_by_user_id"])

    op.create_table(
        "samples",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("sku_id", sa.Uuid(), nullable=True),
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
        sa.Column("offer_id", sa.Uuid(), nullable=True),
        sa.Column("label_document_id", sa.Uuid(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("quoted_price_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("decision", sa.String(16), nullable=False, server_default=sa.text("'undecided'")),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_samples_score"),
        sa.CheckConstraint(f"decision IN {_DECISIONS}", name="ck_samples_decision"),
        sa.CheckConstraint(
            "quoted_price_cents IS NULL OR quoted_price_cents >= 0",
            name="ck_samples_quoted_price",
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_samples_venue_id"),
        sa.ForeignKeyConstraint(["session_id"], ["tasting_sessions.id"], name="fk_samples_session_id"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_samples_product_id"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_samples_sku_id"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_samples_supplier_id"),
        sa.ForeignKeyConstraint(["offer_id"], ["supplier_offers.id"], name="fk_samples_offer_id"),
        sa.ForeignKeyConstraint(["label_document_id"], ["documents.id"], name="fk_samples_label_document_id"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], name="fk_samples_decided_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_samples_venue_id", "samples", ["venue_id"])
    op.create_index("ix_samples_session_id", "samples", ["session_id"])
    op.create_index("ix_samples_product_id", "samples", ["product_id"])
    op.create_index("ix_samples_sku_id", "samples", ["sku_id"])
    op.create_index("ix_samples_supplier_id", "samples", ["supplier_id"])
    op.create_index("ix_samples_offer_id", "samples", ["offer_id"])
    op.create_index("ix_samples_label_document_id", "samples", ["label_document_id"])
    op.create_index("ix_samples_decided_by_user_id", "samples", ["decided_by_user_id"])
    op.create_index("ix_samples_venue_session", "samples", ["venue_id", "session_id"])

    _disable_rls("tastings")
    op.execute(
        """
        INSERT INTO tasting_sessions (
            id, venue_id, supplier_id, title, starts_at, ends_at, location, status, notes, created_by_user_id, created_at
        )
        SELECT id, venue_id, supplier_id, title, starts_at, ends_at, location, 'planned', notes, NULL, created_at
        FROM tastings
        """
    )
    op.drop_index("ix_tastings_venue_id", table_name="tastings")
    op.drop_table("tastings")

    _enable_rls("tasting_sessions")
    _enable_rls("samples")


def downgrade() -> None:
    _disable_rls("samples")
    _disable_rls("tasting_sessions")

    op.create_table(
        "tastings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("ics", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_tastings_venue_id"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_tastings_supplier_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tastings_venue_id", "tastings", ["venue_id"])

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, venue_id, supplier_id, title, starts_at, ends_at, location, notes, created_at
            FROM tasting_sessions
            WHERE supplier_id IS NOT NULL
            """
        )
    ).mappings()
    for row in rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO tastings (
                    id, venue_id, supplier_id, title, starts_at, ends_at, location, notes, ics, created_at
                )
                VALUES (
                    :id, :venue_id, :supplier_id, :title, :starts_at, :ends_at, :location, :notes, :ics, :created_at
                )
                """
            ),
            {
                "id": row["id"],
                "venue_id": row["venue_id"],
                "supplier_id": row["supplier_id"],
                "title": row["title"],
                "starts_at": row["starts_at"],
                "ends_at": row["ends_at"],
                "location": row["location"] or "",
                "notes": row["notes"] or "",
                "ics": _legacy_ics(row["title"], row["starts_at"], row["ends_at"], row["location"], row["notes"]),
                "created_at": row["created_at"],
            },
        )

    _enable_rls("tastings")

    op.drop_index("ix_samples_venue_session", table_name="samples")
    op.drop_index("ix_samples_decided_by_user_id", table_name="samples")
    op.drop_index("ix_samples_label_document_id", table_name="samples")
    op.drop_index("ix_samples_offer_id", table_name="samples")
    op.drop_index("ix_samples_supplier_id", table_name="samples")
    op.drop_index("ix_samples_sku_id", table_name="samples")
    op.drop_index("ix_samples_product_id", table_name="samples")
    op.drop_index("ix_samples_session_id", table_name="samples")
    op.drop_index("ix_samples_venue_id", table_name="samples")
    op.drop_table("samples")

    op.drop_index("ix_tasting_sessions_created_by_user_id", table_name="tasting_sessions")
    op.drop_index("ix_tasting_sessions_supplier_id", table_name="tasting_sessions")
    op.drop_index("ix_tasting_sessions_venue_id", table_name="tasting_sessions")
    op.drop_table("tasting_sessions")
