"""Invoices, receipts, and counted receipt lines.

A delivery is a receipt against a sent purchase order. The supplier invoice
file is archived in the document vault. Postgres gets row level security on
the three new venue-scoped tables, matching ``0009`` through ``0012``.
SQLite skips those statements.

Revision ID: 0013_receiving_invoices
Revises: 0012_purchasing_lifecycle
Create Date: 2026-11-24

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_receiving_invoices"
down_revision: Union[str, Sequence[str], None] = "0012_purchasing_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INVOICE_STATUS = "('uploaded', 'matched', 'discrepancy', 'accepted')"
_EXTRACTION = "('demo', 'vision', 'manual')"
_RECEIPT_STATUS = "('draft', 'accepted', 'rejected')"


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
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_number", sa.String(80), nullable=False),
        sa.Column("invoice_date", sa.String(10), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("extracted_lines", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("extraction_mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'uploaded'")),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN {_INVOICE_STATUS}", name="ck_invoices_status"),
        sa.CheckConstraint(f"extraction_mode IN {_EXTRACTION}", name="ck_invoices_extraction_mode"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_invoices_venue_id"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_invoices_supplier_id"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], name="fk_invoices_purchase_order_id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_invoices_document_id"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_invoices_created_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoices_venue_id", "invoices", ["venue_id"])
    op.create_index("ix_invoices_supplier_id", "invoices", ["supplier_id"])
    op.create_index("ix_invoices_purchase_order_id", "invoices", ["purchase_order_id"])
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"])
    op.create_index("ix_invoices_document_id", "invoices", ["document_id"])

    op.create_table(
        "receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("received_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discrepancies_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("discrepancy_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN {_RECEIPT_STATUS}", name="ck_receipts_status"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_receipts_venue_id"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], name="fk_receipts_purchase_order_id"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], name="fk_receipts_invoice_id"),
        sa.ForeignKeyConstraint(["received_by_user_id"], ["users.id"], name="fk_receipts_received_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_receipts_venue_id", "receipts", ["venue_id"])
    op.create_index("ix_receipts_purchase_order_id", "receipts", ["purchase_order_id"])
    op.create_index("ix_receipts_invoice_id", "receipts", ["invoice_id"])

    op.create_table(
        "receipt_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("po_line_id", sa.Uuid(), nullable=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("ordered_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("invoiced_qty", sa.Numeric(12, 2), nullable=True),
        sa.Column("counted_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("ordered_unit_cost_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("invoiced_unit_cost_cents", sa.Integer(), nullable=True),
        sa.Column("ordered_vintage", sa.String(32), nullable=True),
        sa.Column("received_vintage", sa.String(32), nullable=True),
        sa.Column("bin_id", sa.Uuid(), nullable=True),
        sa.Column("flags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_receipt_lines_venue_id"),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], name="fk_receipt_lines_receipt_id"),
        sa.ForeignKeyConstraint(["po_line_id"], ["po_lines.id"], name="fk_receipt_lines_po_line_id"),
        sa.ForeignKeyConstraint(["bin_id"], ["bins.id"], name="fk_receipt_lines_bin_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_receipt_lines_venue_id", "receipt_lines", ["venue_id"])
    op.create_index("ix_receipt_lines_receipt_id", "receipt_lines", ["receipt_id"])
    op.create_index("ix_receipt_lines_po_line_id", "receipt_lines", ["po_line_id"])
    op.create_index("ix_receipt_lines_sku", "receipt_lines", ["sku"])
    op.create_index("ix_receipt_lines_bin_id", "receipt_lines", ["bin_id"])

    _enable_rls("invoices")
    _enable_rls("receipts")
    _enable_rls("receipt_lines")


def downgrade() -> None:
    _disable_rls("receipt_lines")
    _disable_rls("receipts")
    _disable_rls("invoices")

    op.drop_index("ix_receipt_lines_bin_id", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_sku", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_po_line_id", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_receipt_id", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_venue_id", table_name="receipt_lines")
    op.drop_table("receipt_lines")

    op.drop_index("ix_receipts_invoice_id", table_name="receipts")
    op.drop_index("ix_receipts_purchase_order_id", table_name="receipts")
    op.drop_index("ix_receipts_venue_id", table_name="receipts")
    op.drop_table("receipts")

    op.drop_index("ix_invoices_document_id", table_name="invoices")
    op.drop_index("ix_invoices_invoice_number", table_name="invoices")
    op.drop_index("ix_invoices_purchase_order_id", table_name="invoices")
    op.drop_index("ix_invoices_supplier_id", table_name="invoices")
    op.drop_index("ix_invoices_venue_id", table_name="invoices")
    op.drop_table("invoices")
