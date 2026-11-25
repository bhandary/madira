"""Supplier profiles, allocations, offers, and price sheets.

Postgres gets row level security on the three new venue-scoped tables, matching
``0014``. The new supplier columns sit on the existing suppliers table, which
already has the venue policy. SQLite skips the RLS statements.

Revision ID: 0020_supplier_offers
Revises: 0019_list_versions
Create Date: 2026-11-25

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020_supplier_offers"
down_revision: Union[str, Sequence[str], None] = "0019_list_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCES = "('manual', 'csv', 'pdf')"
_SHEET = "('pending_review', 'applied', 'rejected')"


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
    op.add_column("suppliers", sa.Column("rep_name", sa.String(200), nullable=False, server_default=sa.text("''")))
    op.add_column("suppliers", sa.Column("rep_email", sa.String(320), nullable=False, server_default=sa.text("''")))
    op.add_column("suppliers", sa.Column("rep_phone", sa.String(40), nullable=True))
    op.add_column(
        "suppliers",
        sa.Column("order_minimum_currency", sa.String(3), nullable=False, server_default=sa.text("'USD'")),
    )

    op.create_table(
        "supplier_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("period_label", sa.String(120), nullable=False, server_default=sa.text("''")),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_supplier_allocations_quantity"),
        sa.CheckConstraint(
            "period_end IS NULL OR period_start IS NULL OR period_end >= period_start",
            name="ck_supplier_allocations_period",
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_supplier_allocations_venue_id"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_supplier_allocations_supplier_id"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_supplier_allocations_product_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supplier_allocations_venue_id", "supplier_allocations", ["venue_id"])
    op.create_index("ix_supplier_allocations_supplier_id", "supplier_allocations", ["supplier_id"])
    op.create_index("ix_supplier_allocations_product_id", "supplier_allocations", ["product_id"])
    op.create_index(
        "ix_supplier_allocations_venue_supplier",
        "supplier_allocations",
        ["venue_id", "supplier_id"],
    )

    op.create_table(
        "price_sheets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'pending_review'")),
        sa.Column("parsed_rows", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"status IN {_SHEET}", name="ck_price_sheets_status"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_price_sheets_venue_id"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_price_sheets_supplier_id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_price_sheets_document_id"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_price_sheets_created_by_user_id"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], name="fk_price_sheets_reviewed_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_sheets_venue_id", "price_sheets", ["venue_id"])
    op.create_index("ix_price_sheets_supplier_id", "price_sheets", ["supplier_id"])
    op.create_index("ix_price_sheets_document_id", "price_sheets", ["document_id"])
    op.create_index("ix_price_sheets_created_by_user_id", "price_sheets", ["created_by_user_id"])
    op.create_index("ix_price_sheets_reviewed_by_user_id", "price_sheets", ["reviewed_by_user_id"])

    op.create_table(
        "supplier_offers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=True),
        sa.Column("unit_description", sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column("case_size", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("price_sheet_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"source IN {_SOURCES}", name="ck_supplier_offers_source"),
        sa.CheckConstraint("price_cents >= 0", name="ck_supplier_offers_price"),
        sa.CheckConstraint("case_size >= 1", name="ck_supplier_offers_case_size"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_supplier_offers_window"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_supplier_offers_venue_id"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_supplier_offers_supplier_id"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_supplier_offers_product_id"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_supplier_offers_sku_id"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], name="fk_supplier_offers_source_document_id"),
        sa.ForeignKeyConstraint(["price_sheet_id"], ["price_sheets.id"], name="fk_supplier_offers_price_sheet_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supplier_offers_venue_id", "supplier_offers", ["venue_id"])
    op.create_index("ix_supplier_offers_supplier_id", "supplier_offers", ["supplier_id"])
    op.create_index("ix_supplier_offers_product_id", "supplier_offers", ["product_id"])
    op.create_index("ix_supplier_offers_sku_id", "supplier_offers", ["sku_id"])
    op.create_index("ix_supplier_offers_source_document_id", "supplier_offers", ["source_document_id"])
    op.create_index("ix_supplier_offers_price_sheet_id", "supplier_offers", ["price_sheet_id"])
    op.create_index("ix_supplier_offers_venue_product", "supplier_offers", ["venue_id", "product_id"])
    op.create_index("ix_supplier_offers_venue_supplier", "supplier_offers", ["venue_id", "supplier_id"])

    _enable_rls("supplier_allocations")
    _enable_rls("price_sheets")
    _enable_rls("supplier_offers")


def downgrade() -> None:
    _disable_rls("supplier_offers")
    op.drop_index("ix_supplier_offers_venue_supplier", table_name="supplier_offers")
    op.drop_index("ix_supplier_offers_venue_product", table_name="supplier_offers")
    op.drop_index("ix_supplier_offers_price_sheet_id", table_name="supplier_offers")
    op.drop_index("ix_supplier_offers_source_document_id", table_name="supplier_offers")
    op.drop_index("ix_supplier_offers_sku_id", table_name="supplier_offers")
    op.drop_index("ix_supplier_offers_product_id", table_name="supplier_offers")
    op.drop_index("ix_supplier_offers_supplier_id", table_name="supplier_offers")
    op.drop_index("ix_supplier_offers_venue_id", table_name="supplier_offers")
    op.drop_table("supplier_offers")

    _disable_rls("price_sheets")
    op.drop_index("ix_price_sheets_reviewed_by_user_id", table_name="price_sheets")
    op.drop_index("ix_price_sheets_created_by_user_id", table_name="price_sheets")
    op.drop_index("ix_price_sheets_document_id", table_name="price_sheets")
    op.drop_index("ix_price_sheets_supplier_id", table_name="price_sheets")
    op.drop_index("ix_price_sheets_venue_id", table_name="price_sheets")
    op.drop_table("price_sheets")

    _disable_rls("supplier_allocations")
    op.drop_index("ix_supplier_allocations_venue_supplier", table_name="supplier_allocations")
    op.drop_index("ix_supplier_allocations_product_id", table_name="supplier_allocations")
    op.drop_index("ix_supplier_allocations_supplier_id", table_name="supplier_allocations")
    op.drop_index("ix_supplier_allocations_venue_id", table_name="supplier_allocations")
    op.drop_table("supplier_allocations")

    op.drop_column("suppliers", "order_minimum_currency")
    op.drop_column("suppliers", "rep_phone")
    op.drop_column("suppliers", "rep_email")
    op.drop_column("suppliers", "rep_name")
