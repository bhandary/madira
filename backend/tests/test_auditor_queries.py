"""Auditor queries stay in the venue, page their rows, and link to the source."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from madira.auth import SESSION_COOKIE, issue_session
from madira.db import SessionLocal, init_db
from madira.domain.compliance.queries import (
    audit_events,
    compliance_status,
    conditions,
    list_versions,
    pos_gaps,
    purchases,
    stock_movements,
)
from madira.domain.sensors.service import create_sensor
from madira.main import app
from madira.models import (
    BeverageList,
    ListVersion,
    Membership,
    PosConnection,
    PurchaseOrder,
    Receipt,
    StockMovement,
    StorageZone,
    Supplier,
    User,
    Venue,
)
from madira.seed import seed
from madira.tenancy import AUDITOR, MANAGER, STAFF, ensure_demo_tenant

AUTH_SECRET = "auditor-query-test-secret"


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _table(body: dict) -> dict:
    table = body["audit_table"]
    assert {"title", "columns", "rows", "totals", "page"} <= set(table)
    assert table["page"]["total"] >= len(table["rows"])
    assert table["page"]["limit"] >= 1
    for column in table["columns"]:
        assert column["type"] in {"text", "number", "money", "date"}
        assert column["key"] and column["label"]
    for row in table["rows"]:
        assert row["id"]
        assert isinstance(row["cells"], dict)
        assert row["links"]
        assert all(link["href"].startswith("/") and not link["href"].startswith("//") for link in row["links"])
    return table


def _every_row(fn, venue_id) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    total = 1
    while offset < total:
        table = fn(venue_id, limit=50, offset=offset)["audit_table"]
        rows.extend(table["rows"])
        total = table["page"]["total"]
        offset += 50
    return rows


def test_each_query_has_totals_and_source_links():
    demo = _demo()
    stock = _table(stock_movements(demo.venue_id, limit=1, offset=0))
    assert stock["page"]["limit"] == 1
    assert stock["totals"]["movement_count"] == stock["page"]["total"]
    assert stock["totals"]["movement_count"] > 1
    assert len(stock["rows"]) == 1
    assert stock["rows"][0]["links"][0]["href"].startswith("/inventory?sku=")
    barcode = stock["rows"][0]["cells"]["sku"]
    narrowed = _table(stock_movements(demo.venue_id, sku=barcode))
    assert narrowed["totals"]["movement_count"] >= 1
    assert all(row["cells"]["sku"] == barcode for row in narrowed["rows"])
    future = _table(stock_movements(demo.venue_id, start_date="2099-01-01", end_date="2099-01-02"))
    assert future["totals"]["movement_count"] == 0
    assert future["totals"]["depletion"] == 0

    side_id = uuid.uuid4()
    session = SessionLocal()
    try:
        home = session.get(Venue, demo.venue_id)
        session.add(
            Venue(
                id=side_id,
                organization_id=home.organization_id,
                name="Audit side room",
                slug=f"audit-side-{side_id.hex[:8]}",
                timezone="America/Los_Angeles",
                invite_delivery="draft_only",
                jurisdiction="US-CA",
            )
        )
        session.flush()
        zone = StorageZone(
            venue_id=side_id,
            name="Side cellar",
            target_temp_min_c=12,
            target_temp_max_c=14,
            target_humidity_min_pct=60,
            target_humidity_max_pct=75,
        )
        supplier = Supplier(venue_id=side_id, name=f"Audit supply {side_id.hex[:6]}")
        session.add_all([zone, supplier])
        session.commit()
        zone_id = zone.id
        supplier_id = supplier.id
    finally:
        session.close()
    created = create_sensor(
        side_id,
        name="Gap probe",
        zone_id=zone_id,
        metric="temperature_c",
        external_id=f"gap-{uuid.uuid4().hex[:8]}",
    )
    secret = created["secret"]
    session = SessionLocal()
    try:
        order = PurchaseOrder(
            venue_id=side_id,
            supplier_id=supplier_id,
            status="draft",
            subtotal_cents=2500,
            po_number=f"AQ-{uuid.uuid4().hex[:6]}",
        )
        session.add(order)
        session.flush()
        session.add(Receipt(venue_id=side_id, purchase_order_id=order.id, status="draft"))
        listed = BeverageList(venue_id=side_id, name="Audit list", budget=0)
        session.add(listed)
        session.flush()
        token = uuid.uuid4().hex
        session.add(
            ListVersion(
                venue_id=side_id,
                list_id=listed.id,
                number=1,
                status="published",
                public_token=token,
            )
        )
        session.add(PosConnection(venue_id=side_id, provider="demo", status="active", location_id="bar", location_name="Bar"))
        session.commit()
        order_id = str(order.id)
    finally:
        session.close()

    condition = _table(conditions(side_id, limit=50))
    condition_rows = _every_row(conditions, side_id)
    assert condition["totals"]["sensor_gap_count"] >= 1
    assert condition["totals"]["excursion_count"] == 0
    assert any(row["cells"]["kind"] == "sensor_gap" and row["links"][0]["href"] == "/sensors" for row in condition_rows)
    assert secret not in json.dumps(condition_rows)

    status = _table(compliance_status(demo.venue_id))
    assert status["totals"]["license_count"] >= 1
    assert status["totals"]["reminder_count"] >= 1
    assert any(row["cells"]["kind"] == "license" and any(link["href"].startswith("/records") for link in row["links"]) for row in status["rows"])
    assert "mailto" not in json.dumps(status)

    gaps = _table(pos_gaps(side_id))
    assert gaps["totals"]["gap_count"] >= 1
    assert gaps["totals"]["unmapped_count"] == 0
    assert gaps["rows"][0]["links"][0]["href"] == "/pos"

    versions = _table(list_versions(side_id))
    assert versions["totals"]["version_count"] == 1
    assert versions["totals"]["published_count"] == 1
    assert any(link["href"] == f"/l/{token}" for row in versions["rows"] for link in row["links"])
    assert any(link["href"] == "/list" for row in versions["rows"] for link in row["links"])

    bought = _table(purchases(side_id))
    assert bought["totals"]["order_cents"] == 2500
    assert bought["totals"]["order_count"] == 1
    assert bought["totals"]["receipt_count"] == 1
    assert any(row["id"] == f"po-{order_id}" and row["cells"]["amount_cents"] == 2500 for row in bought["rows"])
    assert any(link["href"] == f"/purchasing?po={order_id}" for row in bought["rows"] for link in row["links"])

    events = _table(audit_events(demo.venue_id))
    assert events["totals"]["event_count"] >= 1
    action = events["rows"][0]["cells"]["action"]
    filtered = _table(audit_events(demo.venue_id, action=action))
    assert filtered["totals"]["event_count"] >= 1
    assert all(row["cells"]["action"] == action for row in filtered["rows"])
    assert _table(audit_events(demo.venue_id, actor="nobody-at-all@example.com"))["totals"]["event_count"] == 0
    assert events["rows"][0]["links"][0]["href"] == "/records"


def test_queries_do_not_cross_venues():
    demo = _demo()
    other_id = uuid.uuid4()
    session = SessionLocal()
    try:
        home = session.get(Venue, demo.venue_id)
        session.add(
            Venue(
                id=other_id,
                organization_id=home.organization_id,
                name="Other room",
                slug=f"other-{other_id.hex[:8]}",
                timezone="America/Los_Angeles",
                invite_delivery="draft_only",
                jurisdiction="US-CA",
            )
        )
        session.commit()
        demo_count = session.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.venue_id == demo.venue_id))
    finally:
        session.close()
    assert demo_count > 0
    assert stock_movements(other_id)["audit_table"]["totals"]["movement_count"] == 0
    assert compliance_status(other_id)["audit_table"]["totals"]["license_count"] == 0


def test_query_routes_follow_records_and_reject_staff(monkeypatch):
    demo = _demo()
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    suffix = uuid.uuid4().hex[:8]
    session = SessionLocal()
    try:
        def add(role: str) -> str:
            sub = f"audit-{role.lower()}-{suffix}"
            user = User(
                google_sub=sub,
                email=f"{sub}@example.com",
                name=sub,
                picture="",
                created_at=datetime.now(timezone.utc),
                last_login_at=datetime.now(timezone.utc),
            )
            session.add(user)
            session.flush()
            session.add(Membership(user_id=user.id, venue_id=demo.venue_id, role=role))
            return sub

        staff = add(STAFF)
        auditor = add(AUDITOR)
        manager = add(MANAGER)
        session.commit()
    finally:
        session.close()
    paths = [
        "/compliance/queries/stock",
        "/compliance/queries/conditions",
        "/compliance/queries/compliance",
        "/compliance/queries/pos",
        "/compliance/queries/lists",
        "/compliance/queries/purchases",
        "/compliance/queries/events",
    ]
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, issue_session(staff))
        for path in paths:
            assert client.get(path).status_code == 403
        assert client.get("/usage").status_code == 403
        client.cookies.set(SESSION_COOKIE, issue_session(auditor))
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, path
            _table(response.json())
        assert client.get("/usage").status_code == 200
        assert client.put("/usage/limits", json={"monthly_spend_cap_cents": 100, "requests_per_minute": 10}).status_code == 403
        client.cookies.set(SESSION_COOKIE, issue_session(manager))
        assert client.get("/compliance/queries/stock").status_code == 200
        assert client.put("/usage/limits", json={"monthly_spend_cap_cents": 100, "requests_per_minute": None}).status_code == 403
        client.cookies.delete(SESSION_COOKIE)
        saved = client.put("/usage/limits", json={"monthly_spend_cap_cents": None, "requests_per_minute": None})
        assert saved.status_code == 200, saved.text
        assert saved.json()["can_edit"] is True
        assert saved.json()["monthly_spend_cap_cents"] is None
