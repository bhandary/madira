"""Tasting notes and service cards.

A tasting note belongs to one venue and one product. It holds the three
texts, the structured profile the draft proposes, who wrote it, and whether
the venue has approved it. A service card is the pour that goes with that
note. Both stay draft until an Owner or Sommelier approves them.

Revision ID: 0006_tasting_notes
Revises: 0005_list_import
Create Date: 2026-11-17

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_tasting_notes"
down_revision: Union[str, Sequence[str], None] = "0005_list_import"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("tasting_notes", "service_cards")


def _bind():
    return op.get_bind()


def _is_postgres() -> bool:
    return _bind().dialect.name == "postgresql"


def _enable_rls() -> None:
    if not _is_postgres():
        return
    for table in _TABLES:
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


def _disable_rls() -> None:
    if not _is_postgres():
        return
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS venue_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "tasting_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("server_hook", sa.Text(), nullable=False),
        sa.Column("guest_description", sa.Text(), nullable=False),
        sa.Column("technical_note", sa.Text(), nullable=False),
        sa.Column("body", sa.String(length=32), nullable=False),
        sa.Column("acidity", sa.String(length=32), nullable=False),
        sa.Column("tannin", sa.String(length=32), nullable=False),
        sa.Column("sweetness", sa.String(length=32), nullable=False),
        sa.Column("oak", sa.String(length=32), nullable=False),
        sa.Column("intensity", sa.String(length=32), nullable=False),
        sa.Column("aroma_families", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tech_sheet_key", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source IN ('agent', 'staff')", name="ck_tasting_notes_source"),
        sa.CheckConstraint("status IN ('draft', 'approved')", name="ck_tasting_notes_status"),
        sa.CheckConstraint(
            "(status = 'draft' AND approved_by IS NULL AND approved_at IS NULL) OR "
            "(status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_tasting_notes_approval",
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], name="fk_tasting_notes_approved_by"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_tasting_notes_product_id"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_tasting_notes_venue_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasting_notes_venue_id", "tasting_notes", ["venue_id"])
    op.create_index("ix_tasting_notes_product_id", "tasting_notes", ["product_id"])
    op.create_index("ix_tasting_notes_approved_by", "tasting_notes", ["approved_by"])
    op.create_index("ix_tasting_notes_venue_product", "tasting_notes", ["venue_id", "product_id"])

    op.create_table(
        "service_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("tasting_note_id", sa.Uuid(), nullable=False),
        sa.Column("serving_temperature", sa.String(length=80), nullable=False),
        sa.Column("glassware", sa.String(length=80), nullable=False),
        sa.Column("decanting", sa.String(length=80), nullable=False),
        sa.Column("pour_size", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source IN ('agent', 'staff')", name="ck_service_cards_source"),
        sa.CheckConstraint("status IN ('draft', 'approved')", name="ck_service_cards_status"),
        sa.CheckConstraint(
            "(status = 'draft' AND approved_by IS NULL AND approved_at IS NULL) OR "
            "(status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_service_cards_approval",
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], name="fk_service_cards_approved_by"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_service_cards_product_id"),
        sa.ForeignKeyConstraint(["tasting_note_id"], ["tasting_notes.id"], name="fk_service_cards_tasting_note_id"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_service_cards_venue_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tasting_note_id", name="uq_service_cards_note"),
    )
    op.create_index("ix_service_cards_venue_id", "service_cards", ["venue_id"])
    op.create_index("ix_service_cards_product_id", "service_cards", ["product_id"])
    op.create_index("ix_service_cards_tasting_note_id", "service_cards", ["tasting_note_id"])
    op.create_index("ix_service_cards_approved_by", "service_cards", ["approved_by"])
    op.create_index("ix_service_cards_venue_product", "service_cards", ["venue_id", "product_id"])
    _enable_rls()


def downgrade() -> None:
    _disable_rls()
    op.drop_index("ix_service_cards_venue_product", table_name="service_cards")
    op.drop_index("ix_service_cards_approved_by", table_name="service_cards")
    op.drop_index("ix_service_cards_tasting_note_id", table_name="service_cards")
    op.drop_index("ix_service_cards_product_id", table_name="service_cards")
    op.drop_index("ix_service_cards_venue_id", table_name="service_cards")
    op.drop_table("service_cards")
    op.drop_index("ix_tasting_notes_venue_product", table_name="tasting_notes")
    op.drop_index("ix_tasting_notes_approved_by", table_name="tasting_notes")
    op.drop_index("ix_tasting_notes_product_id", table_name="tasting_notes")
    op.drop_index("ix_tasting_notes_venue_id", table_name="tasting_notes")
    op.drop_table("tasting_notes")
