"""Procurement service: tastings stay drafts, and one venue cannot read another's calendar."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.domain.errors import NotFound
from madira.domain.procurement.service import list_suppliers
from madira.domain.tastings.service import create_session, ics_text, list_sessions, plan
from madira.main import app
from madira.models import Supplier, Venue
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant


def _other_venue(organization_id: uuid.UUID) -> uuid.UUID:
    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "procurement-service-other"))
        if venue is None:
            venue = Venue(organization_id=organization_id, name="Procurement Service Other", slug="procurement-service-other")
            session.add(venue)
            session.flush()
            session.add(Supplier(venue_id=venue.id, name="Other House Wines", kind="distributor"))
            session.commit()
        return venue.id
    finally:
        session.close()


def test_schedule_builds_a_draft_ics_and_does_not_mark_it_sent():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    payload = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title="Service Loire tasting",
        starts_at="2026-12-01T15:00",
        ends_at="2026-12-01T17:00",
        location="Maison Madira cellar",
    )
    draft = payload["draft"]
    assert draft["sent"] is False
    assert draft["ics"].startswith("BEGIN:VCALENDAR\r\n")
    assert "DTSTART:20261201T150000Z" in draft["ics"]
    assert "DTEND:20261201T170000Z" in draft["ics"]
    assert "Service Loire tasting" in draft["ics"]
    listed = list_sessions(demo.venue_id)["sessions"]
    saved = next(row for row in listed if row["id"] == draft["id"])
    assert saved["ics"] == draft["ics"]
    assert "ics" not in next(row for row in payload["tastings"] if row["id"] == draft["id"])
    assert ics_text(demo.venue_id, draft["id"]) == draft["ics"]


def test_tastings_and_suppliers_stay_inside_the_venue():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    other = _other_venue(demo.organization_id)
    created = create_session(
        other,
        supplier_name="Other House Wines",
        title="Other house tasting",
        starts_at="2026-12-02T15:00",
        ends_at="2026-12-02T16:00",
    )
    demo_ids = {row["id"] for row in list_sessions(demo.venue_id)["sessions"]}
    assert created["draft"]["id"] not in demo_ids
    with pytest.raises(NotFound):
        ics_text(demo.venue_id, created["draft"]["id"])
    demo_names = {row["name"] for row in list_suppliers(demo.venue_id)["suppliers"]}
    other_names = {row["name"] for row in list_suppliers(other)["suppliers"]}
    assert "Other House Wines" not in demo_names
    assert "Kermit Lynch Wine Merchant" not in other_names
    with pytest.raises(NotFound):
        plan(uuid.uuid4(), supplier="Nobody", title="Missing")


def test_tasting_routes_return_the_calendar_surface():
    init_db()
    seed()
    with TestClient(app) as client:
        created = client.post(
            "/tastings",
            json={
                "supplier_name": "Kermit Lynch Wine Merchant",
                "title": "Route Loire tasting",
                "starts_at": "2026-12-03T15:00",
                "ends_at": "2026-12-03T17:00",
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert body["draft"]["sent"] is False
        assert body["a2ui_operations"][0]["createSurface"]["surfaceId"] == "tasting"
        assert "TastingCalendar" in json.dumps(body["a2ui_operations"])
        ics = client.get(f"/tastings/{body['draft']['id']}.ics")
        assert ics.status_code == 200
        assert ics.text.startswith("BEGIN:VCALENDAR")
        missing = client.get(f"/tastings/{uuid.uuid4()}.ics")
        assert missing.status_code == 404
