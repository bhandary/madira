"""Venue currency and imported list files.

A beverage list can record the stored CSV (``source_key``) and each list
item can record the section name and row order from that file. Prices on
an import use the venue's currency. List versioning stays out of this
change: an import is one beverage list, not a published ListVersion.

Revision ID: 0005_list_import
Revises: 0004_catalog
Create Date: 2026-11-17

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_list_import"
down_revision: Union[str, Sequence[str], None] = "0004_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD COLUMN keeps the table in place. Rebuilding venues would drop a table
    # that every venue-owned row points at, which SQLite rejects while foreign
    # keys are on.
    op.add_column("venues", sa.Column("currency", sa.String(3), server_default=sa.text("'USD'"), nullable=False))
    op.add_column("beverage_lists", sa.Column("source_key", sa.String(500), server_default=sa.text("''"), nullable=False))
    op.add_column(
        "beverage_lists",
        sa.Column("source_filename", sa.String(300), server_default=sa.text("''"), nullable=False),
    )
    op.add_column("list_items", sa.Column("section", sa.String(200), server_default=sa.text("''"), nullable=False))
    op.add_column("list_items", sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False))


def downgrade() -> None:
    op.drop_column("list_items", "position")
    op.drop_column("list_items", "section")
    op.drop_column("beverage_lists", "source_filename")
    op.drop_column("beverage_lists", "source_key")
    op.drop_column("venues", "currency")
