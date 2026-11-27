"""Specialist tiers default to the current model and metering stores that id."""

from __future__ import annotations

from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.domain.usage.service import begin_run, finish_run, update_limits
from madira.llm_runtime import LlmRuntime
from madira.model_tiers import TIER_BY_SPECIALIST, model_for_specialist, tier_for
from madira.models import AgentUsage
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant


def _runtime(**overrides) -> LlmRuntime:
    fields = {
        "demo_mode": False,
        "provider": "openai",
        "model": "venue-saved",
        "api_key": "sk-venue-own-key",
        "source": "settings",
        "stored": True,
        "configured": True,
        "key_hint": "key",
        "saved_provider": "openai",
        "saved_model": "venue-saved",
        "warning": "",
    }
    fields.update(overrides)
    return LlmRuntime(**fields)


def test_every_specialist_defaults_to_the_current_model():
    runtime = _runtime()
    assert set(TIER_BY_SPECIALIST) >= {
        "head-sommelier",
        "menu-analyst",
        "pairing-sommelier",
        "list-curator",
        "inventory-purchasing",
        "staff-trainer",
        "supplier-scheduler",
        "buyer",
        "compliance-auditor",
    }
    for name in TIER_BY_SPECIALIST:
        assert model_for_specialist(name, runtime) == "venue-saved"
    assert model_for_specialist("unknown-role", runtime) == "venue-saved"
    assert tier_for("compliance-auditor") == "fast"
    assert tier_for("pairing-sommelier") == "standard"


def test_fast_override_keeps_the_venue_model_for_standard(monkeypatch):
    monkeypatch.setenv("MADIRA_LLM_MODEL", "gpt-4.1")
    monkeypatch.setenv("MADIRA_LLM_MODEL_FAST", "gpt-4.1-mini")
    runtime = _runtime(model="venue-saved", api_key="sk-venue-own-key")
    assert model_for_specialist("compliance-auditor", runtime) == "gpt-4.1-mini"
    assert model_for_specialist("inventory-purchasing", runtime) == "gpt-4.1-mini"
    assert model_for_specialist("pairing-sommelier", runtime) == "venue-saved"
    assert model_for_specialist("menu-analyst", runtime) == "venue-saved"
    assert "sk-venue" not in model_for_specialist("compliance-auditor", runtime)


def test_demo_mode_meters_the_fixture_model():
    runtime = _runtime(demo_mode=True, model="gpt-4.1-mini", source="demo", api_key="")
    assert model_for_specialist("staff-trainer", runtime) == "madira-demo-fixtures"


def test_metering_records_the_model_each_specialist_used(monkeypatch):
    init_db()
    seed()
    demo = ensure_demo_tenant()
    update_limits(demo.venue_id, monthly_spend_cap_cents=None, requests_per_minute=None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-tier-meter")
    monkeypatch.setenv("MADIRA_LLM_MODEL_FAST", "gpt-4.1")
    try:
        run_id = begin_run(demo.venue_id, "meter the specialist model")
        finish_run(
            run_id,
            reply="ok",
            delegated=["pairing-sommelier", "compliance-auditor"],
            latency_ms=4,
            tokens_in=10,
            tokens_out=4,
        )
        session = SessionLocal()
        try:
            rows = {
                row.subagent: row.model
                for row in session.scalars(select(AgentUsage).where(AgentUsage.agent_run_id == run_id))
            }
        finally:
            session.close()
        assert rows["pairing-sommelier"] == "gpt-4.1-mini"
        assert rows["compliance-auditor"] == "gpt-4.1"
        assert "sk-tier" not in "".join(rows.values())
    finally:
        update_limits(demo.venue_id, monthly_spend_cap_cents=None, requests_per_minute=None)
