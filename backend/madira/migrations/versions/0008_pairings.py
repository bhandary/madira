"""Stock-grounded pairing slots and sommelier preferences.

Each pairing gains a slot, a status, a server script, a confidence, and a gap
line. A gap has no SKU. Pins, swaps, and rejections live on pairing_preferences
so a later menu version can honor them. Existing rows stay suggested bottles
with an empty slot until the next pairing run.

Revision ID: 0008_pairings
Revises: 0007_menu_versions
Create Date: 2026-11-17

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_pairings"
down_revision: Union[str, Sequence[str], None] = "0007_menu_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECKS = (
    ("ck_pairings_slot", "slot IN ('best_by_the_glass', 'best_bottle', 'value', 'adventurous', '')"),
    ("ck_pairings_status", "status IN ('suggested', 'pinned', 'swapped', 'rejected', 'gap')"),
    ("ck_pairings_confidence", "confidence IN ('high', 'medium', 'low', '')"),
    (
        "ck_pairings_gap_sku",
        "(status = 'gap' AND sku_id IS NULL) OR (status <> 'gap' AND sku_id IS NOT NULL)",
    ),
)


def _bind():
    return op.get_bind()


def _is_postgres() -> bool:
    return _bind().dialect.name == "postgresql"


def _enable_rls() -> None:
    if not _is_postgres():
        return
    op.execute("ALTER TABLE pairing_preferences ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pairing_preferences FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS venue_isolation ON pairing_preferences")
    op.execute(
        """
        CREATE POLICY venue_isolation ON pairing_preferences
        USING (venue_id = NULLIF(current_setting('app.venue_id', true), '')::uuid)
        WITH CHECK (venue_id = NULLIF(current_setting('app.venue_id', true), '')::uuid)
        """
    )


def _disable_rls() -> None:
    if not _is_postgres():
        return
    op.execute("DROP POLICY IF EXISTS venue_isolation ON pairing_preferences")
    op.execute("ALTER TABLE pairing_preferences NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pairing_preferences DISABLE ROW LEVEL SECURITY")


def _sqlite_foreign_keys(enabled: bool) -> None:
    with op.get_context().autocommit_block():
        op.execute("PRAGMA foreign_keys=ON" if enabled else "PRAGMA foreign_keys=OFF")


def _add_pairing_columns() -> None:
    columns = [
        sa.Column("slot", sa.String(32), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="suggested"),
        sa.Column("server_script", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.String(16), nullable=False, server_default=""),
        sa.Column("gap", sa.Text(), nullable=False, server_default=""),
    ]
    for column in columns:
        op.add_column("pairings", column)


def _seal_pairings() -> None:
    if _is_postgres():
        op.alter_column("pairings", "sku_id", existing_type=sa.Uuid(), nullable=True)
        for name, expr in _CHECKS:
            op.create_check_constraint(name, "pairings", expr)
        return
    _sqlite_foreign_keys(False)
    try:
        with op.batch_alter_table("pairings") as batch:
            batch.alter_column("sku_id", existing_type=sa.Uuid(), nullable=True)
            for name, expr in _CHECKS:
                batch.create_check_constraint(name, expr)
    finally:
        _sqlite_foreign_keys(True)


def _unseal_pairings() -> None:
    if _is_postgres():
        for name, _expr in _CHECKS:
            op.drop_constraint(name, "pairings", type_="check")
        op.alter_column("pairings", "sku_id", existing_type=sa.Uuid(), nullable=False)
        return
    _sqlite_foreign_keys(False)
    try:
        with op.batch_alter_table("pairings") as batch:
            for name, _expr in _CHECKS:
                batch.drop_constraint(name, type_="check")
            batch.alter_column("sku_id", existing_type=sa.Uuid(), nullable=False)
    finally:
        _sqlite_foreign_keys(True)


def upgrade() -> None:
    _add_pairing_columns()
    _seal_pairings()
    op.create_index(
        "uq_pairings_dish_slot",
        "pairings",
        ["dish_id", "slot"],
        unique=True,
        sqlite_where=sa.text("slot != ''"),
        postgresql_where=sa.text("slot <> ''"),
    )
    op.create_table(
        "pairing_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("dish_stable_id", sa.Uuid(), nullable=False),
        sa.Column("slot", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('pin', 'swap', 'reject')", name="ck_pairing_preferences_kind"),
        sa.CheckConstraint(
            "slot IN ('best_by_the_glass', 'best_bottle', 'value', 'adventurous', '')",
            name="ck_pairing_preferences_slot",
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_pairing_preferences_venue_id"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_pairing_preferences_sku_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pairing_preferences_venue_id", "pairing_preferences", ["venue_id"])
    op.create_index("ix_pairing_preferences_dish_stable_id", "pairing_preferences", ["dish_stable_id"])
    op.create_index("ix_pairing_preferences_sku_id", "pairing_preferences", ["sku_id"])
    op.create_index("ix_pairing_preferences_venue_dish", "pairing_preferences", ["venue_id", "dish_stable_id"])
    op.create_index(
        "uq_pairing_preferences_choice",
        "pairing_preferences",
        ["venue_id", "dish_stable_id", "slot"],
        unique=True,
        sqlite_where=sa.text("kind != 'reject'"),
        postgresql_where=sa.text("kind <> 'reject'"),
    )
    op.create_index(
        "uq_pairing_preferences_reject",
        "pairing_preferences",
        ["venue_id", "dish_stable_id", "sku_id"],
        unique=True,
        sqlite_where=sa.text("kind = 'reject'"),
        postgresql_where=sa.text("kind = 'reject'"),
    )
    _enable_rls()


def downgrade() -> None:
    _disable_rls()
    op.drop_index("uq_pairing_preferences_reject", table_name="pairing_preferences")
    op.drop_index("uq_pairing_preferences_choice", table_name="pairing_preferences")
    op.drop_index("ix_pairing_preferences_venue_dish", table_name="pairing_preferences")
    op.drop_index("ix_pairing_preferences_sku_id", table_name="pairing_preferences")
    op.drop_index("ix_pairing_preferences_dish_stable_id", table_name="pairing_preferences")
    op.drop_index("ix_pairing_preferences_venue_id", table_name="pairing_preferences")
    op.drop_table("pairing_preferences")
    op.drop_index("uq_pairings_dish_slot", table_name="pairings")
    _unseal_pairings()
    for name in ("gap", "confidence", "server_script", "status", "slot"):
        op.drop_column("pairings", name)
