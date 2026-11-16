"""Organization, venue, membership, and venue_id on venue-owned tables.

Existing rows are backfilled to the Maison Madira demo organization and venue,
then venue_id is required. On Postgres, venue-owned tables get row-level
security keyed on the per-transaction setting app.venue_id. SQLite skips RLS.

Revision ID: 0002_tenancy
Revises: 0001_baseline
Create Date: 2026-11-16

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_tenancy"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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

_SQLITE_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _bind():
    return op.get_bind()


def _is_postgres() -> bool:
    return _bind().dialect.name == "postgresql"


def _scalar(sql: str):
    return _bind().execute(sa.text(sql)).scalar()


def _add_venue_columns() -> None:
    for table in VENUE_TABLES:
        op.add_column(table, sa.Column("venue_id", sa.Integer(), nullable=True))


def _backfill(venue_id: int) -> None:
    for table in VENUE_TABLES:
        _bind().execute(
            sa.text(f"UPDATE {table} SET venue_id = :venue_id WHERE venue_id IS NULL"),
            {"venue_id": venue_id},
        )


def _seal_venue_columns() -> None:
    for table in VENUE_TABLES:
        if _is_postgres():
            op.alter_column(table, "venue_id", nullable=False)
            op.create_foreign_key(f"fk_{table}_venue_id", table, "venues", ["venue_id"], ["id"])
            op.create_index(f"ix_{table}_venue_id", table, ["venue_id"])
        else:
            with op.batch_alter_table(table) as batch:
                batch.alter_column("venue_id", existing_type=sa.Integer(), nullable=False)
                batch.create_foreign_key(f"fk_{table}_venue_id", "venues", ["venue_id"], ["id"])
                batch.create_index(f"ix_{table}_venue_id", ["venue_id"])


def _replace_global_unique(table: str, column: str, postgres_name: str, sqlite_name: str, new_name: str) -> None:
    columns = ["venue_id", column]
    if _is_postgres():
        op.drop_constraint(postgres_name, table, type_="unique")
        op.create_unique_constraint(new_name, table, columns)
        return
    with op.batch_alter_table(table, naming_convention=_SQLITE_NAMING) as batch:
        batch.drop_constraint(sqlite_name, type_="unique")
        batch.create_unique_constraint(new_name, columns)


def _restore_global_unique(table: str, column: str, new_name: str) -> None:
    if _is_postgres():
        op.drop_constraint(new_name, table, type_="unique")
        op.create_unique_constraint(None, table, [column])
        return
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(new_name, type_="unique")
        batch.create_unique_constraint(f"uq_{table}_{column}", [column])


def _enable_rls() -> None:
    if not _is_postgres():
        return
    for table in VENUE_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS venue_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY venue_isolation ON {table}
            USING (venue_id = NULLIF(current_setting('app.venue_id', true), '')::integer)
            WITH CHECK (venue_id = NULLIF(current_setting('app.venue_id', true), '')::integer)
            """
        )


def _disable_rls() -> None:
    if not _is_postgres():
        return
    for table in VENUE_TABLES:
        op.execute(f"DROP POLICY IF EXISTS venue_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def _drop_venue_columns() -> None:
    for table in reversed(VENUE_TABLES):
        if _is_postgres():
            op.drop_index(f"ix_{table}_venue_id", table_name=table)
            op.drop_constraint(f"fk_{table}_venue_id", table, type_="foreignkey")
            op.drop_column(table, "venue_id")
        else:
            with op.batch_alter_table(table) as batch:
                batch.drop_index(f"ix_{table}_venue_id")
                batch.drop_constraint(f"fk_{table}_venue_id", type_="foreignkey")
                batch.drop_column("venue_id")


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "venues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_venues_org_slug"),
    )
    op.create_index("ix_venues_organization_id", "venues", ["organization_id"])
    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "role IN ('Owner', 'Sommelier', 'Manager', 'Staff', 'Auditor')",
            name="ck_memberships_role",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "venue_id", name="uq_memberships_user_venue"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_venue_id", "memberships", ["venue_id"])

    op.bulk_insert(
        sa.table(
            "organizations",
            sa.column("name", sa.String),
            sa.column("slug", sa.String),
        ),
        [{"name": "Maison Madira", "slug": "maison-madira"}],
    )
    org_id = _scalar("SELECT id FROM organizations WHERE slug = 'maison-madira'")
    op.bulk_insert(
        sa.table(
            "venues",
            sa.column("organization_id", sa.Integer),
            sa.column("name", sa.String),
            sa.column("slug", sa.String),
        ),
        [{"organization_id": org_id, "name": "Maison Madira", "slug": "maison-madira"}],
    )
    venue_id = _scalar("SELECT id FROM venues WHERE slug = 'maison-madira'")

    _add_venue_columns()
    _backfill(int(venue_id))
    _seal_venue_columns()
    _replace_global_unique(
        "inventory_items",
        "sku",
        "inventory_items_sku_key",
        "uq_inventory_items_sku",
        "uq_inventory_items_venue_sku",
    )
    _replace_global_unique(
        "lessons",
        "slug",
        "lessons_slug_key",
        "uq_lessons_slug",
        "uq_lessons_venue_slug",
    )

    op.add_column("llm_credentials", sa.Column("organization_id", sa.Integer(), nullable=True))
    _bind().execute(
        sa.text("UPDATE llm_credentials SET organization_id = :org_id WHERE organization_id IS NULL"),
        {"org_id": org_id},
    )
    if _is_postgres():
        op.alter_column("llm_credentials", "organization_id", nullable=False)
        op.create_foreign_key(
            "fk_llm_credentials_organization_id",
            "llm_credentials",
            "organizations",
            ["organization_id"],
            ["id"],
        )
        op.create_index("ix_llm_credentials_organization_id", "llm_credentials", ["organization_id"])
    else:
        with op.batch_alter_table("llm_credentials") as batch:
            batch.alter_column("organization_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(
                "fk_llm_credentials_organization_id",
                "organizations",
                ["organization_id"],
                ["id"],
            )
            batch.create_index("ix_llm_credentials_organization_id", ["organization_id"])

    _enable_rls()


def downgrade() -> None:
    _disable_rls()
    _restore_global_unique("inventory_items", "sku", "uq_inventory_items_venue_sku")
    _restore_global_unique("lessons", "slug", "uq_lessons_venue_slug")
    _drop_venue_columns()
    if _is_postgres():
        op.drop_index("ix_llm_credentials_organization_id", table_name="llm_credentials")
        op.drop_constraint("fk_llm_credentials_organization_id", "llm_credentials", type_="foreignkey")
        op.drop_column("llm_credentials", "organization_id")
    else:
        with op.batch_alter_table("llm_credentials") as batch:
            batch.drop_index("ix_llm_credentials_organization_id")
            batch.drop_constraint("fk_llm_credentials_organization_id", type_="foreignkey")
            batch.drop_column("organization_id")
    op.drop_index("ix_memberships_venue_id", table_name="memberships")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_index("ix_venues_organization_id", table_name="venues")
    op.drop_table("venues")
    op.drop_table("organizations")
