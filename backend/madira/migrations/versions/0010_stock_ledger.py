"""Append-only stock ledger, locations, and bins.

``stock_movements`` is insert-only. A correction is a new row, and database
triggers reject updates and deletes. ``inventory_items.on_hand`` stays as a
cache of the movement sum. ``depletion_30d`` is no longer stored; readers
derive it from the ledger.

Upgraded databases get a ``Main Cellar`` location per venue that already has
stock, plus an ``opening_balance`` (or a signed ``count_adjustment`` when the
old on-hand was negative) so the movement sum matches ``on_hand``. Row level
security is applied after that backfill. The migration role would otherwise
be blocked by FORCE RLS, the same way ``0009_audit_and_vault`` scopes a table
once its rows exist.

Revision ID: 0010_stock_ledger
Revises: 0009_audit_and_vault
Create Date: 2026-11-24

"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_stock_ledger"
down_revision: Union[str, Sequence[str], None] = "0009_audit_and_vault"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KINDS = "('cellar', 'bar', 'walk_in', 'storage', 'other')"
_TYPES = (
    "('opening_balance', 'receive', 'sale', 'count_adjustment', 'breakage', "
    "'comp', 'transfer_in', 'transfer_out', 'return', 'faulty_bottle')"
)
_CENT = Decimal("0.01")


def _bind():
    return op.get_bind()


def _is_postgres() -> bool:
    return _bind().dialect.name == "postgresql"


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


def _qty(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def _create_tables() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"kind IN {_KINDS}", name="ck_locations_kind"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_locations_venue_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "name", name="uq_locations_venue_name"),
    )
    op.create_index("ix_locations_venue_id", "locations", ["venue_id"])
    op.create_table(
        "bins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("label", sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column("qr_payload", sa.String(240), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_bins_venue_id"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], name="fk_bins_location_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "code", name="uq_bins_venue_code"),
    )
    op.create_index("ix_bins_venue_id", "bins", ["venue_id"])
    op.create_index("ix_bins_location_id", "bins", ["location_id"])
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("bin_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("movement_type", sa.String(32), nullable=False),
        sa.Column("unit_cost_cents", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(80), nullable=True),
        sa.Column("source_id", sa.String(80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"movement_type IN {_TYPES}", name="ck_stock_movements_type"),
        sa.CheckConstraint("quantity <> 0", name="ck_stock_movements_quantity"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_stock_movements_venue_id"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], name="fk_stock_movements_sku_id"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], name="fk_stock_movements_location_id"),
        sa.ForeignKeyConstraint(["bin_id"], ["bins.id"], name="fk_stock_movements_bin_id"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_stock_movements_actor_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_movements_venue_id", "stock_movements", ["venue_id"])
    op.create_index("ix_stock_movements_sku_id", "stock_movements", ["sku_id"])
    op.create_index("ix_stock_movements_location_id", "stock_movements", ["location_id"])
    op.create_index("ix_stock_movements_bin_id", "stock_movements", ["bin_id"])
    op.create_index("ix_stock_movements_actor_user_id", "stock_movements", ["actor_user_id"])
    op.create_index("ix_stock_movements_created_at", "stock_movements", ["created_at"])
    op.create_index("ix_stock_movements_venue_created", "stock_movements", ["venue_id", "created_at"])
    op.create_index(
        "ix_stock_movements_venue_sku_created",
        "stock_movements",
        ["venue_id", "sku_id", "created_at"],
    )


def _triggers() -> None:
    if _is_postgres():
        op.execute(
            """
            CREATE OR REPLACE FUNCTION stock_movements_append_only()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'stock_movements is append-only';
            END;
            $$;
            """
        )
        op.execute(
            """
            CREATE TRIGGER stock_movements_append_only
            BEFORE UPDATE OR DELETE ON stock_movements
            FOR EACH ROW
            EXECUTE PROCEDURE stock_movements_append_only();
            """
        )
        return
    op.execute(
        """
        CREATE TRIGGER stock_movements_append_only_update
        BEFORE UPDATE ON stock_movements
        BEGIN
            SELECT RAISE(ABORT, 'stock_movements is append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER stock_movements_append_only_delete
        BEFORE DELETE ON stock_movements
        BEGIN
            SELECT RAISE(ABORT, 'stock_movements is append-only');
        END
        """
    )


def _drop_triggers() -> None:
    if _is_postgres():
        op.execute("DROP TRIGGER IF EXISTS stock_movements_append_only ON stock_movements")
        op.execute("DROP FUNCTION IF EXISTS stock_movements_append_only()")
        return
    op.execute("DROP TRIGGER IF EXISTS stock_movements_append_only_update")
    op.execute("DROP TRIGGER IF EXISTS stock_movements_append_only_delete")


def _read_stock() -> list[dict]:
    rows = _bind().execute(sa.text("SELECT id, venue_id, sku_id, on_hand FROM inventory_items")).mappings()
    return [dict(row) for row in rows]


def _backfill(rows: list[dict]) -> None:
    """One Main Cellar and one opening row per non-zero on-hand SKU."""

    by_venue: dict[uuid.UUID, list[dict]] = {}
    for row in rows:
        if row.get("sku_id") is None:
            continue
        by_venue.setdefault(_uuid(row["venue_id"]), []).append(row)
    if not by_venue:
        return
    opened = datetime.now(timezone.utc) - timedelta(days=40)
    locations = sa.table(
        "locations",
        sa.column("id", sa.Uuid()),
        sa.column("venue_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("kind", sa.String()),
        sa.column("notes", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    movements = sa.table(
        "stock_movements",
        sa.column("id", sa.Uuid()),
        sa.column("venue_id", sa.Uuid()),
        sa.column("sku_id", sa.Uuid()),
        sa.column("location_id", sa.Uuid()),
        sa.column("bin_id", sa.Uuid()),
        sa.column("quantity", sa.Numeric(12, 2)),
        sa.column("movement_type", sa.String()),
        sa.column("unit_cost_cents", sa.Integer()),
        sa.column("source_type", sa.String()),
        sa.column("source_id", sa.String()),
        sa.column("reason", sa.Text()),
        sa.column("actor_user_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    bind = _bind()
    for venue_id, items in by_venue.items():
        needed = [item for item in items if _qty(item["on_hand"]) != 0]
        if not needed:
            continue
        location_id = uuid.uuid4()
        bind.execute(
            locations.insert(),
            {
                "id": location_id,
                "venue_id": venue_id,
                "name": "Main Cellar",
                "kind": "cellar",
                "notes": "",
                "created_at": opened,
            },
        )
        payload = []
        for item in needed:
            quantity = _qty(item["on_hand"])
            payload.append(
                {
                    "id": uuid.uuid4(),
                    "venue_id": venue_id,
                    "sku_id": _uuid(item["sku_id"]),
                    "location_id": location_id,
                    "bin_id": None,
                    "quantity": quantity,
                    "movement_type": "opening_balance" if quantity > 0 else "count_adjustment",
                    "unit_cost_cents": None,
                    "source_type": "migration",
                    "source_id": str(_uuid(item["id"])),
                    "reason": "Opening balance backfill from inventory_items.on_hand",
                    "actor_user_id": None,
                    "created_at": opened,
                }
            )
        bind.execute(movements.insert(), payload)


def _retarget_inventory() -> None:
    """Cache on-hand as Numeric(12, 2) and drop the stored depletion constant."""

    if _is_postgres():
        op.alter_column(
            "inventory_items",
            "on_hand",
            existing_type=sa.Integer(),
            type_=sa.Numeric(12, 2),
            existing_nullable=False,
            postgresql_using="on_hand::numeric(12,2)",
        )
        op.drop_column("inventory_items", "depletion_30d")
        return
    with op.batch_alter_table("inventory_items") as batch:
        batch.alter_column(
            "on_hand",
            existing_type=sa.Integer(),
            type_=sa.Numeric(12, 2),
            existing_nullable=False,
        )
        batch.drop_column("depletion_30d")


def _restore_inventory() -> None:
    bind = _bind()
    if bind.dialect.name == "sqlite":
        bind.execute(sa.text("UPDATE inventory_items SET on_hand = CAST(ROUND(on_hand) AS INTEGER)"))
    else:
        bind.execute(sa.text("UPDATE inventory_items SET on_hand = CAST(ROUND(on_hand) AS INTEGER)"))
    column = sa.Column("depletion_30d", sa.Integer(), nullable=False, server_default=sa.text("0"))
    if _is_postgres():
        op.add_column("inventory_items", column)
        op.alter_column(
            "inventory_items",
            "on_hand",
            existing_type=sa.Numeric(12, 2),
            type_=sa.Integer(),
            existing_nullable=False,
            postgresql_using="CAST(ROUND(on_hand) AS INTEGER)",
        )
        return
    with op.batch_alter_table("inventory_items") as batch:
        batch.add_column(column)
        batch.alter_column(
            "on_hand",
            existing_type=sa.Numeric(12, 2),
            type_=sa.Integer(),
            existing_nullable=False,
        )


def _drop_tables() -> None:
    op.drop_index("ix_stock_movements_venue_sku_created", table_name="stock_movements")
    op.drop_index("ix_stock_movements_venue_created", table_name="stock_movements")
    op.drop_index("ix_stock_movements_created_at", table_name="stock_movements")
    op.drop_index("ix_stock_movements_actor_user_id", table_name="stock_movements")
    op.drop_index("ix_stock_movements_bin_id", table_name="stock_movements")
    op.drop_index("ix_stock_movements_location_id", table_name="stock_movements")
    op.drop_index("ix_stock_movements_sku_id", table_name="stock_movements")
    op.drop_index("ix_stock_movements_venue_id", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("ix_bins_location_id", table_name="bins")
    op.drop_index("ix_bins_venue_id", table_name="bins")
    op.drop_table("bins")
    op.drop_index("ix_locations_venue_id", table_name="locations")
    op.drop_table("locations")


def upgrade() -> None:
    # Read the integer on-hand before the column type changes.
    existing = _read_stock()
    _create_tables()
    _triggers()
    _backfill(existing)
    _retarget_inventory()
    _enable_rls("locations")
    _enable_rls("bins")
    _enable_rls("stock_movements")


def downgrade() -> None:
    _disable_rls("stock_movements")
    _disable_rls("bins")
    _disable_rls("locations")
    _drop_triggers()
    _drop_tables()
    _restore_inventory()
