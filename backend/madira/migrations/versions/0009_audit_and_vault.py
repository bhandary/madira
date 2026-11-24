"""Append-only audit ledger, document vault, and retention default.

``audit_events`` is one hash chain per venue. ``seq`` starts at 1 and the
unique key on ``(venue_id, seq)`` keeps it strictly increasing. ``documents``
stores vault metadata; the bytes stay in file storage. Organizations keep
compliance files for 7 years unless an Owner changes that.

Revision ID: 0009_audit_and_vault
Revises: 0008_pairings
Create Date: 2026-11-24

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_audit_and_vault"
down_revision: Union[str, Sequence[str], None] = "0008_pairings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DOC_TYPES = "('invoice', 'po_pdf', 'delivery_note', 'license', 'certificate', 'other')"


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


def upgrade() -> None:
    # ADD COLUMN keeps organizations in place. Rebuilding it would drop a table
    # every venue points at, which SQLite rejects while foreign keys are on.
    op.add_column(
        "organizations",
        sa.Column("document_retention_years", sa.Integer(), nullable=False, server_default=sa.text("7")),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(320), nullable=False, server_default=sa.text("''")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False, server_default=sa.text("''")),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("seq >= 1", name="ck_audit_events_seq"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="fk_audit_events_org_id"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_audit_events_venue_id"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_audit_events_actor_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "seq", name="uq_audit_events_venue_seq"),
    )
    op.create_index("ix_audit_events_org_id", "audit_events", ["org_id"])
    op.create_index("ix_audit_events_venue_id", "audit_events", ["venue_id"])
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_venue_created", "audit_events", ["venue_id", "created_at"])
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("linked_entity_type", sa.String(80), nullable=False, server_default=sa.text("''")),
        sa.Column("linked_entity_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"doc_type IN {_DOC_TYPES}", name="ck_documents_doc_type"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="fk_documents_org_id"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_documents_venue_id"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], name="fk_documents_uploaded_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_documents_storage_key"),
    )
    op.create_index("ix_documents_org_id", "documents", ["org_id"])
    op.create_index("ix_documents_venue_id", "documents", ["venue_id"])
    op.create_index("ix_documents_uploaded_by_user_id", "documents", ["uploaded_by_user_id"])
    op.create_index("ix_documents_venue_created", "documents", ["venue_id", "created_at"])
    _enable_rls("audit_events")
    _enable_rls("documents")


def downgrade() -> None:
    _disable_rls("documents")
    _disable_rls("audit_events")
    op.drop_index("ix_documents_venue_created", table_name="documents")
    op.drop_index("ix_documents_uploaded_by_user_id", table_name="documents")
    op.drop_index("ix_documents_venue_id", table_name="documents")
    op.drop_index("ix_documents_org_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_audit_events_venue_created", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_venue_id", table_name="audit_events")
    op.drop_index("ix_audit_events_org_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_column("organizations", "document_retention_years")
