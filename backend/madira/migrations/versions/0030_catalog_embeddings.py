"""Catalog embeddings for semantic search.

Postgres tries ``CREATE EXTENSION vector`` and, when that works, adds an
unmapped ``embedding`` column. A server without the extension still migrates:
the JSON ``values`` column is the ranking source. SQLite always uses that
fallback. Row level security matches migration 0014. Downgrade drops the
policy and the table. The extension is left in place.

Revision ID: 0030_catalog_embeddings
Revises: 0029_tablet_pin
Create Date: 2026-11-27

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0030_catalog_embeddings"
down_revision: Union[str, Sequence[str], None] = "0029_tablet_pin"
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


def _add_vector_column() -> None:
    if not _is_postgres():
        return
    from madira.domain.embeddings.schema import vector_extension_available

    if not vector_extension_available(op.get_bind()):
        return
    op.execute("ALTER TABLE catalog_embeddings ADD COLUMN embedding vector")


def upgrade() -> None:
    op.create_table(
        "catalog_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), server_default="", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("subject_type IN ('sku', 'note')", name="ck_catalog_embeddings_subject"),
        sa.CheckConstraint("dimension >= 1", name="ck_catalog_embeddings_dimension"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "subject_type", "subject_id", name="uq_catalog_embeddings_subject"),
    )
    op.create_index("ix_catalog_embeddings_organization_id", "catalog_embeddings", ["organization_id"])
    op.create_index("ix_catalog_embeddings_venue_id", "catalog_embeddings", ["venue_id"])
    op.create_index("ix_catalog_embeddings_subject_id", "catalog_embeddings", ["subject_id"])
    op.create_index(
        "ix_catalog_embeddings_venue_model",
        "catalog_embeddings",
        ["venue_id", "model_name", "dimension"],
    )
    _add_vector_column()
    _enable_rls("catalog_embeddings")


def downgrade() -> None:
    _disable_rls("catalog_embeddings")
    op.drop_index("ix_catalog_embeddings_venue_model", table_name="catalog_embeddings")
    op.drop_index("ix_catalog_embeddings_subject_id", table_name="catalog_embeddings")
    op.drop_index("ix_catalog_embeddings_venue_id", table_name="catalog_embeddings")
    op.drop_index("ix_catalog_embeddings_organization_id", table_name="catalog_embeddings")
    op.drop_table("catalog_embeddings")
