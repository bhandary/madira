"""The selector stays inside the budget and the cellar, and the same inputs pick the same bottles."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.errors import DraftFailed
from madira.domain.lists.copy import set_list_completer
from madira.domain.lists.service import curate
from madira.main import app
from madira.models import AuditEvent, Membership, StorageZone, User, Venue
from madira.seed import seed
from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, bind, ensure_demo_tenant, reset

AUTH_SECRET = "list-curation-test-secret"


@pytest.fixture(autouse=True)
def _reset_completer():
    set_list_completer(None)
    yield
    set_list_completer(None)


def _ids(payload: dict) -> list[str]:
    return [str(item["product_id"]) for item in payload["items"]]


def test_curate_stays_inside_budget_and_capacity_and_is_deterministic():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        zones = session.scalars(select(StorageZone).where(StorageZone.venue_id == demo.venue_id)).all()
        previous = [(zone.id, zone.capacity_bottles) for zone in zones]
        for zone in zones:
            zone.capacity_bottles = 2
        session.commit()
    finally:
        session.close()
    first = curate(demo.venue_id, budget=12000, target_margin=3.2, name="House list")
    second = curate(demo.venue_id, budget=12000, target_margin=3.2, name="House list")
    assert first["spent"] <= first["budget"]
    assert first["bottles"] <= first["capacity_bottles"]
    assert first["bottles"] == len(first["items"])
    assert all(item["product_id"] for item in first["items"])
    assert all(cell["product_id"] is None for cell in first["suggestions"])
    assert _ids(first) == _ids(second)
    assert first["spent"] == second["spent"]
    tight = curate(demo.venue_id, budget=20, target_margin=3.2, name="Tight list")
    assert tight["spent"] <= tight["budget"]
    assert tight["bottles"] <= 2
    session = SessionLocal()
    try:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "list.curated")
        )
        for zone_id, bottles in previous:
            zone = session.get(StorageZone, zone_id)
            if zone is not None:
                zone.capacity_bottles = bottles
        session.commit()
    finally:
        session.close()
    assert event is not None


def test_live_mode_uses_the_completer_and_stays_grounded(monkeypatch):
    init_db()
    seed()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-list-curation-not-a-fixture")
    seen = {"calls": 0}

    def fake(prompt: str) -> str:
        seen["calls"] += 1
        assert "SECTIONS_JSON=" in prompt
        start = prompt.find("SECTIONS_JSON=")
        names = json.loads(prompt[start + len("SECTIONS_JSON=") :].splitlines()[0])
        return json.dumps(
            {
                "sections": [
                    {"name": name, "note": f"The {name} section follows the menu and leaves room to buy what is still missing."}
                    for name in names
                ]
            }
        )

    set_list_completer(fake)
    demo = ensure_demo_tenant()
    payload = curate(demo.venue_id, budget=12000, target_margin=3.2)
    assert seen["calls"] >= 1
    encoded = json.dumps(payload, default=str)
    assert "Sèvre-et-Maine" not in encoded
    assert all(item["product_id"] for item in payload["items"])
    assert payload["spent"] <= payload["budget"]


def test_a_failing_completer_raises_and_does_not_invent_a_list(monkeypatch):
    init_db()
    seed()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-list-curation-not-a-fixture")

    def boom(_prompt: str) -> str:
        raise RuntimeError("connection refused")

    set_list_completer(boom)
    demo = ensure_demo_tenant()
    with pytest.raises(DraftFailed) as raised:
        curate(demo.venue_id, budget=12000, target_margin=3.2)
    assert "RuntimeError" in raised.value.message
    assert "Sèvre-et-Maine" not in raised.value.message


def _member(session, google_sub: str, email: str, venue_id, role: str) -> None:
    user = session.scalar(select(User).where(User.google_sub == google_sub))
    now = utcnow()
    if user is None:
        user = User(google_sub=google_sub, email=email, name=email, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
    membership = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id))
    if membership is None:
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=role))
    else:
        membership.role = role


def test_routes_follow_role_and_venue(monkeypatch):
    init_db()
    seed()
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        other = Venue(
            organization_id=demo.organization_id,
            name="Other List",
            slug=f"other-list-{uuid.uuid4().hex[:8]}",
        )
        session.add(other)
        session.flush()
        _member(session, "staff-list", "staff-list@example.com", demo.venue_id, STAFF)
        _member(session, "manager-list", "manager-list@example.com", demo.venue_id, MANAGER)
        _member(session, "auditor-list", "auditor-list@example.com", demo.venue_id, AUDITOR)
        _member(session, "sommelier-list", "sommelier-list@example.com", demo.venue_id, SOMMELIER)
        _member(session, "owner-other-list", "owner-other-list@example.com", other.id, OWNER)
        session.commit()
        other_id = other.id
    finally:
        session.close()

    created = curate(demo.venue_id, budget=12000, target_margin=3.2, name="Role list")
    list_id = created["list_id"]
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, issue_session("staff-list"))
        denied = client.post("/lists/curate", json={"budget": 1000, "target_margin": 3})
        assert denied.status_code == 403
        listed = client.get("/lists")
        assert listed.status_code == 200
        listed_body = listed.json()
        assert listed_body["lists"]
        for row in listed_body["lists"]:
            for item in row["items"]:
                assert "cost" not in item
                assert "margin_pct" not in item
                assert "beverage_cost_pct" not in item
                assert "line_cost" not in item
            for section in row["sections"]:
                assert "margin_pct" not in section
                assert "spend" not in section
                assert "beverage_cost_pct" not in section
        health = client.get(f"/lists/{list_id}/health")
        assert health.status_code == 403

        client.cookies.set(SESSION_COOKIE, issue_session("manager-list"))
        covered = client.get(f"/lists/{list_id}/coverage")
        assert covered.status_code == 200
        assert "cells" in covered.json()

        client.cookies.set(SESSION_COOKIE, issue_session("auditor-list"))
        audited = client.get(f"/lists/{list_id}/health")
        assert audited.status_code == 200

        client.cookies.set(SESSION_COOKIE, issue_session("owner-other-list"))
        missing = client.get(f"/lists/{list_id}/coverage")
        assert missing.status_code == 404

        client.cookies.set(SESSION_COOKIE, issue_session("sommelier-list"))
        rules = client.put(
            "/lists/pricing-rules",
            json={
                "rules": [
                    {
                        "category": "wine",
                        "cost_min_cents": 0,
                        "cost_max_cents": None,
                        "bottle_multiple": 3,
                        "glass_pours_per_bottle": 5,
                        "glass_multiple": 1.2,
                        "round_to_cents": 100,
                    }
                ]
            },
        )
        assert rules.status_code == 200, rules.text
        assert rules.json()["source"] == "stored"
    session = SessionLocal()
    try:
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.venue_id == demo.venue_id,
                AuditEvent.action == "list.pricing_rules_updated",
            )
        )
    finally:
        session.close()
    assert event is not None
    assert other_id != demo.venue_id
    token = bind(ensure_demo_tenant())
    try:
        assert uuid.UUID(str(list_id))
    finally:
        reset(token)
