"""Menu service: money stays in minor units, and one venue cannot read another's menu."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.agents.tools import parse_menu as parse_menu_tool
from madira.agents.tools import recommend_pairings as recommend_pairings_tool
from madira.db import SessionLocal, init_db
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.menu.service import (
    extract_upload_text,
    get_menu,
    list_menus,
    parse_menu,
    recommend_pairings,
)
from madira.agents.demo.fixtures import SAMPLE_MENU_TEXT
from madira.main import app
from madira.models import Venue
from madira.seed import seed
from madira.tenancy import bind, ensure_demo_tenant, reset


@pytest.fixture(scope="module", autouse=True)
def _db():
    init_db()
    seed()


def _other_venue(organization_id: uuid.UUID) -> uuid.UUID:
    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "menu-service-other"))
        if venue is None:
            venue = Venue(organization_id=organization_id, name="Menu Service Other", slug="menu-service-other")
            session.add(venue)
            session.commit()
        return venue.id
    finally:
        session.close()


def test_parse_stores_prices_as_minor_units():
    demo = ensure_demo_tenant()
    payload = parse_menu(demo.venue_id, SAMPLE_MENU_TEXT, "pasted")
    crab = payload["dishes"][0]
    assert crab["name"].startswith("Dungeness")
    assert crab["price"] == 2400
    assert crab["currency"] == "USD"
    assert payload["cuisine"] == "California-French"
    assert "a2ui_operations" not in payload


def test_menus_are_isolated_by_venue():
    demo = ensure_demo_tenant()
    other = _other_venue(demo.organization_id)
    created = parse_menu(other, "Other House crab — $30\n", "pasted")
    demo_ids = {row["id"] for row in list_menus(demo.venue_id)["menus"]}
    other_ids = {row["id"] for row in list_menus(other)["menus"]}
    assert created["menu_id"] in other_ids
    assert created["menu_id"] not in demo_ids
    with pytest.raises(NotFound):
        get_menu(demo.venue_id, created["menu_id"])
    hidden = recommend_pairings(demo.venue_id, str(created["menu_id"]))
    assert hidden == {"error": "menu not found"}
    own = get_menu(other, created["menu_id"])
    assert own["dishes"][0]["pairings"] == []


def test_pairings_use_service_prices_for_the_owning_venue():
    from madira.domain.lists.service import curate
    from madira.models import BeverageList, ListItem

    demo = ensure_demo_tenant()
    curate(demo.venue_id)
    created = parse_menu(demo.venue_id, SAMPLE_MENU_TEXT, "pasted")
    paired = recommend_pairings(demo.venue_id, str(created["menu_id"]))
    assert "error" not in paired
    rows = paired["dishes"][0]["pairings"]
    assert [row["slot"] for row in rows] == [
        "best_by_the_glass",
        "best_bottle",
        "value",
        "adventurous",
    ]
    suggested = [row for row in rows if row["status"] != "gap"]
    assert suggested
    session = SessionLocal()
    try:
        for row in suggested:
            item = session.scalar(
                select(ListItem)
                .join(BeverageList, BeverageList.id == ListItem.list_id)
                .where(ListItem.sku_id == row["sku_id"], ListItem.venue_id == demo.venue_id)
                .order_by(BeverageList.created_at.desc(), ListItem.position.asc(), ListItem.id.asc())
            )
            assert item is not None
            assert row["glass_price"] == item.pour_price
            assert row["bottle_price"] == item.bottle_price
            assert row["currency"] == "USD"
    finally:
        session.close()
    stored = get_menu(demo.venue_id, created["menu_id"])
    stored_glass = next(row for row in stored["dishes"][0]["pairings"] if row["slot"] == "best_by_the_glass")
    fresh_glass = next(row for row in rows if row["slot"] == "best_by_the_glass")
    assert stored_glass["glass_price"] == fresh_glass["glass_price"]


def test_photo_and_binary_uploads_are_not_replaced_with_the_sample_menu():
    with pytest.raises(DraftFailed) as photo:
        extract_upload_text("plate.png", b"\x89PNG\r\n")
    assert photo.value.status == 415
    assert "Dungeness" not in photo.value.message
    assert extract_upload_text("notes.txt", "Crab special — $18\n".encode()) == "Crab special — $18\n"
    with pytest.raises(DraftFailed) as binary:
        extract_upload_text("blob.bin", b"\xff\xfe")
    assert binary.value.status == 415
    assert "Dungeness" not in binary.value.message


def test_tool_wrapper_emits_the_dish_surface():
    demo = ensure_demo_tenant()
    token = bind(demo)
    try:
        body = json.loads(parse_menu_tool(SAMPLE_MENU_TEXT, "pasted"))
    finally:
        reset(token)
    assert body["dishes"][0]["price"] == 2400
    ops = body["a2ui_operations"]
    assert ops[0]["createSurface"]["surfaceId"] == "dishes"
    assert "DishList" in json.dumps(ops)


def test_parse_route_returns_the_same_surface():
    with TestClient(app) as client:
        parsed = client.post("/menus/parse", json={"text": SAMPLE_MENU_TEXT, "source_name": "pasted"})
        assert parsed.status_code == 200
        body = parsed.json()
        assert body["dishes"][0]["price"] == 2400
        assert "DishList" in json.dumps(body["a2ui_operations"])
        menu_id = body["menu_id"]
        paired = client.post(f"/menus/{menu_id}/pair")
        assert paired.status_code == 200
        pair_body = paired.json()
        assert "PairingGrid" in json.dumps(pair_body["a2ui_operations"])
        assert [row["slot"] for row in pair_body["dishes"][0]["pairings"]] == [
            "best_by_the_glass",
            "best_bottle",
            "value",
            "adventurous",
        ]
        missing = client.post(f"/menus/{uuid.uuid4()}/pair")
        assert missing.status_code == 404


def test_recommend_tool_records_a_pairing_surface():
    demo = ensure_demo_tenant()
    token = bind(demo)
    try:
        created = parse_menu(demo.venue_id, SAMPLE_MENU_TEXT, "pasted")
        body = json.loads(recommend_pairings_tool(str(created["menu_id"])))
    finally:
        reset(token)
    assert "error" not in body
    assert [row["slot"] for row in body["dishes"][0]["pairings"]] == [
        "best_by_the_glass",
        "best_bottle",
        "value",
        "adventurous",
    ]
    assert "PairingGrid" in json.dumps(body["a2ui_operations"])
