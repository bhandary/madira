"""Menu versions and structured dishes.

Each existing menu becomes version 1. Its dishes point at that version, keep
their id as the stable identity, and are not marked for re-pairing. A later
upload adds a version and copies that identity when the dish is unchanged.

Revision ID: 0007_menu_versions
Revises: 0006_tasting_notes
Create Date: 2026-11-17

"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from madira.domain.menu.schemas import content_hash

revision: str = "0007_menu_versions"
down_revision: Union[str, Sequence[str], None] = "0006_tasting_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONFIDENCE = {
    "name": 1.0,
    "course": 1.0,
    "price": 1.0,
    "main_component": 1.0,
    "cooking_method": 1.0,
    "sauce": 1.0,
    "richness": 1.0,
    "acidity": 1.0,
    "sweetness": 1.0,
    "spice": 1.0,
    "umami": 1.0,
    "allergens": 1.0,
}


def _bind():
    return op.get_bind()


def _is_postgres() -> bool:
    return _bind().dialect.name == "postgresql"


def _enable_rls() -> None:
    if not _is_postgres():
        return
    op.execute("ALTER TABLE menu_versions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE menu_versions FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS venue_isolation ON menu_versions")
    op.execute(
        """
        CREATE POLICY venue_isolation ON menu_versions
        USING (venue_id = NULLIF(current_setting('app.venue_id', true), '')::uuid)
        WITH CHECK (venue_id = NULLIF(current_setting('app.venue_id', true), '')::uuid)
        """
    )


def _disable_rls() -> None:
    if not _is_postgres():
        return
    op.execute("DROP POLICY IF EXISTS venue_isolation ON menu_versions")
    op.execute("ALTER TABLE menu_versions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE menu_versions DISABLE ROW LEVEL SECURITY")


def _add_dish_columns() -> None:
    columns = [
        sa.Column("main_component", sa.String(200), nullable=False, server_default=""),
        sa.Column("cooking_method", sa.String(200), nullable=False, server_default=""),
        sa.Column("sauce", sa.String(200), nullable=False, server_default=""),
        sa.Column("richness", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("acidity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sweetness", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spice", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("umami", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allergens", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("confidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("needs_repairing", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("menu_version_id", sa.Uuid(), nullable=True),
        sa.Column("stable_id", sa.Uuid(), nullable=True),
    ]
    for column in columns:
        op.add_column("dishes", column)


def _sqlite_foreign_keys(enabled: bool) -> None:
    """SQLite ignores this pragma inside a transaction, so it runs on its own."""

    with op.get_context().autocommit_block():
        op.execute("PRAGMA foreign_keys=ON" if enabled else "PRAGMA foreign_keys=OFF")


def _seal_dish_columns() -> None:
    if _is_postgres():
        op.alter_column("dishes", "menu_version_id", existing_type=sa.Uuid(), nullable=False)
        op.alter_column("dishes", "stable_id", existing_type=sa.Uuid(), nullable=False)
        op.create_foreign_key("fk_dishes_menu_version_id", "dishes", "menu_versions", ["menu_version_id"], ["id"])
        op.create_index("ix_dishes_menu_version_id", "dishes", ["menu_version_id"])
        op.create_index("ix_dishes_version_position", "dishes", ["menu_version_id", "position"])
        op.create_unique_constraint("uq_dishes_version_stable", "dishes", ["menu_version_id", "stable_id"])
        for name, expr in _checks():
            op.create_check_constraint(name, "dishes", expr)
        return
    _sqlite_foreign_keys(False)
    try:
        with op.batch_alter_table("dishes") as batch:
            batch.alter_column("menu_version_id", existing_type=sa.Uuid(), nullable=False)
            batch.alter_column("stable_id", existing_type=sa.Uuid(), nullable=False)
            batch.create_foreign_key("fk_dishes_menu_version_id", "menu_versions", ["menu_version_id"], ["id"])
            batch.create_index("ix_dishes_menu_version_id", ["menu_version_id"])
            batch.create_index("ix_dishes_version_position", ["menu_version_id", "position"])
            batch.create_unique_constraint("uq_dishes_version_stable", ["menu_version_id", "stable_id"])
            for name, expr in _checks():
                batch.create_check_constraint(name, expr)
    finally:
        _sqlite_foreign_keys(True)


def _checks() -> tuple[tuple[str, str], ...]:
    return (
        ("ck_dishes_position", "position >= 0"),
        ("ck_dishes_richness", "richness >= 0 AND richness <= 5"),
        ("ck_dishes_acidity", "acidity >= 0 AND acidity <= 5"),
        ("ck_dishes_sweetness", "sweetness >= 0 AND sweetness <= 5"),
        ("ck_dishes_spice", "spice >= 0 AND spice <= 5"),
        ("ck_dishes_umami", "umami >= 0 AND umami <= 5"),
    )


def _drop_dish_columns() -> None:
    if _is_postgres():
        for name, _expr in _checks():
            op.drop_constraint(name, "dishes", type_="check")
        op.drop_constraint("uq_dishes_version_stable", "dishes", type_="unique")
        op.drop_index("ix_dishes_version_position", table_name="dishes")
        op.drop_index("ix_dishes_menu_version_id", table_name="dishes")
        op.drop_constraint("fk_dishes_menu_version_id", "dishes", type_="foreignkey")
    else:
        _sqlite_foreign_keys(False)
        try:
            with op.batch_alter_table("dishes") as batch:
                for name, _expr in _checks():
                    batch.drop_constraint(name, type_="check")
                batch.drop_constraint("uq_dishes_version_stable", type_="unique")
                batch.drop_index("ix_dishes_version_position")
                batch.drop_index("ix_dishes_menu_version_id")
                batch.drop_constraint("fk_dishes_menu_version_id", type_="foreignkey")
        finally:
            _sqlite_foreign_keys(True)
    for name in (
        "stable_id",
        "menu_version_id",
        "position",
        "needs_repairing",
        "content_hash",
        "confidence",
        "allergens",
        "umami",
        "spice",
        "sweetness",
        "acidity",
        "richness",
        "sauce",
        "cooking_method",
        "main_component",
    ):
        op.drop_column("dishes", name)


def _uuid(value):
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _backfill() -> None:
    bind = _bind()
    menus = bind.execute(sa.text("SELECT id, venue_id, raw_text FROM menus")).fetchall()
    user_id = _uuid(bind.execute(sa.text("SELECT id FROM users LIMIT 1")).scalar())
    now = datetime.now(timezone.utc)
    versions = sa.table(
        "menu_versions",
        sa.column("id", sa.Uuid()),
        sa.column("venue_id", sa.Uuid()),
        sa.column("menu_id", sa.Uuid()),
        sa.column("number", sa.Integer()),
        sa.column("source_type", sa.String()),
        sa.column("source_key", sa.String()),
        sa.column("source_filename", sa.String()),
        sa.column("source_url", sa.String()),
        sa.column("raw_text", sa.Text()),
        sa.column("status", sa.String()),
        sa.column("confirmed_by", sa.Uuid()),
        sa.column("confirmed_at", sa.DateTime(timezone=True)),
    )
    for menu_id, venue_id, raw_text in menus:
        menu_id = _uuid(menu_id)
        venue_id = _uuid(venue_id)
        version_id = uuid.uuid4()
        confirmed = user_id is not None
        bind.execute(
            versions.insert().values(
                id=version_id,
                venue_id=venue_id,
                menu_id=menu_id,
                number=1,
                source_type="text",
                source_key="",
                source_filename="",
                source_url="",
                raw_text=raw_text or "",
                status="confirmed" if confirmed else "draft",
                confirmed_by=user_id if confirmed else None,
                confirmed_at=now if confirmed else None,
            )
        )
        dishes_table = sa.table(
            "dishes",
            sa.column("id", sa.Uuid()),
            sa.column("menu_id", sa.Uuid()),
            sa.column("menu_version_id", sa.Uuid()),
        )
        bind.execute(
            dishes_table.update()
            .where(dishes_table.c.menu_id == menu_id)
            .values(menu_version_id=version_id)
        )
    dishes = bind.execute(
        sa.text("SELECT id, menu_id, name, course, price FROM dishes ORDER BY menu_id, id")
    ).fetchall()
    dish_updates = sa.table(
        "dishes",
        sa.column("id", sa.Uuid()),
        sa.column("stable_id", sa.Uuid()),
        sa.column("position", sa.Integer()),
        sa.column("content_hash", sa.String()),
        sa.column("confidence", sa.JSON()),
        sa.column("allergens", sa.JSON()),
        sa.column("needs_repairing", sa.Boolean()),
    )
    positions: dict = {}
    for dish_id, menu_id, name, course, price in dishes:
        dish_id = _uuid(dish_id)
        menu_id = _uuid(menu_id)
        position = positions.get(menu_id, 0)
        positions[menu_id] = position + 1
        digest = content_hash(
            {
                "name": name or "",
                "course": course or "",
                "price": int(price or 0),
                "main_component": "",
                "cooking_method": "",
                "sauce": "",
                "richness": 0,
                "acidity": 0,
                "sweetness": 0,
                "spice": 0,
                "umami": 0,
                "allergens": [],
            }
        )
        bind.execute(
            dish_updates.update()
            .where(dish_updates.c.id == dish_id)
            .values(
                stable_id=dish_id,
                position=position,
                content_hash=digest,
                confidence=_CONFIDENCE,
                allergens=[],
                needs_repairing=False,
            )
        )


def upgrade() -> None:
    op.create_table(
        "menu_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("menu_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_key", sa.String(length=500), nullable=False),
        sa.Column("source_filename", sa.String(length=300), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("number >= 1", name="ck_menu_versions_number"),
        sa.CheckConstraint("source_type IN ('photo', 'pdf', 'url', 'text')", name="ck_menu_versions_source"),
        sa.CheckConstraint("status IN ('draft', 'confirmed')", name="ck_menu_versions_status"),
        sa.CheckConstraint(
            "(status = 'draft' AND confirmed_by IS NULL AND confirmed_at IS NULL) OR "
            "(status = 'confirmed' AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_menu_versions_confirm",
        ),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], name="fk_menu_versions_confirmed_by"),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"], name="fk_menu_versions_menu_id"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_menu_versions_venue_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("menu_id", "number", name="uq_menu_versions_menu_number"),
    )
    op.create_index("ix_menu_versions_venue_id", "menu_versions", ["venue_id"])
    op.create_index("ix_menu_versions_menu_id", "menu_versions", ["menu_id"])
    op.create_index("ix_menu_versions_confirmed_by", "menu_versions", ["confirmed_by"])
    op.create_index("ix_menu_versions_venue_menu", "menu_versions", ["venue_id", "menu_id"])
    _enable_rls()
    _add_dish_columns()
    _backfill()
    _seal_dish_columns()


def downgrade() -> None:
    _drop_dish_columns()
    _disable_rls()
    op.drop_index("ix_menu_versions_venue_menu", table_name="menu_versions")
    op.drop_index("ix_menu_versions_confirmed_by", table_name="menu_versions")
    op.drop_index("ix_menu_versions_menu_id", table_name="menu_versions")
    op.drop_index("ix_menu_versions_venue_id", table_name="menu_versions")
    op.drop_table("menu_versions")
