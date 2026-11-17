"""Shared product catalog.

Free-text drink fields on pairings, list items, and inventory rows are
deduplicated into an organization Product, a ProductVariant (vintage and
bottle size), and one Sku per venue. Those three tables keep a sku_id.
Inventory on_hand stays put; par, barcode, and current cost move onto the Sku.

Pairings and list items are loaded first, keyed by category, producer, name,
region, country, style, and grape within the organization. An inventory row
only has category and name. It joins the product with that category and name
when the organization has exactly one, and that product's variant when the
product has exactly one. Otherwise it becomes its own product. The first
non-empty barcode, and the first non-zero par and cost, win when several rows
share a Sku.

Downgrade copies the catalog text back. Country, grape, and the structured
profile have no old column to return to. Two inventory rows that shared a Sku
keep distinct sku codes when the barcode would collide.

Revision ID: 0004_catalog
Revises: 0003_uuid_money_time
Create Date: 2026-11-17

"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from madira.domain.catalog.identity import clean, norm, product_key, variant_key
from madira.money import DEFAULT_CURRENCY

revision: str = "0004_catalog"
down_revision: Union[str, Sequence[str], None] = "0003_uuid_money_time"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TEXT_TABLES = ("pairings", "list_items", "inventory_items")
_PAIRING_TEXT = ("category", "name", "producer", "region", "style", "vintage")
_LIST_TEXT = _PAIRING_TEXT
_INVENTORY_TEXT = ("sku", "name", "category", "par", "unit_cost", "currency")


def _bind():
    return op.get_bind()


def _is_postgres() -> bool:
    return _bind().dialect.name == "postgresql"


def _rows(table: str) -> list[dict]:
    result = _bind().execute(sa.text(f"SELECT * FROM {table}"))
    return [dict(row) for row in result.mappings()]


def _uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _int(value) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def _pause_rls(tables: tuple[str, ...]) -> None:
    if not _is_postgres():
        return
    for table in tables:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def _resume_rls(tables: tuple[str, ...]) -> None:
    if not _is_postgres():
        return
    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def _enable_sku_rls() -> None:
    if not _is_postgres():
        return
    op.execute("ALTER TABLE skus ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE skus FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS venue_isolation ON skus")
    op.execute(
        """
        CREATE POLICY venue_isolation ON skus
        USING (venue_id = NULLIF(current_setting('app.venue_id', true), '')::uuid)
        WITH CHECK (venue_id = NULLIF(current_setting('app.venue_id', true), '')::uuid)
        """
    )


def _create_tables() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("producer", sa.String(200), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("region", sa.String(200), nullable=False),
        sa.Column("country", sa.String(80), nullable=False),
        sa.Column("style", sa.String(200), nullable=False),
        sa.Column("grape", sa.String(200), nullable=False),
        sa.Column("body", sa.String(32), nullable=False),
        sa.Column("acidity", sa.String(32), nullable=False),
        sa.Column("tannin", sa.String(32), nullable=False),
        sa.Column("sweetness", sa.String(32), nullable=False),
        sa.Column("oak", sa.String(32), nullable=False),
        sa.Column("intensity", sa.String(32), nullable=False),
        sa.Column("aroma_families", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_products_organization_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "category",
            "producer",
            "name",
            "region",
            "country",
            "style",
            "grape",
            name="uq_products_identity",
        ),
    )
    op.create_index("ix_products_organization_id", "products", ["organization_id"])
    op.create_table(
        "product_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("vintage", sa.String(32), nullable=False),
        sa.Column("bottle_size", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_variants_product_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "vintage",
            "bottle_size",
            name="uq_product_variants_identity",
        ),
    )
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])
    op.create_table(
        "skus",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("product_variant_id", sa.Uuid(), nullable=False),
        sa.Column("barcode", sa.String(64), nullable=False),
        sa.Column("bin_label", sa.String(200), nullable=False),
        sa.Column("par", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'USD'"), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_skus_venue_id"),
        sa.ForeignKeyConstraint(
            ["product_variant_id"],
            ["product_variants.id"],
            name="fk_skus_product_variant_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "product_variant_id", name="uq_skus_venue_variant"),
    )
    op.create_index("ix_skus_venue_id", "skus", ["venue_id"])
    op.create_index("ix_skus_product_variant_id", "skus", ["product_variant_id"])
    op.create_index(
        "uq_skus_venue_barcode",
        "skus",
        ["venue_id", "barcode"],
        unique=True,
        sqlite_where=sa.text("barcode != ''"),
        postgresql_where=sa.text("barcode <> ''"),
    )


def _new_sku() -> dict:
    return {
        "id": uuid.uuid4(),
        "barcode": "",
        "bin_label": "",
        "par": 0,
        "cost": 0,
        "currency": DEFAULT_CURRENCY,
    }


def _fill_stock(sku: dict, row: dict) -> None:
    code = clean(row.get("sku")).upper()
    if code and not sku["barcode"]:
        sku["barcode"] = code
    par = _int(row.get("par"))
    if sku["par"] == 0 and par:
        sku["par"] = par
    cost = _int(row.get("unit_cost"))
    if sku["cost"] == 0 and cost:
        sku["cost"] = cost
        sku["currency"] = clean(row.get("currency")) or DEFAULT_CURRENCY


def _build_catalog() -> dict[str, list[tuple[uuid.UUID, uuid.UUID]]]:
    venues = {_uuid(row["id"]): _uuid(row["organization_id"]) for row in _rows("venues")}
    products: dict[tuple, dict] = {}

    def ensure(
        organization_id: uuid.UUID,
        venue_id: uuid.UUID,
        *,
        category: str,
        producer: str,
        name: str,
        region: str,
        country: str,
        style: str,
        grape: str,
        vintage: str,
        bottle_size: str,
    ) -> dict:
        key = (organization_id, product_key(
            category=category,
            producer=producer,
            name=name,
            region=region,
            country=country,
            style=style,
            grape=grape,
        ))
        product = products.get(key)
        if product is None:
            product = {
                "id": uuid.uuid4(),
                "organization_id": organization_id,
                "category": clean(category),
                "producer": clean(producer),
                "name": clean(name),
                "region": clean(region),
                "country": clean(country),
                "style": clean(style),
                "grape": clean(grape),
                "variants": {},
            }
            products[key] = product
        vkey = variant_key(vintage=vintage, bottle_size=bottle_size)
        variant = product["variants"].get(vkey)
        if variant is None:
            variant = {
                "id": uuid.uuid4(),
                "vintage": clean(vintage),
                "bottle_size": clean(bottle_size),
                "skus": {},
            }
            product["variants"][vkey] = variant
        sku = variant["skus"].get(venue_id)
        if sku is None:
            sku = _new_sku()
            variant["skus"][venue_id] = sku
        return sku

    links: dict[str, list[tuple[uuid.UUID, uuid.UUID]]] = {
        "pairings": [],
        "list_items": [],
        "inventory_items": [],
    }
    for row in _rows("pairings"):
        venue_id = _uuid(row["venue_id"])
        sku = ensure(
            venues[venue_id],
            venue_id,
            category=row.get("category") or "",
            producer=row.get("producer") or "",
            name=row.get("name") or "",
            region=row.get("region") or "",
            country="",
            style=row.get("style") or "",
            grape="",
            vintage=row.get("vintage") or "",
            bottle_size="",
        )
        links["pairings"].append((_uuid(row["id"]), sku["id"]))
    for row in _rows("list_items"):
        venue_id = _uuid(row["venue_id"])
        sku = ensure(
            venues[venue_id],
            venue_id,
            category=row.get("category") or "",
            producer=row.get("producer") or "",
            name=row.get("name") or "",
            region=row.get("region") or "",
            country="",
            style=row.get("style") or "",
            grape="",
            vintage=row.get("vintage") or "",
            bottle_size="",
        )
        links["list_items"].append((_uuid(row["id"]), sku["id"]))

    for row in _rows("inventory_items"):
        venue_id = _uuid(row["venue_id"])
        organization_id = venues[venue_id]
        category_name = (norm(row.get("category")), norm(row.get("name")))
        named = [
            product
            for (org_id, key), product in products.items()
            if org_id == organization_id and (key[0], key[2]) == category_name
        ]
        if len(named) == 1 and len(named[0]["variants"]) == 1:
            variant = next(iter(named[0]["variants"].values()))
            sku = variant["skus"].get(venue_id)
            if sku is None:
                sku = _new_sku()
                variant["skus"][venue_id] = sku
        else:
            sku = ensure(
                organization_id,
                venue_id,
                category=row.get("category") or "",
                producer="",
                name=row.get("name") or "",
                region="",
                country="",
                style="",
                grape="",
                vintage="",
                bottle_size="",
            )
        _fill_stock(sku, row)
        links["inventory_items"].append((_uuid(row["id"]), sku["id"]))

    _insert_catalog(products)
    return links


def _insert_catalog(products: dict) -> None:
    product_rows = []
    variant_rows = []
    sku_rows = []
    for product in products.values():
        product_rows.append(
            {
                "id": product["id"],
                "organization_id": product["organization_id"],
                "category": product["category"],
                "producer": product["producer"],
                "name": product["name"],
                "region": product["region"],
                "country": product["country"],
                "style": product["style"],
                "grape": product["grape"],
                "body": "",
                "acidity": "",
                "tannin": "",
                "sweetness": "",
                "oak": "",
                "intensity": "",
                "aroma_families": [],
            }
        )
        for variant in product["variants"].values():
            variant_rows.append(
                {
                    "id": variant["id"],
                    "product_id": product["id"],
                    "vintage": variant["vintage"],
                    "bottle_size": variant["bottle_size"],
                }
            )
            for venue_id, sku in variant["skus"].items():
                sku_rows.append(
                    {
                        "id": sku["id"],
                        "venue_id": venue_id,
                        "product_variant_id": variant["id"],
                        "barcode": sku["barcode"],
                        "bin_label": sku["bin_label"],
                        "par": sku["par"],
                        "cost": sku["cost"],
                        "currency": sku["currency"] or DEFAULT_CURRENCY,
                    }
                )
    _insert("products", product_rows)
    _insert("product_variants", variant_rows)
    _insert("skus", sku_rows)


def _insert(table: str, rows: list[dict]) -> None:
    if not rows:
        return
    table_clause = sa.table(
        table,
        *[
            sa.column(
                name,
                sa.JSON() if name == "aroma_families" else sa.Uuid() if name.endswith("id") or name == "id" else sa.Integer() if name in {"par", "cost"} else sa.String(),
            )
            for name in rows[0]
        ],
    )
    _bind().execute(table_clause.insert(), rows)


def _add_sku_id(table: str) -> None:
    column = sa.Column("sku_id", sa.Uuid(), nullable=True)
    if _is_postgres():
        op.add_column(table, column)
        op.create_foreign_key(f"fk_{table}_sku_id", table, "skus", ["sku_id"], ["id"])
        op.create_index(f"ix_{table}_sku_id", table, ["sku_id"])
        return
    with op.batch_alter_table(table) as batch:
        batch.add_column(column)
        batch.create_foreign_key(f"fk_{table}_sku_id", "skus", ["sku_id"], ["id"])
        batch.create_index(f"ix_{table}_sku_id", ["sku_id"])


def _write_links(links: dict[str, list[tuple[uuid.UUID, uuid.UUID]]]) -> None:
    for table, pairs in links.items():
        if not pairs:
            continue
        target = sa.table(
            table,
            sa.column("id", sa.Uuid()),
            sa.column("sku_id", sa.Uuid()),
        )
        statement = (
            target.update()
            .where(target.c.id == sa.bindparam("b_id"))
            .values(sku_id=sa.bindparam("b_sku"))
        )
        _bind().execute(statement, [{"b_id": row_id, "b_sku": sku_id} for row_id, sku_id in pairs])


def _require_sku_ids() -> None:
    for table in _TEXT_TABLES:
        missing = _bind().execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE sku_id IS NULL")).scalar()
        if missing:
            raise RuntimeError(f"{table} has {missing} rows without a sku")


def _seal_sku_id(table: str) -> None:
    if _is_postgres():
        op.alter_column(table, "sku_id", existing_type=sa.Uuid(), nullable=False)
        return
    with op.batch_alter_table(table) as batch:
        batch.alter_column("sku_id", existing_type=sa.Uuid(), nullable=False)


def _drop_free_text() -> None:
    _drop_columns("pairings", _PAIRING_TEXT)
    _drop_columns("list_items", _LIST_TEXT)
    _drop_columns("inventory_items", _INVENTORY_TEXT, uniques=("uq_inventory_items_venue_sku",))


def _drop_columns(table: str, columns: tuple[str, ...], uniques: tuple[str, ...] = ()) -> None:
    if _is_postgres():
        for name in uniques:
            op.drop_constraint(name, table, type_="unique")
        for name in columns:
            op.drop_column(table, name)
        return
    with op.batch_alter_table(table) as batch:
        for name in uniques:
            batch.drop_constraint(name, type_="unique")
        for name in columns:
            batch.drop_column(name)


def _string_column(name: str, length: int) -> sa.Column:
    return sa.Column(name, sa.String(length), nullable=True)


def _add_restored_columns() -> None:
    pairing_columns = (
        _string_column("category", 32),
        _string_column("name", 200),
        _string_column("producer", 200),
        _string_column("region", 200),
        _string_column("style", 200),
        _string_column("vintage", 32),
    )
    list_columns = (
        _string_column("category", 32),
        _string_column("name", 200),
        _string_column("producer", 200),
        _string_column("region", 200),
        _string_column("style", 200),
        _string_column("vintage", 32),
    )
    inventory_columns = (
        _string_column("sku", 64),
        _string_column("name", 200),
        _string_column("category", 32),
        sa.Column("par", sa.Integer(), nullable=True),
        sa.Column("unit_cost", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
    )
    for table, columns in (
        ("pairings", pairing_columns),
        ("list_items", list_columns),
        ("inventory_items", inventory_columns),
    ):
        if _is_postgres():
            for column in columns:
                op.add_column(table, column)
        else:
            with op.batch_alter_table(table) as batch:
                for column in columns:
                    batch.add_column(column)


def _seal_restored() -> None:
    seals = {
        "pairings": {name: sa.String() for name in _PAIRING_TEXT},
        "list_items": {name: sa.String() for name in _LIST_TEXT},
        "inventory_items": {
            "sku": sa.String(),
            "name": sa.String(),
            "category": sa.String(),
            "par": sa.Integer(),
            "unit_cost": sa.Integer(),
            "currency": sa.String(3),
        },
    }
    for table, columns in seals.items():
        if _is_postgres():
            for name, kind in columns.items():
                op.alter_column(table, name, existing_type=kind, nullable=False)
        else:
            with op.batch_alter_table(table) as batch:
                for name, kind in columns.items():
                    batch.alter_column(name, existing_type=kind, nullable=False)
    if _is_postgres():
        op.create_unique_constraint(
            "uq_inventory_items_venue_sku",
            "inventory_items",
            ["venue_id", "sku"],
        )
        return
    with op.batch_alter_table("inventory_items") as batch:
        batch.create_unique_constraint("uq_inventory_items_venue_sku", ["venue_id", "sku"])


def _restore_text() -> None:
    products = {_uuid(row["id"]): row for row in _rows("products")}
    variants = {_uuid(row["id"]): row for row in _rows("product_variants")}
    skus = {_uuid(row["id"]): row for row in _rows("skus")}
    pairings = _rows("pairings")
    list_items = _rows("list_items")
    inventory = _rows("inventory_items")
    _add_restored_columns()

    def parts(sku_id):
        sku = skus[_uuid(sku_id)]
        variant = variants[_uuid(sku["product_variant_id"])]
        product = products[_uuid(variant["product_id"])]
        return product, variant, sku

    _update_rows(
        "pairings",
        [
            {
                "b_id": _uuid(row["id"]),
                "category": parts(row["sku_id"])[0]["category"],
                "name": parts(row["sku_id"])[0]["name"],
                "producer": parts(row["sku_id"])[0]["producer"],
                "region": parts(row["sku_id"])[0]["region"],
                "style": parts(row["sku_id"])[0]["style"],
                "vintage": parts(row["sku_id"])[1]["vintage"],
            }
            for row in pairings
        ],
        ("category", "name", "producer", "region", "style", "vintage"),
    )
    _update_rows(
        "list_items",
        [
            {
                "b_id": _uuid(row["id"]),
                "category": parts(row["sku_id"])[0]["category"],
                "name": parts(row["sku_id"])[0]["name"],
                "producer": parts(row["sku_id"])[0]["producer"],
                "region": parts(row["sku_id"])[0]["region"],
                "style": parts(row["sku_id"])[0]["style"],
                "vintage": parts(row["sku_id"])[1]["vintage"],
            }
            for row in list_items
        ],
        ("category", "name", "producer", "region", "style", "vintage"),
    )

    used: set[tuple[uuid.UUID, str]] = set()

    def take_code(venue_id: uuid.UUID, barcode: str, sku_id: uuid.UUID) -> str:
        base = clean(barcode).upper() or f"SKU-{str(sku_id).replace('-', '')[:8].upper()}"
        code = base
        number = 2
        while (venue_id, code) in used:
            code = f"{base}-{number}"
            number += 1
        used.add((venue_id, code))
        return code

    _update_rows(
        "inventory_items",
        [
            {
                "b_id": _uuid(row["id"]),
                "sku": take_code(_uuid(row["venue_id"]), parts(row["sku_id"])[2]["barcode"], _uuid(row["sku_id"])),
                "name": parts(row["sku_id"])[0]["name"],
                "category": parts(row["sku_id"])[0]["category"],
                "par": _int(parts(row["sku_id"])[2]["par"]),
                "unit_cost": _int(parts(row["sku_id"])[2]["cost"]),
                "currency": parts(row["sku_id"])[2]["currency"] or DEFAULT_CURRENCY,
            }
            for row in inventory
        ],
        ("sku", "name", "category", "par", "unit_cost", "currency"),
    )
    _seal_restored()


def _update_rows(table: str, rows: list[dict], columns: tuple[str, ...]) -> None:
    if not rows:
        return
    widths = {
        "category": 32,
        "name": 200,
        "producer": 200,
        "region": 200,
        "style": 200,
        "vintage": 32,
        "sku": 64,
        "currency": 3,
    }
    target = sa.table(
        table,
        sa.column("id", sa.Uuid()),
        *[
            sa.column(name, sa.Integer() if name in {"par", "unit_cost"} else sa.String(widths.get(name, 200)))
            for name in columns
        ],
    )
    statement = target.update().where(target.c.id == sa.bindparam("b_id")).values(
        **{name: sa.bindparam(name) for name in columns}
    )
    _bind().execute(statement, rows)


def _drop_sku_id(table: str) -> None:
    if _is_postgres():
        op.drop_index(f"ix_{table}_sku_id", table_name=table)
        op.drop_constraint(f"fk_{table}_sku_id", table, type_="foreignkey")
        op.drop_column(table, "sku_id")
        return
    with op.batch_alter_table(table) as batch:
        batch.drop_index(f"ix_{table}_sku_id")
        batch.drop_constraint(f"fk_{table}_sku_id", type_="foreignkey")
        batch.drop_column("sku_id")


def _drop_catalog() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS venue_isolation ON skus")
        op.execute("ALTER TABLE skus NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE skus DISABLE ROW LEVEL SECURITY")
    op.drop_index("uq_skus_venue_barcode", table_name="skus")
    op.drop_index("ix_skus_product_variant_id", table_name="skus")
    op.drop_index("ix_skus_venue_id", table_name="skus")
    op.drop_table("skus")
    op.drop_index("ix_product_variants_product_id", table_name="product_variants")
    op.drop_table("product_variants")
    op.drop_index("ix_products_organization_id", table_name="products")
    op.drop_table("products")


def upgrade() -> None:
    _create_tables()
    _pause_rls(_TEXT_TABLES)
    links = _build_catalog()
    for table in _TEXT_TABLES:
        _add_sku_id(table)
    _write_links(links)
    _require_sku_ids()
    for table in _TEXT_TABLES:
        _seal_sku_id(table)
    _drop_free_text()
    _resume_rls(_TEXT_TABLES)
    _enable_sku_rls()


def downgrade() -> None:
    _pause_rls(_TEXT_TABLES + ("skus",))
    _restore_text()
    for table in _TEXT_TABLES:
        _drop_sku_id(table)
    _drop_catalog()
    _resume_rls(_TEXT_TABLES)
