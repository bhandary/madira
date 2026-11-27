"""Usage metering and organization spend limits.

``agent_usage`` stores one row per subagent call. Cost is integer
micro-dollars. ``organizations`` gains nullable cap columns in place: null
means the limit is off. ``agent_runs.organization_id`` is added in place so a
limit can count requests. Postgres RLS uses the 0014 helpers. A second SELECT
policy lets an organization read its own usage. SQLite skips both. Downgrade
drops the policies, the table, and the columns.

Revision ID: 0026_usage_metering
Revises: 0025_sensors_reminders
Create Date: 2026-11-25

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026_usage_metering"
down_revision: Union[str, Sequence[str], None] = "0025_sensors_reminders"
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


def _org_read_policy(table: str) -> None:
    if not _is_postgres():
        return
    op.execute(f"DROP POLICY IF EXISTS org_usage_read ON {table}")
    op.execute(
        f"""
        CREATE POLICY org_usage_read ON {table}
        FOR SELECT
        USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
        """
    )


def _drop_org_read_policy(table: str) -> None:
    if not _is_postgres():
        return
    op.execute(f"DROP POLICY IF EXISTS org_usage_read ON {table}")


def upgrade() -> None:
    op.add_column("organizations", sa.Column("monthly_spend_cap_cents", sa.Integer(), nullable=True))
    op.add_column("organizations", sa.Column("requests_per_minute", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_index("ix_agent_runs_org_created", "agent_runs", ["organization_id", "created_at"])
    _org_read_policy("agent_runs")

    op.create_table(
        "agent_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("subagent", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("tokens_in", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_micro_usd", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_label", sa.String(16), nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("tokens_in >= 0", name="ck_agent_usage_tokens_in"),
        sa.CheckConstraint("tokens_out >= 0", name="ck_agent_usage_tokens_out"),
        sa.CheckConstraint("cost_micro_usd >= 0", name="ck_agent_usage_cost"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_agent_usage_latency"),
        sa.CheckConstraint("cost_label IN ('demo', 'estimate')", name="ck_agent_usage_label"),
    )
    op.create_index("ix_agent_usage_organization_id", "agent_usage", ["organization_id"])
    op.create_index("ix_agent_usage_venue_id", "agent_usage", ["venue_id"])
    op.create_index("ix_agent_usage_agent_run_id", "agent_usage", ["agent_run_id"])
    op.create_index("ix_agent_usage_org_created", "agent_usage", ["organization_id", "created_at"])
    _enable_rls("agent_usage")
    _org_read_policy("agent_usage")


def downgrade() -> None:
    _drop_org_read_policy("agent_usage")
    _disable_rls("agent_usage")
    op.drop_index("ix_agent_usage_org_created", table_name="agent_usage")
    op.drop_index("ix_agent_usage_agent_run_id", table_name="agent_usage")
    op.drop_index("ix_agent_usage_venue_id", table_name="agent_usage")
    op.drop_index("ix_agent_usage_organization_id", table_name="agent_usage")
    op.drop_table("agent_usage")
    _drop_org_read_policy("agent_runs")
    op.drop_index("ix_agent_runs_org_created", table_name="agent_runs")
    op.drop_column("agent_runs", "organization_id")
    op.drop_column("organizations", "requests_per_minute")
    op.drop_column("organizations", "monthly_spend_cap_cents")
