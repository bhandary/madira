"""Pricing rules, list sections, and list-curation columns.

Pricing is a venue rule: a category and a cost band set the bottle multiple,
the glass multiple, and the rounding step. A list section is the named group
already written on list rows. Postgres gets row level security on the two new
venue-scoped tables, matching ``0014``. SQLite skips those statements.

Revision ID: 0015_list_pricing_coverage
Revises: 0014_storage_zones
Create Date: 2026-11-24

"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_list_pricing_coverage"
down_revision: Union[str, Sequence[str], None] = "0014_storage_zones"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CATEGORIES = "('wine', 'beer', 'spirits', 'sake', 'other', '*')"


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


def _uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _backfill_sections() -> None:
    """One section per distinct list item section string, then point the row at it."""

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT id, venue_id, list_id, section
            FROM list_items
            WHERE section IS NOT NULL AND section != ''
            ORDER BY list_id, position, id
            """
        )
    ).fetchall()
    sections = sa.table(
        "list_sections",
        sa.column("id", sa.Uuid()),
        sa.column("venue_id", sa.Uuid()),
        sa.column("list_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("position", sa.Integer()),
        sa.column("budget_share_pct", sa.Numeric()),
    )
    items = sa.table(
        "list_items",
        sa.column("id", sa.Uuid()),
        sa.column("section_id", sa.Uuid()),
    )
    seen: dict[tuple, uuid.UUID] = {}
    position: dict[uuid.UUID, int] = {}
    for row in rows:
        list_id = _uuid(row.list_id)
        name = str(row.section)
        key = (list_id, name)
        section_id = seen.get(key)
        if section_id is None:
            section_id = uuid.uuid4()
            seen[key] = section_id
            place = position.get(list_id, 0)
            position[list_id] = place + 1
            conn.execute(
                sections.insert().values(
                    id=section_id,
                    venue_id=_uuid(row.venue_id),
                    list_id=list_id,
                    name=name,
                    position=place,
                    budget_share_pct=None,
                )
            )
        conn.execute(items.update().where(items.c.id == _uuid(row.id)).values(section_id=section_id))


def upgrade() -> None:
    op.create_table(
        "pricing_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("cost_min_cents", sa.Integer(), nullable=False),
        sa.Column("cost_max_cents", sa.Integer(), nullable=True),
        sa.Column("bottle_multiple", sa.Numeric(6, 2), nullable=False),
        sa.Column("glass_pours_per_bottle", sa.Integer(), nullable=False),
        sa.Column("glass_multiple", sa.Numeric(6, 2), nullable=False),
        sa.Column("round_to_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint(f"category IN {_CATEGORIES}", name="ck_pricing_rules_category"),
        sa.CheckConstraint("cost_min_cents >= 0", name="ck_pricing_rules_cost_min"),
        sa.CheckConstraint(
            "cost_max_cents IS NULL OR cost_max_cents > cost_min_cents",
            name="ck_pricing_rules_cost_max",
        ),
        sa.CheckConstraint("bottle_multiple > 0", name="ck_pricing_rules_bottle_multiple"),
        sa.CheckConstraint("glass_pours_per_bottle >= 1", name="ck_pricing_rules_pours"),
        sa.CheckConstraint("glass_multiple > 0", name="ck_pricing_rules_glass_multiple"),
        sa.CheckConstraint("round_to_cents >= 1", name="ck_pricing_rules_round"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_pricing_rules_venue_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "category", "cost_min_cents", name="uq_pricing_rules_band"),
    )
    op.create_index("ix_pricing_rules_venue_id", "pricing_rules", ["venue_id"])

    op.create_table(
        "list_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("budget_share_pct", sa.Numeric(5, 2), nullable=True),
        sa.CheckConstraint(
            "budget_share_pct IS NULL OR (budget_share_pct >= 0 AND budget_share_pct <= 100)",
            name="ck_list_sections_share",
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_list_sections_venue_id"),
        sa.ForeignKeyConstraint(["list_id"], ["beverage_lists.id"], name="fk_list_sections_list_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("list_id", "name", name="uq_list_sections_list_name"),
    )
    op.create_index("ix_list_sections_venue_id", "list_sections", ["venue_id"])
    op.create_index("ix_list_sections_list_id", "list_sections", ["list_id"])

    with op.batch_alter_table("list_items") as batch:
        batch.add_column(sa.Column("section_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_list_items_section_id",
            "list_sections",
            ["section_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_list_items_section_id", ["section_id"])

    _backfill_sections()

    op.add_column(
        "beverage_lists",
        sa.Column("target_beverage_cost_pct", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "beverage_lists",
        sa.Column("concept", sa.String(400), nullable=False, server_default=sa.text("''")),
    )
    op.add_column(
        "beverage_lists",
        sa.Column("price_tier", sa.String(32), nullable=False, server_default=sa.text("''")),
    )
    op.add_column("storage_zones", sa.Column("capacity_bottles", sa.Integer(), nullable=True))
    op.add_column("product_variants", sa.Column("drink_from_year", sa.Integer(), nullable=True))
    op.add_column("product_variants", sa.Column("drink_by_year", sa.Integer(), nullable=True))
    op.add_column("skus", sa.Column("best_by", sa.Date(), nullable=True))

    _enable_rls("pricing_rules")
    _enable_rls("list_sections")


def downgrade() -> None:
    _disable_rls("list_sections")
    _disable_rls("pricing_rules")

    op.drop_column("skus", "best_by")
    op.drop_column("product_variants", "drink_by_year")
    op.drop_column("product_variants", "drink_from_year")
    op.drop_column("storage_zones", "capacity_bottles")
    op.drop_column("beverage_lists", "price_tier")
    op.drop_column("beverage_lists", "concept")
    op.drop_column("beverage_lists", "target_beverage_cost_pct")

    with op.batch_alter_table("list_items") as batch:
        batch.drop_index("ix_list_items_section_id")
        batch.drop_constraint("fk_list_items_section_id", type_="foreignkey")
        batch.drop_column("section_id")

    op.drop_index("ix_list_sections_list_id", table_name="list_sections")
    op.drop_index("ix_list_sections_venue_id", table_name="list_sections")
    op.drop_table("list_sections")

    op.drop_index("ix_pricing_rules_venue_id", table_name="pricing_rules")
    op.drop_table("pricing_rules")
