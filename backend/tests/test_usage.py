"""Meter a run, block at the cap, and let the minute window reset."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, update

from madira.db import SessionLocal, init_db
from madira.domain.usage.pricing import estimate_cost
from madira.domain.usage.service import UsageError, begin_run, finish_run, update_limits
from madira.models import AgentRun, AgentUsage, AuditEvent
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _clear(venue_id):
    update_limits(venue_id, monthly_spend_cap_cents=None, requests_per_minute=None)


def test_demo_run_records_tokens_at_zero_cost():
    demo = _demo()
    _clear(demo.venue_id)
    try:
        run_id = begin_run(demo.venue_id, "How many bottles moved?")
        finish_run(
            run_id,
            reply="movement_count 4",
            delegated=["compliance-auditor"],
            latency_ms=15,
            tokens_in=8,
            tokens_out=4,
        )
        session = SessionLocal()
        try:
            run = session.get(AgentRun, run_id)
            assert run is not None
            assert run.organization_id == demo.organization_id
            usage = session.scalar(select(AgentUsage).where(AgentUsage.agent_run_id == run_id))
            assert usage is not None
            assert usage.subagent == "compliance-auditor"
            assert usage.tokens_in == 8
            assert usage.tokens_out == 4
            assert usage.cost_micro_usd == 0
            assert usage.cost_label == "demo"
            assert usage.model == "madira-demo-fixtures"
            assert usage.latency_ms == 15
            assert usage.created_at.tzinfo is not None
        finally:
            session.close()
    finally:
        _clear(demo.venue_id)


def test_live_cost_uses_the_pricing_table(monkeypatch):
    demo = _demo()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-usage-meter-test")
    _clear(demo.venue_id)
    try:
        assert estimate_cost("gpt-4.1-mini", 1_000_000, 0, demo=False) == (400_000, "estimate")
        assert estimate_cost("gpt-4.1-mini", 1_000_000, 0, demo=True) == (0, "demo")
        run_id = begin_run(demo.venue_id, "price this")
        finish_run(run_id, reply="done", delegated=["head-sommelier"], latency_ms=3, tokens_in=1_000_000, tokens_out=0)
        session = SessionLocal()
        try:
            usage = session.scalar(select(AgentUsage).where(AgentUsage.agent_run_id == run_id))
            assert usage is not None
            assert usage.cost_label == "estimate"
            assert usage.cost_micro_usd == 400_000
            assert "sk-usage" not in usage.model
        finally:
            session.close()
    finally:
        _clear(demo.venue_id)


def test_cap_blocks_at_the_limit_and_is_audited():
    demo = _demo()
    session = SessionLocal()
    try:
        session.execute(update(AgentUsage).where(AgentUsage.organization_id == demo.organization_id).values(cost_micro_usd=0))
        session.commit()
    finally:
        session.close()
    try:
        update_limits(demo.venue_id, monthly_spend_cap_cents=1, requests_per_minute=None)
        run_id = begin_run(demo.venue_id, "under the cap")
        finish_run(run_id, reply="ok", delegated=["head-sommelier"], latency_ms=1, tokens_in=0, tokens_out=0)
        session = SessionLocal()
        try:
            usage = session.scalar(select(AgentUsage).where(AgentUsage.agent_run_id == run_id))
            usage.cost_micro_usd = 10_000
            session.commit()
        finally:
            session.close()
        with pytest.raises(UsageError) as caught:
            begin_run(demo.venue_id, "over the cap")
        assert "cap" in caught.value.message
        session = SessionLocal()
        try:
            event = session.scalar(
                select(AuditEvent)
                .where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "usage.cap_blocked")
                .order_by(AuditEvent.seq.desc())
            )
            assert event is not None
            assert event.after_json["spent_cents"] >= 1
        finally:
            session.close()
        update_limits(demo.venue_id, monthly_spend_cap_cents=0, requests_per_minute=None)
        with pytest.raises(UsageError):
            begin_run(demo.venue_id, "zero cap")
    finally:
        _clear(demo.venue_id)


def test_rate_limit_blocks_a_burst_and_resets():
    demo = _demo()
    session = SessionLocal()
    try:
        old = datetime.now(timezone.utc) - timedelta(minutes=5)
        for run in session.scalars(select(AgentRun).where(AgentRun.organization_id == demo.organization_id)).all():
            run.created_at = old
        session.commit()
    finally:
        session.close()
    try:
        update_limits(demo.venue_id, monthly_spend_cap_cents=None, requests_per_minute=1)
        first = begin_run(demo.venue_id, "one")
        with pytest.raises(UsageError) as caught:
            begin_run(demo.venue_id, "two")
        assert "minute" in caught.value.message
        session = SessionLocal()
        try:
            event = session.scalar(
                select(AuditEvent)
                .where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "usage.rate_blocked")
                .order_by(AuditEvent.seq.desc())
            )
            assert event is not None
            run = session.get(AgentRun, first)
            run.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
            session.commit()
        finally:
            session.close()
        begin_run(demo.venue_id, "after the window")
    finally:
        _clear(demo.venue_id)


def test_migration_0026_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0026_usage_metering.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0025_sensors_reminders"' in source
    assert source.count('_enable_rls("') == 1
    assert "org_usage_read" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "if not _is_postgres():" in source
    db = tmp_path / "usage.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "head")
engine = sa.create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0029_tablet_pin"
    tables = set(sa.inspect(conn).get_table_names())
    assert "agent_usage" in tables
    orgs = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(organizations)"))}
    assert "monthly_spend_cap_cents" in orgs
    assert "requests_per_minute" in orgs
    runs = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(agent_runs)"))}
    assert "organization_id" in runs

command.downgrade(cfg, "0025_sensors_reminders")
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "agent_usage" not in tables
    orgs = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(organizations)"))}
    assert "monthly_spend_cap_cents" not in orgs
    runs = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(agent_runs)"))}
    assert "organization_id" not in runs
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0025_sensors_reminders"

command.upgrade(cfg, "head")
with engine.connect() as conn:
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0029_tablet_pin"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout