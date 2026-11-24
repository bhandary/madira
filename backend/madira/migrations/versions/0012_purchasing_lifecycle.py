"""Supplier contacts, purchase-order lifecycle, and owner approvals.

Existing ``suppliers``, ``purchase_orders``, and ``po_lines`` rows stay.
New columns have defaults so a draft created before this revision still
loads. ``po_id`` remains the purchase-order foreign key. ``supplier_contacts``
and ``approvals`` are new venue-scoped tables.

Postgres gets row level security on those new tables, matching
``0009_audit_and_vault``, ``0010_stock_ledger``, and ``0011_counts_and_par``.
SQLite skips those statements. The document vault accepts ``purchase_order``
in addition to the earlier types.

Revision ID: 0012_purchasing_lifecycle
Revises: 0011_counts_and_par
Create Date: 2026-11-24

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_purchasing_lifecycle"
down_revision: Union[str, Sequence[str], None] = "0011_counts_and_par"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PO_STATUS = "('draft', 'approved', 'sent', 'part_received', 'received', 'closed', 'canceled')"
_DECISION = "('pending', 'approved', 'rejected')"
_DOC_TYPES = "('invoice', 'po_pdf', 'purchase_order', 'delivery_note', 'license', 'certificate', 'other')"
_DOC_TYPES_PREVIOUS = "('invoice', 'po_pdf', 'delivery_note', 'license', 'certificate', 'other')"


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


def _add_fk(name: str, source: str, referent: str, local: list[str], remote: list[str]) -> None:
    # SQLite cannot add a foreign key without rebuilding a table other tables
    # already point at. Postgres enforces these. The columns exist on both.
    if not _is_postgres():
        return
    op.create_foreign_key(name, source, referent, local, remote)


def _drop_fk(name: str, table: str) -> None:
    if not _is_postgres():
        return
    op.drop_constraint(name, table, type_="foreignkey")


def _sqlite_foreign_keys(enabled: bool) -> None:
    if _is_postgres():
        return
    with op.get_context().autocommit_block():
        op.execute("PRAGMA foreign_keys=ON" if enabled else "PRAGMA foreign_keys=OFF")


def _create_unique(table: str, name: str, columns: list[str]) -> None:
    if _is_postgres():
        op.create_unique_constraint(name, table, columns)
        return
    _sqlite_foreign_keys(False)
    try:
        with op.batch_alter_table(table) as batch:
            batch.create_unique_constraint(name, columns)
    finally:
        _sqlite_foreign_keys(True)


def _drop_unique(table: str, name: str) -> None:
    if _is_postgres():
        op.drop_constraint(name, table, type_="unique")
        return
    _sqlite_foreign_keys(False)
    try:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="unique")
    finally:
        _sqlite_foreign_keys(True)


def _add_timestamp(table: str, column: str) -> None:
    # SQLite refuses ADD COLUMN when the default is CURRENT_TIMESTAMP and the
    # table already has rows. A constant default loads, then existing rows
    # are stamped. Postgres can use CURRENT_TIMESTAMP directly.
    if _is_postgres():
        default = sa.text("CURRENT_TIMESTAMP")
    else:
        default = sa.text("'2026-01-01 00:00:00'")
    op.add_column(
        table,
        sa.Column(column, sa.DateTime(timezone=True), server_default=default, nullable=False),
    )
    if not _is_postgres():
        op.execute(sa.text(f"UPDATE {table} SET {column} = CURRENT_TIMESTAMP"))


def _replace_doc_check(allowed: str) -> None:
    sql = f"doc_type IN {allowed}"
    if _is_postgres():
        op.drop_constraint("ck_documents_doc_type", "documents", type_="check")
        op.create_check_constraint("ck_documents_doc_type", "documents", sql)
        return
    _sqlite_foreign_keys(False)
    try:
        with op.batch_alter_table("documents") as batch:
            batch.drop_constraint("ck_documents_doc_type", type_="check")
            batch.create_check_constraint("ck_documents_doc_type", sql)
    finally:
        _sqlite_foreign_keys(True)


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("account_number", sa.String(80), nullable=True))
    op.add_column(
        "suppliers",
        sa.Column("order_minimum_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "suppliers",
        sa.Column("default_case_size", sa.Integer(), nullable=False, server_default=sa.text("12")),
    )
    op.add_column(
        "suppliers",
        sa.Column("delivery_days", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "suppliers",
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default=sa.text("7")),
    )
    op.add_column("suppliers", sa.Column("payment_terms", sa.String(80), nullable=True))
    _add_timestamp("suppliers", "created_at")
    _create_unique("suppliers", "uq_suppliers_venue_name", ["venue_id", "name"])

    op.create_table(
        "supplier_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(80), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_supplier_contacts_venue_id"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_supplier_contacts_supplier_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supplier_contacts_venue_id", "supplier_contacts", ["venue_id"])
    op.create_index("ix_supplier_contacts_supplier_id", "supplier_contacts", ["supplier_id"])

    op.add_column("purchase_orders", sa.Column("po_number", sa.String(32), nullable=True))
    op.add_column("purchase_orders", sa.Column("expected_delivery_date", sa.String(10), nullable=True))
    op.add_column(
        "purchase_orders",
        sa.Column("subtotal_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "purchase_orders",
        sa.Column("order_minimum_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "purchase_orders",
        sa.Column("minimum_met", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column("purchase_orders", sa.Column("pdf_document_id", sa.Uuid(), nullable=True))
    op.add_column("purchase_orders", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("purchase_orders", sa.Column("sent_via", sa.String(40), nullable=True))
    op.add_column("purchase_orders", sa.Column("delivery_adapter_ref", sa.String(120), nullable=True))
    op.add_column("purchase_orders", sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
    _add_timestamp("purchase_orders", "updated_at")
    _create_unique("purchase_orders", "uq_purchase_orders_venue_number", ["venue_id", "po_number"])
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    _add_fk(
        "fk_purchase_orders_pdf_document_id",
        "purchase_orders",
        "documents",
        ["pdf_document_id"],
        ["id"],
    )
    _add_fk(
        "fk_purchase_orders_created_by_user_id",
        "purchase_orders",
        "users",
        ["created_by_user_id"],
        ["id"],
    )
    if _is_postgres():
        op.create_check_constraint("ck_purchase_orders_status", "purchase_orders", f"status IN {_PO_STATUS}")

    op.add_column("po_lines", sa.Column("sku_id", sa.Uuid(), nullable=True))
    op.add_column("po_lines", sa.Column("product_name", sa.String(200), nullable=True))
    op.add_column("po_lines", sa.Column("case_size", sa.Integer(), nullable=False, server_default=sa.text("12")))
    op.add_column(
        "po_lines",
        sa.Column("cases_ordered", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "po_lines",
        sa.Column("quantity_ordered", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "po_lines",
        sa.Column("quantity_received", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "po_lines",
        sa.Column("unit_cost_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "po_lines",
        sa.Column("line_total_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("po_lines", sa.Column("vintage", sa.String(32), nullable=True))
    op.add_column("po_lines", sa.Column("notes", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE po_lines
        SET product_name = name,
            case_size = 1,
            cases_ordered = qty,
            quantity_ordered = qty,
            unit_cost_cents = unit_cost,
            line_total_cents = qty * unit_cost
        WHERE quantity_ordered = 0
        """
    )
    op.create_index("ix_po_lines_po_id", "po_lines", ["po_id"])
    op.create_index("ix_po_lines_sku", "po_lines", ["sku"])
    op.create_index("ix_po_lines_sku_id", "po_lines", ["sku_id"])
    _add_fk("fk_po_lines_sku_id", "po_lines", "skus", ["sku_id"], ["id"])

    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("required_role", sa.String(32), nullable=False, server_default=sa.text("'owner'")),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"decision IN {_DECISION}", name="ck_approvals_decision"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_approvals_venue_id"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], name="fk_approvals_decided_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_venue_id", "approvals", ["venue_id"])
    op.create_index("ix_approvals_entity_id", "approvals", ["entity_id"])
    op.create_index("ix_approvals_entity", "approvals", ["venue_id", "entity_type", "entity_id"])

    _enable_rls("supplier_contacts")
    _enable_rls("approvals")
    _replace_doc_check(_DOC_TYPES)


def downgrade() -> None:
    _replace_doc_check(_DOC_TYPES_PREVIOUS)
    _disable_rls("approvals")
    _disable_rls("supplier_contacts")

    op.drop_index("ix_approvals_entity", table_name="approvals")
    op.drop_index("ix_approvals_entity_id", table_name="approvals")
    op.drop_index("ix_approvals_venue_id", table_name="approvals")
    op.drop_table("approvals")

    _drop_fk("fk_po_lines_sku_id", "po_lines")
    op.drop_index("ix_po_lines_sku_id", table_name="po_lines")
    op.drop_index("ix_po_lines_sku", table_name="po_lines")
    op.drop_index("ix_po_lines_po_id", table_name="po_lines")
    for column in (
        "notes",
        "vintage",
        "line_total_cents",
        "unit_cost_cents",
        "quantity_received",
        "quantity_ordered",
        "cases_ordered",
        "case_size",
        "product_name",
        "sku_id",
    ):
        op.drop_column("po_lines", column)

    if _is_postgres():
        op.drop_constraint("ck_purchase_orders_status", "purchase_orders", type_="check")
    _drop_fk("fk_purchase_orders_created_by_user_id", "purchase_orders")
    _drop_fk("fk_purchase_orders_pdf_document_id", "purchase_orders")
    op.drop_index("ix_purchase_orders_supplier_id", table_name="purchase_orders")
    _drop_unique("purchase_orders", "uq_purchase_orders_venue_number")
    for column in (
        "updated_at",
        "created_by_user_id",
        "delivery_adapter_ref",
        "sent_via",
        "sent_at",
        "pdf_document_id",
        "minimum_met",
        "order_minimum_cents",
        "subtotal_cents",
        "expected_delivery_date",
        "po_number",
    ):
        op.drop_column("purchase_orders", column)

    op.drop_index("ix_supplier_contacts_supplier_id", table_name="supplier_contacts")
    op.drop_index("ix_supplier_contacts_venue_id", table_name="supplier_contacts")
    op.drop_table("supplier_contacts")

    _drop_unique("suppliers", "uq_suppliers_venue_name")
    for column in (
        "created_at",
        "payment_terms",
        "lead_time_days",
        "delivery_days",
        "default_case_size",
        "order_minimum_cents",
        "account_number",
    ):
        op.drop_column("suppliers", column)
