"""Service standards, lesson drafts, and per-user quiz reviews.

Standards are the venue's service text. Lessons gain a floor position and an
approval. Quiz attempts record the signed-in user and a basis-point score.
Quiz reviews are the Leitner boxes. Postgres gets row level security on the
two new venue-scoped tables, matching ``0014``. SQLite skips those statements.

Revision ID: 0016_training_content
Revises: 0015_list_pricing_coverage
Create Date: 2026-11-24

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_training_content"
down_revision: Union[str, Sequence[str], None] = "0015_list_pricing_coverage"
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


def _add_timestamp(table: str, column: str) -> None:
    """SQLite rejects ADD COLUMN with CURRENT_TIMESTAMP. Postgres can backfill it."""

    if _is_postgres():
        op.add_column(
            table,
            sa.Column(column, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        return
    op.add_column(table, sa.Column(column, sa.DateTime(timezone=True), nullable=True))
    op.execute(f"UPDATE {table} SET {column} = CURRENT_TIMESTAMP WHERE {column} IS NULL")


def upgrade() -> None:
    op.create_table(
        "standards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("topic", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_standards_version"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_standards_venue_id"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], name="fk_standards_updated_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "slug", name="uq_standards_venue_slug"),
    )
    op.create_index("ix_standards_venue_id", "standards", ["venue_id"])

    op.add_column("lessons", sa.Column("position", sa.String(16), nullable=False, server_default=sa.text("'all'")))
    op.add_column("lessons", sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'approved'")))
    op.add_column("lessons", sa.Column("approved_by", sa.Uuid(), nullable=True))
    op.add_column("lessons", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lessons", sa.Column("source", sa.String(16), nullable=False, server_default=sa.text("'seed'")))
    op.add_column("lessons", sa.Column("standard_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("lessons", sa.Column("sku_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    _add_timestamp("lessons", "created_at")
    # SQLite cannot rebuild lessons while quizzes reference it and foreign keys are on.
    if _is_postgres():
        op.create_foreign_key("fk_lessons_approved_by", "lessons", "users", ["approved_by"], ["id"])
    op.execute(
        """
        UPDATE lessons SET position = CASE
            WHEN lower(role) = 'waitstaff' THEN 'server'
            WHEN lower(role) IN ('server', 'bartender', 'barback', 'host', 'all') THEN lower(role)
            ELSE 'all'
        END
        """
    )

    op.add_column("quizzes", sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'approved'")))
    op.add_column("quizzes", sa.Column("source", sa.String(16), nullable=False, server_default=sa.text("'lesson'")))
    _add_timestamp("quizzes", "created_at")

    op.add_column("quiz_attempts", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.add_column("quiz_attempts", sa.Column("score_bp", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column(
        "quiz_attempts",
        sa.Column("per_question", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    if _is_postgres():
        op.create_foreign_key("fk_quiz_attempts_user_id", "quiz_attempts", "users", ["user_id"], ["id"])
    op.create_index("ix_quiz_attempts_user_id", "quiz_attempts", ["user_id"])
    op.execute(
        """
        UPDATE quiz_attempts
        SET score_bp = CAST(ROUND(COALESCE(score, 0) * 100) AS INTEGER)
        """
    )

    op.create_table(
        "quiz_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("quiz_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.String(80), nullable=False),
        sa.Column("box", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_result", sa.String(16), nullable=False, server_default=sa.text("''")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("box >= 0 AND box <= 5", name="ck_quiz_reviews_box"),
        sa.CheckConstraint("last_result IN ('correct', 'wrong', '')", name="ck_quiz_reviews_last_result"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name="fk_quiz_reviews_venue_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_quiz_reviews_user_id"),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], name="fk_quiz_reviews_quiz_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "quiz_id", "question_id", name="uq_quiz_reviews_user_quiz_question"),
    )
    op.create_index("ix_quiz_reviews_venue_id", "quiz_reviews", ["venue_id"])
    op.create_index("ix_quiz_reviews_user_id", "quiz_reviews", ["user_id"])
    op.create_index("ix_quiz_reviews_quiz_id", "quiz_reviews", ["quiz_id"])

    op.add_column("memberships", sa.Column("position", sa.String(16), nullable=True))

    _enable_rls("standards")
    _enable_rls("quiz_reviews")


def downgrade() -> None:
    _disable_rls("quiz_reviews")
    _disable_rls("standards")

    op.drop_column("memberships", "position")

    op.drop_index("ix_quiz_reviews_quiz_id", table_name="quiz_reviews")
    op.drop_index("ix_quiz_reviews_user_id", table_name="quiz_reviews")
    op.drop_index("ix_quiz_reviews_venue_id", table_name="quiz_reviews")
    op.drop_table("quiz_reviews")

    op.drop_index("ix_quiz_attempts_user_id", table_name="quiz_attempts")
    if _is_postgres():
        op.drop_constraint("fk_quiz_attempts_user_id", "quiz_attempts", type_="foreignkey")
    op.drop_column("quiz_attempts", "per_question")
    op.drop_column("quiz_attempts", "score_bp")
    op.drop_column("quiz_attempts", "user_id")

    op.drop_column("quizzes", "created_at")
    op.drop_column("quizzes", "source")
    op.drop_column("quizzes", "status")

    if _is_postgres():
        op.drop_constraint("fk_lessons_approved_by", "lessons", type_="foreignkey")
    op.drop_column("lessons", "created_at")
    op.drop_column("lessons", "sku_ids")
    op.drop_column("lessons", "standard_ids")
    op.drop_column("lessons", "source")
    op.drop_column("lessons", "approved_at")
    op.drop_column("lessons", "approved_by")
    op.drop_column("lessons", "status")
    op.drop_column("lessons", "position")

    op.drop_index("ix_standards_venue_id", table_name="standards")
    op.drop_table("standards")
