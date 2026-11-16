"""List service: buying math stays in minor units, and lists stay inside the venue."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.agents.tools import curate_beverage_list
from madira.db import SessionLocal, init_db
from madira.domain.lists.service import curate, list_lists
from madira.main import app
from madira.models import Venue
from madira.seed import seed
from madira.tenancy import bind, ensure_demo_tenant, reset


def _other_venue(organization_id: uuid.UUID) -> uuid.UUID:
    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "list-service-other"))
        if venue is None:
            venue = Venue(organization_id=organization_id, name="List Service Other", slug="list-service-other")
            session.add(venue)
            session.commit()
        return venue.id
    finally:
        session.close()


def test_curate_keeps_money_in_minor_units():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    payload = curate(demo.venue_id, budget=12000, target_margin=3.2, name="Maison Madira autumn list")
    assert payload["budget"] == 1_200_000
    assert payload["spent"] == 519_760
    assert payload["remaining"] == 1_200_000 - 519_760
    assert payload["currency"] == "USD"
    assert payload["items"][0]["cost"] == 1800
    assert payload["items"][0]["line_cost"] == 1800 * 12
    assert "a2ui_operations" not in payload
    stored = list_lists(demo.venue_id)["lists"]
    saved = next(row for row in stored if row["id"] == payload["list_id"])
    assert saved["budget"] == 1_200_000
    assert saved["items"][0]["cost"] == 1800


def test_lists_are_isolated_by_venue():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    other = _other_venue(demo.organization_id)
    created = curate(other, budget=100, target_margin=3, name="Other house list")
    demo_ids = {row["id"] for row in list_lists(demo.venue_id)["lists"]}
    other_ids = {row["id"] for row in list_lists(other)["lists"]}
    assert created["list_id"] in other_ids
    assert created["list_id"] not in demo_ids


def test_curate_route_and_tool_emit_the_list_surface():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    with TestClient(app) as client:
        response = client.post(
            "/lists/curate",
            json={"budget": 12000, "target_margin": 3.2, "name": "Maison Madira autumn list"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["budget"] == 1_200_000
    assert body["spent"] == 519_760
    assert "BeverageListTable" in json.dumps(body["a2ui_operations"])
    token = bind(demo)
    try:
        tool_body = json.loads(curate_beverage_list(12000, 3.2, "Maison Madira autumn list"))
    finally:
        reset(token)
    assert tool_body["spent"] == 519_760
    assert tool_body["a2ui_operations"][0]["createSurface"]["surfaceId"] == "beverage-list"
