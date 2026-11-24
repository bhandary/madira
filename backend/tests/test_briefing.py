"""Tonight's briefing is built once per local date, after briefing hour."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from madira.db import SessionLocal, init_db
from madira.domain.catalog.service import ensure_sku
from madira.domain.errors import DraftFailed
from madira.domain.inventory.ledger import apply_count
from madira.domain.training.briefing import (
    bottle_push_score,
    build,
    get_or_build_today,
    set_clock,
    set_intro_completer,
    urgency_for,
)
from madira.main import app
from madira.models import (
    BeverageList,
    Briefing,
    BriefingAck,
    Dish,
    InventoryItem,
    ListItem,
    Menu,
    MenuVersion,
    Pairing,
    PurchaseOrder,
    Receipt,
    ReceiptLine,
    Sku,
    Supplier,
    Venue,
)
from madira.seed import seed
from madira.tenancy import bind, ensure_demo_tenant, reset

ROOT = Path(__file__).resolve().parents[2]
ZONE = ZoneInfo("America/Los_Angeles")
AUTH_SECRET = "briefing-test-secret"


def _boom(_prompt: str) -> str:
    raise DraftFailed("The briefing intro failed (RuntimeError).", 502)


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clock():
    set_clock(None)
    set_intro_completer(None)
    yield
    set_clock(None)
    set_intro_completer(None)


@pytest.fixture
def house():
    init_db()
    seed()
    ctx = ensure_demo_tenant()
    token = bind(ctx)
    session = SessionLocal()
    try:
        session.execute(delete(BriefingAck).where(BriefingAck.venue_id == ctx.venue_id))
        session.execute(delete(Briefing).where(Briefing.venue_id == ctx.venue_id))
        venue = session.get(Venue, ctx.venue_id)
        venue.timezone = "America/Los_Angeles"
        venue.briefing_hour = 15
        session.commit()
    finally:
        session.close()
    yield ctx
    reset(token)


def _local(moment: datetime) -> datetime:
    return moment.astimezone(ZONE)


def test_push_score_is_surplus_times_margin_times_urgency():
    assert bottle_push_score(10, 10, 60, 2) == 0
    assert bottle_push_score(8, 10, 60, 2) == 0
    assert bottle_push_score(14, 10, 50, 2) == 4
    today = date(2026, 11, 24)
    quiet, quiet_why = urgency_for(today, "wine", 2028, None)
    assert quiet == 0
    assert quiet_why == ""
    soon, why = urgency_for(today, "wine", 2026, None)
    assert soon > 0
    assert "2026" in why
    assert "margin" not in why
    fresh, fresh_why = urgency_for(today, "beer", None, date(2026, 12, 20))
    assert fresh > 0
    assert "best by" in fresh_why


def test_briefing_waits_for_briefing_hour_and_stays_on_the_local_date(house):
    set_clock(lambda: _utc(2026, 11, 24, 22, 30))
    assert _local(_utc(2026, 11, 24, 22, 30)).hour < 15
    early = get_or_build_today()
    assert early["briefing"] is None
    assert early["service_date"] == "2026-11-24"

    set_clock(lambda: _utc(2026, 11, 24, 23, 0))
    assert _local(_utc(2026, 11, 24, 23, 0)).hour == 15
    opened = get_or_build_today()
    assert opened["briefing"]["service_date"] == "2026-11-24"
    first_id = opened["briefing"]["id"]

    set_clock(lambda: _utc(2026, 11, 25, 7, 30))
    assert _local(_utc(2026, 11, 25, 7, 30)).date() == date(2026, 11, 24)
    same_night = get_or_build_today()
    assert same_night["briefing"]["id"] == first_id

    set_clock(lambda: _utc(2026, 11, 25, 8, 5))
    assert _local(_utc(2026, 11, 25, 8, 5)).date() == date(2026, 11, 25)
    assert _local(_utc(2026, 11, 25, 8, 5)).hour < 15
    next_morning = get_or_build_today()
    assert next_morning["briefing"] is None
    assert next_morning["service_date"] == "2026-11-25"


def test_dst_boundaries_use_the_venue_timezone(house):
    before_spring = _utc(2026, 3, 8, 21, 30)
    assert _local(before_spring).date() == date(2026, 3, 8)
    assert _local(before_spring).hour < 15
    set_clock(lambda: before_spring)
    assert get_or_build_today()["briefing"] is None

    after_spring = _utc(2026, 3, 8, 22, 5)
    assert _local(after_spring).date() == date(2026, 3, 8)
    assert _local(after_spring).hour >= 15
    set_clock(lambda: after_spring)
    sprung = get_or_build_today()
    assert sprung["briefing"]["service_date"] == "2026-03-08"

    before_fall = _utc(2026, 11, 1, 22, 0)
    assert _local(before_fall).utcoffset() == timedelta(hours=-8)
    assert _local(before_fall).hour < 15
    set_clock(lambda: before_fall)
    assert get_or_build_today()["briefing"] is None

    at_fall = _utc(2026, 11, 1, 23, 0)
    assert _local(at_fall).date() == date(2026, 11, 1)
    assert _local(at_fall).hour == 15
    set_clock(lambda: at_fall)
    fallen = get_or_build_today()
    assert fallen["briefing"]["service_date"] == "2026-11-01"
    fall_id = fallen["briefing"]["id"]

    still = _utc(2026, 11, 2, 7, 30)
    assert _local(still).date() == date(2026, 11, 1)
    set_clock(lambda: still)
    assert get_or_build_today()["briefing"]["id"] == fall_id

    morning = _utc(2026, 11, 2, 8, 5)
    assert _local(morning).date() == date(2026, 11, 2)
    assert _local(morning).hour < 15
    set_clock(lambda: morning)
    assert get_or_build_today()["briefing"] is None


def test_build_is_idempotent(house):
    set_clock(lambda: _utc(2026, 11, 24, 23, 30))
    first = build()
    second = build()
    assert first["briefing"]["id"] == second["briefing"]["id"]
    assert first["briefing"]["status"] == "published"
    session = SessionLocal()
    try:
        rows = session.scalars(select(Briefing).where(Briefing.venue_id == house.venue_id)).all()
        assert len(rows) == 1
    finally:
        session.close()


def test_worker_builds_every_venue(house):
    set_clock(lambda: _utc(2026, 6, 2, 22, 30))
    from madira.workers.briefings import main

    assert main() == 0
    again = build()
    session = SessionLocal()
    try:
        row = session.scalar(
            select(Briefing).where(Briefing.venue_id == house.venue_id, Briefing.service_date == date(2026, 6, 2))
        )
        assert row is not None
        assert str(row.id) == again["briefing"]["id"]
    finally:
        session.close()

    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "MADIRA_API_KEY", "DATABASE_URL"):
        env.pop(key, None)
    env["MADIRA_DEMO_MODE"] = "true"
    env["PYTHONPATH"] = "backend"
    proc = subprocess.run(
        [sys.executable, "-m", "madira.workers.briefings"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_higher_margin_wins_the_push_and_the_reason_has_no_numbers(house):
    today = date(2026, 11, 24)
    set_clock(lambda: _utc(2026, 11, 24, 23, 30))
    session = SessionLocal()
    created = []
    try:
        skus = session.scalars(
            select(Sku).where(Sku.venue_id == house.venue_id).options(joinedload(Sku.variant))
        ).unique().all()
        for sku in skus:
            sku.best_by = None
            if sku.variant is not None:
                sku.variant.drink_by_year = None
        listing = session.scalar(select(BeverageList).where(BeverageList.venue_id == house.venue_id))
        quiet = ensure_sku(
            session,
            house.venue_id,
            category="wine",
            producer="Quiet House",
            name="Quiet Push Chardonnay",
            grape="Chardonnay",
            barcode="W-PSH-01",
            par=10,
            cost=1000,
        )
        loud = ensure_sku(
            session,
            house.venue_id,
            category="wine",
            producer="Loud House",
            name="Loud Push Chardonnay",
            grape="Chardonnay",
            barcode="W-PSH-02",
            par=10,
            cost=1000,
        )
        for sku, price in ((quiet, 2000), (loud, 8000)):
            sku.variant.drink_by_year = 2026
            session.add(InventoryItem(venue_id=house.venue_id, sku_id=sku.id, on_hand=Decimal("0"), unit="btl"))
            session.add(
                ListItem(
                    venue_id=house.venue_id,
                    list_id=listing.id,
                    sku_id=sku.id,
                    bottle_price=price,
                    cost=1000,
                    currency="USD",
                )
            )
            created.append(sku.barcode)
        session.commit()
        for barcode in created:
            apply_count(session, house.venue_id, barcode, 20)
        session.commit()
    finally:
        session.close()
    payload = build(today)
    push = next(card for card in payload["briefing"]["cards"] if card["kind"] == "push")
    assert push["items"][0]["title"] == "Loud Push Chardonnay"
    assert "margin" not in push["body"].lower()
    assert "$" not in push["body"]
    session = SessionLocal()
    try:
        for sku in session.scalars(select(Sku).where(Sku.venue_id == house.venue_id, Sku.barcode.in_(created))).all():
            sku.variant.drink_by_year = None
        session.commit()
    finally:
        session.close()


def test_staff_briefing_has_no_cost_or_margin(house, monkeypatch):
    set_clock(lambda: _utc(2026, 11, 24, 23, 30))
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "ana")
        response = client.get("/tonight/briefing")
        assert response.status_code == 200, response.text
        blob = response.text.lower()
        assert "margin" not in blob
        assert "cost" not in blob
        assert "$" not in response.text


def test_live_intro_failure_does_not_store_a_fixture(house, monkeypatch):
    set_clock(lambda: _utc(2026, 8, 4, 23, 30))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-not-a-fixture")
    monkeypatch.setattr("madira.domain.training.briefing.live_complete", _boom)
    with pytest.raises(DraftFailed):
        build(date(2026, 8, 4))
    session = SessionLocal()
    try:
        row = session.scalar(
            select(Briefing).where(Briefing.venue_id == house.venue_id, Briefing.service_date == date(2026, 8, 4))
        )
        assert row is None
    finally:
        session.close()


def test_cards_include_menu_specials_arrivals_pairings_and_the_86_list(house):
    service = date(2026, 11, 24)
    set_clock(lambda: _utc(2026, 11, 24, 23, 30))
    session = SessionLocal()
    menu_id = None
    receipt_id = None
    try:
        owner = house.user_id
        menu = Menu(venue_id=house.venue_id, name="Tonight service menu", source_type="text", raw_text="crab")
        session.add(menu)
        session.flush()
        menu_id = menu.id
        version = MenuVersion(
            venue_id=house.venue_id,
            menu_id=menu.id,
            number=1,
            source_type="text",
            status="confirmed",
            confirmed_by=owner,
            confirmed_at=_utc(2099, 1, 1, 0, 0),
            raw_text="crab",
        )
        session.add(version)
        session.flush()
        dish = Dish(
            venue_id=house.venue_id,
            menu_id=menu.id,
            menu_version_id=version.id,
            name="Dungeness crab",
            is_special=True,
        )
        session.add(dish)
        session.flush()
        sku = session.scalar(select(Sku).where(Sku.venue_id == house.venue_id, Sku.barcode == "W-CHA-01"))
        session.add(
            Pairing(
                venue_id=house.venue_id,
                dish_id=dish.id,
                sku_id=sku.id,
                slot="best_bottle",
                status="pinned",
                server_script="Pour the Chablis while the crab is still cold.",
                confidence="high",
            )
        )
        empty = session.scalar(select(Sku).where(Sku.venue_id == house.venue_id, Sku.barcode == "W-BAR-01"))
        flagged = session.scalar(select(Sku).where(Sku.venue_id == house.venue_id, Sku.barcode == "W-COT-01"))
        flagged.eighty_sixed_at = _utc(2026, 11, 24, 18, 0)
        flagged.eighty_sixed_by_user_id = owner
        supplier = session.scalar(select(Supplier).where(Supplier.venue_id == house.venue_id))
        order = PurchaseOrder(
            venue_id=house.venue_id,
            supplier_id=supplier.id,
            po_number=f"PO-BRIEF-{uuid.uuid4().hex[:6]}",
            status="received",
        )
        session.add(order)
        session.flush()
        receipt = Receipt(
            venue_id=house.venue_id,
            purchase_order_id=order.id,
            status="accepted",
            accepted_at=_utc(2026, 11, 22, 20, 0),
        )
        session.add(receipt)
        session.flush()
        receipt_id = receipt.id
        session.add(
            ReceiptLine(
                venue_id=house.venue_id,
                receipt_id=receipt.id,
                sku="W-CHA-01",
                product_name="Just-landed Chablis",
                ordered_qty=Decimal("6"),
                counted_qty=Decimal("6"),
            )
        )
        session.commit()
        apply_count(session, house.venue_id, "W-BAR-01", 0)
        session.commit()
        _ = empty
    finally:
        session.close()

    payload = build(service)
    cards = {card["kind"]: card for card in payload["briefing"]["cards"]}
    assert any(item["title"] == "Dungeness crab" for item in cards["menu"]["items"])
    assert any(item["title"] == "Dungeness crab" for item in cards["specials"]["items"])
    assert any(item["title"] == "Just-landed Chablis" for item in cards["arrivals"]["items"])
    assert any("Chablis" in item["detail"] for item in cards["pairings"]["items"])
    eighty = " ".join(item["title"] + " " + item["detail"] for item in cards["eighty_six"]["items"])
    assert "Barolo" in eighty
    assert "Côte" in eighty or "Cotie" in eighty or "W-COT" in eighty or "86'd" in eighty

    session = SessionLocal()
    try:
        if menu_id is not None:
            menu = session.get(Menu, menu_id)
            if menu is not None:
                session.delete(menu)
        if receipt_id is not None:
            receipt = session.get(Receipt, receipt_id)
            if receipt is not None:
                session.delete(receipt)
        flagged = session.scalar(select(Sku).where(Sku.venue_id == house.venue_id, Sku.barcode == "W-COT-01"))
        if flagged is not None:
            flagged.eighty_sixed_at = None
            flagged.eighty_sixed_by_user_id = None
        session.commit()
        apply_count(session, house.venue_id, "W-BAR-01", 9)
        session.commit()
    finally:
        session.close()
