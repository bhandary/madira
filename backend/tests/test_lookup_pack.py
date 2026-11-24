"""The floor pack is versioned, venue-scoped, and hides cost from Staff."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.catalog.service import ensure_sku
from madira.domain.training.lookup import parse_query, parser_result_id
from madira.main import app
from madira.models import BeverageList, ListItem, Membership, Sku, User, Venue
from madira.seed import seed
from madira.tenancy import AUDITOR, DEMO_USER_SUB, ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "fixtures" / "lookup_vectors.json"
AUTH_SECRET = "lookup-pack-test-secret"
FORBIDDEN = {
    "cost",
    "margin",
    "margin_pct",
    "beverage_cost_pct",
    "line_cost",
    "wholesale",
    "unit_cost",
    "unit_cost_cents",
    "valuation_cents",
}


def _keys(value, found: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            _keys(item, found)
    elif isinstance(value, list):
        for item in value:
            _keys(item, found)


def _prepare():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.google_sub == "lookup-pack-auditor"))
        if user is None:
            user = User(
                google_sub="lookup-pack-auditor",
                email="lookup-pack-auditor@example.com",
                name="Lookup Pack Auditor",
                picture="",
                created_at=utcnow(),
                last_login_at=utcnow(),
            )
            session.add(user)
            session.flush()
        member = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == demo.venue_id))
        if member is None:
            session.add(Membership(user_id=user.id, venue_id=demo.venue_id, role=AUDITOR))
        else:
            member.role = AUDITOR
        other = session.scalar(select(Venue).where(Venue.slug == "other-lookup-pack"))
        if other is None:
            other = Venue(organization_id=demo.organization_id, name="Other Lookup", slug="other-lookup-pack")
            session.add(other)
            session.flush()
        foreign = ensure_sku(
            session,
            other.id,
            category="wine",
            producer="Foreign House",
            name="Foreign Pack Only",
            grape="Gamay",
            barcode="W-PACK-FOREIGN",
            par=1,
            cost=4321,
        )
        listing = session.scalar(select(BeverageList).where(BeverageList.venue_id == other.id))
        if listing is None:
            listing = BeverageList(venue_id=other.id, name="Foreign list", currency="USD")
            session.add(listing)
            session.flush()
        existing = session.scalar(select(ListItem).where(ListItem.venue_id == other.id, ListItem.sku_id == foreign.id))
        if existing is None:
            session.add(
                ListItem(
                    venue_id=other.id,
                    list_id=listing.id,
                    sku_id=foreign.id,
                    bottle_price=9000,
                    cost=4321,
                    margin_pct=40,
                    currency="USD",
                )
            )
        flagged = session.scalar(select(Sku).where(Sku.venue_id == demo.venue_id, Sku.barcode == "W-COT-01"))
        flagged.eighty_sixed_at = utcnow()
        session.commit()
    finally:
        session.close()
    return demo


def test_parser_vectors_match_the_shared_fixture():
    rows = json.loads(VECTORS.read_text())
    assert rows
    for row in rows:
        filters = parse_query(row["query"])
        assert parser_result_id(filters) == row["id"]
        assert filters.model_dump() == row["expect"]


def test_lookup_pack_etag_staff_and_tenancy(monkeypatch):
    _prepare()
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    with TestClient(app) as client:
        first = client.get("/lookup/pack")
        assert first.status_code == 200, first.text
        etag = first.headers["etag"]
        assert etag.startswith('"') and etag.endswith('"')
        body = first.json()
        assert set(body) >= {"service_date", "items", "notes", "cards", "dishes", "pairings"}
        names = [row["name"] for row in body["items"]]
        assert any("Chablis" in name for name in names)
        assert "Foreign Pack Only" not in names
        chablis = next(row for row in body["items"] if "Chablis" in row["name"])
        assert chablis["on_list"] is True
        assert isinstance(chablis["stock"], int)
        assert isinstance(chablis["eighty_six"], bool)
        assert "cost" in chablis
        cote = next(row for row in body["items"] if row["sku"] == "W-COT-01")
        assert cote["eighty_six"] is True
        note = next(row for row in body["notes"] if row["product_id"] == chablis["product_id"])
        assert note["guest_description"]
        card = next(row for row in body["cards"] if row["product_id"] == chablis["product_id"])
        assert "White wine glass" in card["glassware"]
        assert isinstance(body["pairings"], list)

        cached = client.get("/lookup/pack", headers={"If-None-Match": etag})
        assert cached.status_code == 304
        assert cached.content == b""
        assert cached.headers["etag"] == etag
        weak = client.get("/lookup/pack", headers={"If-None-Match": f"W/{etag}"})
        assert weak.status_code == 304
        fresh = client.get("/lookup/pack", headers={"If-None-Match": '"deadbeef"'})
        assert fresh.status_code == 200

        briefing = client.get("/tonight/briefing")
        assert briefing.status_code == 200, briefing.text
        briefing_etag = briefing.headers["etag"]
        assert briefing_etag
        again = client.get("/tonight/briefing", headers={"If-None-Match": briefing_etag})
        assert again.status_code == 304
        assert again.headers["etag"] == briefing_etag

        client.cookies.set("madira_demo_persona", "ana")
        staff = client.get("/lookup/pack")
        assert staff.status_code == 200, staff.text
        staff_body = staff.json()
        found: set[str] = set()
        _keys(staff_body, found)
        assert found.isdisjoint(FORBIDDEN)
        assert any("Chablis" in row["name"] for row in staff_body["items"])
        denied = client.post("/tonight/briefing/rebuild")
        assert denied.status_code == 403

        client.cookies.pop("madira_demo_persona")
        client.cookies.set(SESSION_COOKIE, issue_session("lookup-pack-auditor"))
        hidden = client.get("/lookup/pack")
        assert hidden.status_code == 403
        briefing_hidden = client.get("/tonight/briefing")
        assert briefing_hidden.status_code == 403
    session = SessionLocal()
    try:
        flagged = session.scalar(select(Sku).where(Sku.barcode == "W-COT-01"))
        if flagged is not None:
            flagged.eighty_sixed_at = None
            flagged.eighty_sixed_by_user_id = None
            session.commit()
    finally:
        session.close()
