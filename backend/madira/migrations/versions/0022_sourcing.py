"""Sourcing briefs, want items, and rep follow-up drafts.

Sample decisions gain links to the draft purchase order line and the draft
list version they produced. Postgres gets row level security on the three new
venue-scoped tables, matching ``0014``. SQLite skips those statements.

Revision ID: 0022_sourcing
Revises: 0021_tasting_sessions
Create Date: 2026-11-25

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022_sourcing"
down_revision: Union[str, Sequence[str], None] = "0021_tasting_sessions"
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
    # SQLite cannot ALTER a foreign key in place. Batch mode copies the table
    # there and emits ordinary ALTER statements on Postgres.
    with op.batch_alter_table("samples") as batch:
        batch.add_column(sa.Column("pass_reason", sa.Text(), nullable=False, server_default=sa.text("''")))
        batch.add_column(sa.Column("purchase_order_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("po_line_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("list_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("list_version_id", sa.Uuid(), nullable=True))
        batch.create_index("ix_samples_purchase_order_id", ["purchase_order_id"])
        batch.create_index("ix_samples_po_line_id", ["po_line_id"])
        batch.create_index("ix_samples_list_id", ["list_id"])
        batch.create_index("ix_samples_list_version_id", ["list_version_id"])
        batch.create_foreign_key("fk_samples_purchase_order_id", "purchase_orders", ["purchase_order_id"], ["id"])
        batch.create_foreign_key("fk_samples_po_line_id", "po_lines", ["po_line_id"], ["id"])
        batch.create_foreign_key("fk_samples_list_id", "beverage_lists", ["list_id"], ["id"])
        batch.create_foreign_key("fk_samples_list_version_id", "list_versions", ["list_version_id"], ["id"])

    op.create_table(
        "sourcing_briefs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("list_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'closed')", name="ck_sourcing_briefs_status"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["list_id"], ["beverage_lists.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sourcing_briefs_venue_id", "sourcing_briefs", ["venue_id"])
    op.create_index("ix_sourcing_briefs_list_id", "sourcing_briefs", ["list_id"])
    op.create_index("ix_sourcing_briefs_created_by_user_id", "sourcing_briefs", ["created_by_user_id"])

    op.create_table(
        "want_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("brief_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("style", sa.String(80), nullable=False),
        sa.Column("price_band", sa.String(16), nullable=False, server_default=sa.text("''")),
        sa.Column("quantity_hint", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("dishes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("sample_id", sa.Uuid(), nullable=True),
        sa.Column("offer_id", sa.Uuid(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity_hint >= 0", name="ck_want_items_quantity"),
        sa.CheckConstraint("position >= 0", name="ck_want_items_position"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["brief_id"], ["sourcing_briefs.id"]),
        sa.ForeignKeyConstraint(["sample_id"], ["samples.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["supplier_offers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_want_items_venue_id", "want_items", ["venue_id"])
    op.create_index("ix_want_items_brief_id", "want_items", ["brief_id"])
    op.create_index("ix_want_items_sample_id", "want_items", ["sample_id"])
    op.create_index("ix_want_items_offer_id", "want_items", ["offer_id"])
    op.create_index("ix_want_items_venue_brief", "want_items", ["venue_id", "brief_id"])

    op.create_table(
        "rep_followups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
        sa.Column("to_email", sa.String(320), nullable=False, server_default=sa.text("''")),
        sa.Column("subject", sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column("body", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["tasting_sessions.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_rep_followups_session"),
    )
    op.create_index("ix_rep_followups_venue_id", "rep_followups", ["venue_id"])
    op.create_index("ix_rep_followups_session_id", "rep_followups", ["session_id"])
    op.create_index("ix_rep_followups_supplier_id", "rep_followups", ["supplier_id"])
    op.create_index("ix_rep_followups_purchase_order_id", "rep_followups", ["purchase_order_id"])
    op.create_index("ix_rep_followups_created_by_user_id", "rep_followups", ["created_by_user_id"])

    _enable_rls("sourcing_briefs")
    _enable_rls("want_items")
    _enable_rls("rep_followups")


def downgrade() -> None:
    _disable_rls("rep_followups")
    _disable_rls("want_items")
    _disable_rls("sourcing_briefs")
    op.drop_index("ix_rep_followups_created_by_user_id", table_name="rep_followups")
    op.drop_index("ix_rep_followups_purchase_order_id", table_name="rep_followups")
    op.drop_index("ix_rep_followups_supplier_id", table_name="rep_followups")
    op.drop_index("ix_rep_followups_session_id", table_name="rep_followups")
    op.drop_index("ix_rep_followups_venue_id", table_name="rep_followups")
    op.drop_table("rep_followups")
    op.drop_index("ix_want_items_venue_brief", table_name="want_items")
    op.drop_index("ix_want_items_offer_id", table_name="want_items")
    op.drop_index("ix_want_items_sample_id", table_name="want_items")
    op.drop_index("ix_want_items_brief_id", table_name="want_items")
    op.drop_index("ix_want_items_venue_id", table_name="want_items")
    op.drop_table("want_items")
    op.drop_index("ix_sourcing_briefs_created_by_user_id", table_name="sourcing_briefs")
    op.drop_index("ix_sourcing_briefs_list_id", table_name="sourcing_briefs")
    op.drop_index("ix_sourcing_briefs_venue_id", table_name="sourcing_briefs")
    op.drop_table("sourcing_briefs")
    with op.batch_alter_table("samples") as batch:
        batch.drop_constraint("fk_samples_list_version_id", type_="foreignkey")
        batch.drop_constraint("fk_samples_list_id", type_="foreignkey")
        batch.drop_constraint("fk_samples_po_line_id", type_="foreignkey")
        batch.drop_constraint("fk_samples_purchase_order_id", type_="foreignkey")
        batch.drop_index("ix_samples_list_version_id")
        batch.drop_index("ix_samples_list_id")
        batch.drop_index("ix_samples_po_line_id")
        batch.drop_index("ix_samples_purchase_order_id")
        batch.drop_column("list_version_id")
        batch.drop_column("list_id")
        batch.drop_column("po_line_id")
        batch.drop_column("purchase_order_id")
        batch.drop_column("pass_reason")
