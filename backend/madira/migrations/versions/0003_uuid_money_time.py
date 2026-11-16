"""UUID primary keys, minor-unit money, and timezone-aware timestamps.

Existing integer ids are remapped to one uuid per row and that uuid is written
on every foreign key that pointed at it. Float prices, costs, and budgets
become minor units (half up) with currency USD. Tasting start/end strings and
naive timestamps become UTC datetimes. Postgres venue policies are recreated
so ``app.venue_id`` compares as uuid.

Revision ID: 0003_uuid_money_time
Revises: 0002_tenancy
Create Date: 2026-11-16

"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from madira.money import DEFAULT_CURRENCY, to_major, to_minor
from madira.timestamps import format_wall, parse_stamp

revision: str = "0003_uuid_money_time"
down_revision: Union[str, Sequence[str], None] = "0002_tenancy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Parents before children. Drop walks this list backwards.
CREATE_ORDER = (
    "organizations",
    "users",
    "venues",
    "memberships",
    "agent_runs",
    "beverage_lists",
    "lessons",
    "llm_credentials",
    "menus",
    "suppliers",
    "dishes",
    "inventory_items",
    "list_items",
    "purchase_orders",
    "quizzes",
    "tastings",
    "pairings",
    "po_lines",
    "quiz_attempts",
)

VENUE_TABLES = (
    "agent_runs",
    "beverage_lists",
    "lessons",
    "menus",
    "suppliers",
    "dishes",
    "inventory_items",
    "list_items",
    "purchase_orders",
    "quizzes",
    "tastings",
    "pairings",
    "po_lines",
    "quiz_attempts",
)

_JSON = {"agent_runs": ("delegated",), "quizzes": ("questions",), "quiz_attempts": ("answers",)}
_MONEY = {
    "dishes": ("price",),
    "pairings": ("glass_price", "bottle_price"),
    "beverage_lists": ("budget",),
    "list_items": ("cost", "pour_price", "bottle_price"),
    "inventory_items": ("unit_cost",),
    "po_lines": ("unit_cost",),
}
_STAMPS = {
    "agent_runs": ("created_at",),
    "beverage_lists": ("created_at",),
    "llm_credentials": ("updated_at",),
    "menus": ("created_at",),
    "purchase_orders": ("created_at",),
    "quiz_attempts": ("created_at",),
    "tastings": ("created_at",),
    "users": ("created_at", "last_login_at"),
}
_FKS = {
    "venues": {"organization_id": "organizations"},
    "memberships": {"user_id": "users", "venue_id": "venues"},
    "agent_runs": {"venue_id": "venues"},
    "beverage_lists": {"venue_id": "venues"},
    "lessons": {"venue_id": "venues"},
    "llm_credentials": {"organization_id": "organizations"},
    "menus": {"venue_id": "venues"},
    "suppliers": {"venue_id": "venues"},
    "dishes": {"venue_id": "venues", "menu_id": "menus"},
    "inventory_items": {"venue_id": "venues", "supplier_id": "suppliers"},
    "list_items": {"venue_id": "venues", "list_id": "beverage_lists"},
    "purchase_orders": {"venue_id": "venues", "supplier_id": "suppliers"},
    "quizzes": {"venue_id": "venues", "lesson_id": "lessons"},
    "tastings": {"venue_id": "venues", "supplier_id": "suppliers"},
    "pairings": {"venue_id": "venues", "dish_id": "dishes"},
    "po_lines": {"venue_id": "venues", "po_id": "purchase_orders"},
    "quiz_attempts": {"venue_id": "venues", "quiz_id": "quizzes"},
}


def _bind():
    return op.get_bind()


def _is_postgres() -> bool:
    return _bind().dialect.name == "postgresql"


def _rows(table: str) -> list[dict]:
    result = _bind().execute(sa.text(f"SELECT * FROM {table}"))
    return [dict(row) for row in result.mappings()]


def _json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _as_uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _read_all() -> dict[str, list[dict]]:
    return {table: _rows(table) for table in CREATE_ORDER}


def _assign(legacy: dict[str, list[dict]]) -> dict[str, dict]:
    maps: dict[str, dict] = {}
    for table, rows in legacy.items():
        maps[table] = {row["id"]: uuid.uuid4() for row in rows}
    return maps


def _assign_ints(current: dict[str, list[dict]]) -> dict[str, dict]:
    maps: dict[str, dict] = {}
    for table, rows in current.items():
        ordered = sorted(rows, key=lambda row: str(_as_uuid(row["id"])))
        maps[table] = {_as_uuid(row["id"]): index for index, row in enumerate(ordered, start=1)}
    return maps


def _ref(maps: dict[str, dict], table: str, old):
    if old is None:
        return None
    return maps[table][old if not isinstance(old, uuid.UUID) else old]


def _convert_forward(table: str, row: dict, maps: dict[str, dict]) -> dict:
    out = dict(row)
    out["id"] = maps[table][row["id"]]
    for column, parent in _FKS.get(table, {}).items():
        out[column] = _ref(maps, parent, row.get(column))
    for column in _MONEY.get(table, ()):
        out[column] = to_minor(0 if row.get(column) is None else row[column])
    if table in _MONEY:
        out["currency"] = DEFAULT_CURRENCY
    for column in _STAMPS.get(table, ()):
        out[column] = parse_stamp(row[column])
    if table == "tastings":
        out["starts_at"] = parse_stamp(row["starts_at"])
        out["ends_at"] = parse_stamp(row["ends_at"])
    for column in _JSON.get(table, ()):
        out[column] = _json_value(row.get(column))
    return out


def _naive(value) -> datetime:
    parsed = parse_stamp(value)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _convert_back(table: str, row: dict, maps: dict[str, dict]) -> dict:
    out = dict(row)
    out["id"] = maps[table][_as_uuid(row["id"])]
    for column, parent in _FKS.get(table, {}).items():
        old = row.get(column)
        out[column] = None if old is None else maps[parent][_as_uuid(old)]
    for column in _MONEY.get(table, ()):
        out[column] = to_major(0 if row.get(column) is None else row[column])
    out.pop("currency", None)
    for column in _STAMPS.get(table, ()):
        out[column] = _naive(row[column])
    if table == "tastings":
        out["starts_at"] = format_wall(parse_stamp(row["starts_at"]))
        out["ends_at"] = format_wall(parse_stamp(row["ends_at"]))
    for column in _JSON.get(table, ()):
        out[column] = _json_value(row.get(column))
    return out


def _col_type(table: str, name: str, uuid_keys: bool):
    if name == "id" or name in _FKS.get(table, {}):
        return sa.Uuid() if uuid_keys else sa.Integer()
    if name in _MONEY.get(table, ()):
        return sa.Integer() if uuid_keys else sa.Float()
    if name == "currency":
        return sa.String(3)
    if name in _JSON.get(table, ()):
        return sa.JSON()
    if table == "tastings" and name in {"starts_at", "ends_at"}:
        return sa.DateTime(timezone=True) if uuid_keys else sa.String(40)
    if name in _STAMPS.get(table, ()):
        return sa.DateTime(timezone=True) if uuid_keys else sa.DateTime()
    if name in {"target_margin", "margin_pct", "score"}:
        return sa.Float()
    if name in {"on_hand", "par", "depletion_30d", "qty"}:
        return sa.Integer()
    if name in {
        "message",
        "reply",
        "notes",
        "raw_text",
        "body",
        "description",
        "flavor_profile",
        "rationale",
        "ics",
        "ciphertext",
        "picture",
    }:
        return sa.Text()
    return sa.String()


def _insert(table: str, rows: list[dict]) -> None:
    if not rows:
        return
    uuid_keys = isinstance(rows[0]["id"], uuid.UUID)
    table_clause = sa.table(
        table,
        *[sa.column(name, _col_type(table, name, uuid_keys)) for name in rows[0]],
    )
    _bind().execute(table_clause.insert(), rows)


def _reset_sequences() -> None:
    if not _is_postgres():
        return
    for table in CREATE_ORDER:
        _bind().execute(
            sa.text(
                f"""
                DO $$
                DECLARE seq text;
                BEGIN
                    seq := pg_get_serial_sequence('{table}', 'id');
                    IF seq IS NOT NULL THEN
                        PERFORM setval(
                            seq,
                            GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1),
                            (SELECT MAX(id) IS NOT NULL FROM {table})
                        );
                    END IF;
                END $$;
                """
            )
        )


def _drop_policies() -> None:
    if not _is_postgres():
        return
    for table in VENUE_TABLES:
        op.execute(f"DROP POLICY IF EXISTS venue_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def _policies(cast: str) -> None:
    if not _is_postgres():
        return
    for table in VENUE_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS venue_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY venue_isolation ON {table}
            USING (venue_id = NULLIF(current_setting('app.venue_id', true), '')::{cast})
            WITH CHECK (venue_id = NULLIF(current_setting('app.venue_id', true), '')::{cast})
            """
        )


def _index(name: str, table: str, column: str) -> None:
    op.create_index(name, table, [column])


def _create_current() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("google_sub", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("picture", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("google_sub"),
    )
    op.create_table(
        "venues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_venues_organization_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_venues_org_slug"),
    )
    _index("ix_venues_organization_id", "venues", "organization_id")
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "role IN ('Owner', 'Sommelier', 'Manager', 'Staff', 'Auditor')",
            name="ck_memberships_role",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_memberships_user_id"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_memberships_venue_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "venue_id", name="uq_memberships_user_venue"),
    )
    _index("ix_memberships_user_id", "memberships", "user_id")
    _index("ix_memberships_venue_id", "memberships", "venue_id")
    _venue_table(
        "agent_runs",
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("reply", sa.Text(), nullable=False),
        sa.Column("delegated", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    _venue_table(
        "beverage_lists",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("budget", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'USD'"), nullable=False),
        sa.Column("target_margin", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    _venue_table(
        "lessons",
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        unique=(("venue_id", "slug"), "uq_lessons_venue_slug"),
    )
    op.create_table(
        "llm_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_last4", sa.String(8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_llm_credentials_organization_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_llm_credentials_organization_id", "llm_credentials", "organization_id")
    _venue_table(
        "menus",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("cuisine", sa.String(80), nullable=False),
        sa.Column("price_tier", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    _venue_table(
        "suppliers",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("contact_email", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
    )
    _venue_table(
        "dishes",
        sa.Column("menu_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("course", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("flavor_profile", sa.Text(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'USD'"), nullable=False),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"], name="fk_dishes_menu_id"),
    )
    _venue_table(
        "inventory_items",
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
        sa.Column("on_hand", sa.Integer(), nullable=False),
        sa.Column("par", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'USD'"), nullable=False),
        sa.Column("depletion_30d", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_inventory_items_supplier_id"),
        unique=(("venue_id", "sku"), "uq_inventory_items_venue_sku"),
    )
    _venue_table(
        "list_items",
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("producer", sa.String(200), nullable=False),
        sa.Column("region", sa.String(200), nullable=False),
        sa.Column("style", sa.String(200), nullable=False),
        sa.Column("vintage", sa.String(32), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False),
        sa.Column("pour_price", sa.Integer(), nullable=False),
        sa.Column("bottle_price", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'USD'"), nullable=False),
        sa.Column("margin_pct", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["list_id"], ["beverage_lists.id"], name="fk_list_items_list_id"),
    )
    _venue_table(
        "purchase_orders",
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_purchase_orders_supplier_id"),
    )
    _venue_table(
        "quizzes",
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], name="fk_quizzes_lesson_id"),
    )
    _venue_table(
        "tastings",
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("ics", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_tastings_supplier_id"),
    )
    _venue_table(
        "pairings",
        sa.Column("dish_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("producer", sa.String(200), nullable=False),
        sa.Column("region", sa.String(200), nullable=False),
        sa.Column("style", sa.String(200), nullable=False),
        sa.Column("vintage", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("price_tier", sa.String(32), nullable=False),
        sa.Column("glass_price", sa.Integer(), nullable=False),
        sa.Column("bottle_price", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'USD'"), nullable=False),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], name="fk_pairings_dish_id"),
    )
    _venue_table(
        "po_lines",
        sa.Column("po_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'USD'"), nullable=False),
        sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"], name="fk_po_lines_po_id"),
    )
    _venue_table(
        "quiz_attempts",
        sa.Column("quiz_id", sa.Uuid(), nullable=False),
        sa.Column("staff_name", sa.String(120), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], name="fk_quiz_attempts_quiz_id"),
    )


def _venue_table(name: str, *columns: sa.Column, unique: tuple | None = None) -> None:
    extras = []
    if unique is not None:
        cols, constraint = unique
        extras.append(sa.UniqueConstraint(*cols, name=constraint))
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        *columns,
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name=f"fk_{name}_venue_id"),
        sa.PrimaryKeyConstraint("id"),
        *extras,
    )
    _index(f"ix_{name}_venue_id", name, "venue_id")


def _create_legacy() -> None:
    """Schema as 0002 left it: integer keys, float money, string tasting times."""

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("google_sub", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("picture", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("google_sub"),
    )
    op.create_table(
        "venues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_venues_org_slug"),
    )
    _index("ix_venues_organization_id", "venues", "organization_id")
    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "role IN ('Owner', 'Sommelier', 'Manager', 'Staff', 'Auditor')",
            name="ck_memberships_role",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_memberships_venue_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "venue_id", name="uq_memberships_user_venue"),
    )
    _index("ix_memberships_user_id", "memberships", "user_id")
    _index("ix_memberships_venue_id", "memberships", "venue_id")
    _legacy_venue(
        "agent_runs",
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("reply", sa.Text(), nullable=False),
        sa.Column("delegated", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    _legacy_venue(
        "beverage_lists",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("budget", sa.Float(), nullable=False),
        sa.Column("target_margin", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    _legacy_venue(
        "lessons",
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        unique=(("venue_id", "slug"), "uq_lessons_venue_slug"),
    )
    op.create_table(
        "llm_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_last4", sa.String(8), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_llm_credentials_organization_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_llm_credentials_organization_id", "llm_credentials", "organization_id")
    _legacy_venue(
        "menus",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("cuisine", sa.String(80), nullable=False),
        sa.Column("price_tier", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    _legacy_venue(
        "suppliers",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("contact_email", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
    )
    _legacy_venue(
        "dishes",
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("course", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("flavor_profile", sa.Text(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"]),
    )
    _legacy_venue(
        "inventory_items",
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("on_hand", sa.Integer(), nullable=False),
        sa.Column("par", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Float(), nullable=False),
        sa.Column("depletion_30d", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        unique=(("venue_id", "sku"), "uq_inventory_items_venue_sku"),
    )
    _legacy_venue(
        "list_items",
        sa.Column("list_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("producer", sa.String(200), nullable=False),
        sa.Column("region", sa.String(200), nullable=False),
        sa.Column("style", sa.String(200), nullable=False),
        sa.Column("vintage", sa.String(32), nullable=False),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("pour_price", sa.Float(), nullable=False),
        sa.Column("bottle_price", sa.Float(), nullable=False),
        sa.Column("margin_pct", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["list_id"], ["beverage_lists.id"]),
    )
    _legacy_venue(
        "purchase_orders",
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
    )
    _legacy_venue(
        "quizzes",
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"]),
    )
    _legacy_venue(
        "tastings",
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("starts_at", sa.String(40), nullable=False),
        sa.Column("ends_at", sa.String(40), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("ics", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
    )
    _legacy_venue(
        "pairings",
        sa.Column("dish_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("producer", sa.String(200), nullable=False),
        sa.Column("region", sa.String(200), nullable=False),
        sa.Column("style", sa.String(200), nullable=False),
        sa.Column("vintage", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("price_tier", sa.String(32), nullable=False),
        sa.Column("glass_price", sa.Float(), nullable=False),
        sa.Column("bottle_price", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"]),
    )
    _legacy_venue(
        "po_lines",
        sa.Column("po_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"]),
    )
    _legacy_venue(
        "quiz_attempts",
        sa.Column("quiz_id", sa.Integer(), nullable=False),
        sa.Column("staff_name", sa.String(120), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"]),
    )


def _legacy_venue(name: str, *columns: sa.Column, unique: tuple | None = None) -> None:
    extras = []
    if unique is not None:
        cols, constraint = unique
        extras.append(sa.UniqueConstraint(*cols, name=constraint))
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), nullable=False),
        *columns,
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name=f"fk_{name}_venue_id"),
        sa.PrimaryKeyConstraint("id"),
        *extras,
    )
    _index(f"ix_{name}_venue_id", name, "venue_id")


def _drop_all() -> None:
    for table in reversed(CREATE_ORDER):
        op.drop_table(table)


def _rewrite(direction: str) -> None:
    current_or_legacy = _read_all()
    if direction == "forward":
        maps = _assign(current_or_legacy)
        convert = _convert_forward
        create = _create_current
        cast = "uuid"
    else:
        keyed = {
            table: [{**row, "id": _as_uuid(row["id"])} for row in rows]
            for table, rows in current_or_legacy.items()
        }
        for table, rows in keyed.items():
            for row in rows:
                for column in _FKS.get(table, {}):
                    if row.get(column) is not None:
                        row[column] = _as_uuid(row[column])
        maps = _assign_ints(keyed)
        current_or_legacy = keyed
        convert = _convert_back
        create = _create_legacy
        cast = "integer"
    _drop_policies()
    _drop_all()
    create()
    for table in CREATE_ORDER:
        _insert(table, [convert(table, row, maps) for row in current_or_legacy[table]])
    if direction == "back":
        _reset_sequences()
    _policies(cast)


def upgrade() -> None:
    _rewrite("forward")


def downgrade() -> None:
    _rewrite("back")
