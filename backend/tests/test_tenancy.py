"""Venue isolation, role checks, the demo owner, owner-email bootstrap, and CORS."""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from madira.agents.tools import get_inventory, get_training_briefing, list_tastings, update_stock
from madira.auth import issue_session, upsert_google_user, utcnow
from madira.db import SessionLocal, engine
from madira.main import app
from madira.models import (
    BeverageList,
    Dish,
    InventoryItem,
    Lesson,
    ListItem,
    Membership,
    Menu,
    POLine,
    Pairing,
    PurchaseOrder,
    Quiz,
    QuizAttempt,
    Supplier,
    Tasting,
    User,
    Venue,
)
from madira.tenancy import (
    AUDITOR,
    MANAGER,
    OWNER,
    SOMMELIER,
    STAFF,
    RequestContext,
    bind,
    ensure_demo_tenant,
    reset,
)

AUTH_SECRET = "tenancy-test-secret"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _session_cookie(monkeypatch, google_sub: str) -> str:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    return issue_session(google_sub)


def _user(session, google_sub: str, email: str, venue_id: int, role: str) -> User:
    user = session.scalar(select(User).where(User.google_sub == google_sub))
    now = utcnow()
    if user is None:
        user = User(
            google_sub=google_sub,
            email=email,
            name=email,
            picture="",
            created_at=now,
            last_login_at=now,
        )
        session.add(user)
        session.flush()
    else:
        user.email = email
    membership = session.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id)
    )
    if membership is None:
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=role))
    else:
        membership.role = role
    session.commit()
    return user


def _plant_other_venue() -> dict:
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "other-house"))
        if venue is None:
            venue = Venue(organization_id=demo.organization_id, name="Other House", slug="other-house")
            session.add(venue)
            session.flush()
        supplier = session.scalar(select(Supplier).where(Supplier.venue_id == venue.id, Supplier.name == "Other House Wines"))
        if supplier is None:
            supplier = Supplier(
                venue_id=venue.id,
                name="Other House Wines",
                kind="importer",
                contact_email="other@example.com",
                notes="venue B",
            )
            session.add(supplier)
            session.flush()
        menu = session.scalar(select(Menu).where(Menu.venue_id == venue.id, Menu.name == "B secret menu"))
        if menu is None:
            menu = Menu(
                venue_id=venue.id,
                name="B secret menu",
                source_type="text",
                raw_text="secret",
                cuisine="secret",
                price_tier="$",
            )
            session.add(menu)
            session.flush()
            dish = Dish(
                venue_id=venue.id,
                menu_id=menu.id,
                name="B secret dish",
                course="main",
                description="",
                flavor_profile="",
                price=10,
            )
            session.add(dish)
            session.flush()
            pairing = Pairing(
                venue_id=venue.id,
                dish_id=dish.id,
                category="wine",
                name="B secret pairing",
                producer="",
                region="",
                style="",
                vintage="",
                rationale="secret",
                price_tier="$",
                glass_price=1,
                bottle_price=2,
            )
            session.add(pairing)
        else:
            dish = session.scalar(select(Dish).where(Dish.menu_id == menu.id))
            pairing = session.scalar(select(Pairing).where(Pairing.dish_id == dish.id))
        beverage_list = session.scalar(
            select(BeverageList).where(BeverageList.venue_id == venue.id, BeverageList.name == "B secret list")
        )
        if beverage_list is None:
            beverage_list = BeverageList(
                venue_id=venue.id,
                name="B secret list",
                budget=1,
                target_margin=1,
                notes="secret list",
            )
            session.add(beverage_list)
            session.flush()
            session.add(
                ListItem(
                    venue_id=venue.id,
                    list_id=beverage_list.id,
                    category="wine",
                    name="B secret bottle",
                    producer="",
                    region="",
                    style="",
                    vintage="",
                    cost=1,
                    pour_price=1,
                    bottle_price=1,
                    margin_pct=1,
                )
            )
        for sku, name, on_hand in (("B-ONLY-01", "B-SECRET-BOTTLE", 9), ("W-MUS-01", "B muscadet", 77)):
            item = session.scalar(
                select(InventoryItem).where(InventoryItem.venue_id == venue.id, InventoryItem.sku == sku)
            )
            if item is None:
                session.add(
                    InventoryItem(
                        venue_id=venue.id,
                        sku=sku,
                        name=name,
                        category="wine",
                        supplier_id=supplier.id,
                        on_hand=on_hand,
                        par=1,
                        unit_cost=1,
                        depletion_30d=0,
                        unit="btl",
                    )
                )
            else:
                item.on_hand = on_hand
                item.name = name
        order = session.scalar(
            select(PurchaseOrder).where(PurchaseOrder.venue_id == venue.id, PurchaseOrder.notes == "B secret order")
        )
        if order is None:
            order = PurchaseOrder(venue_id=venue.id, supplier_id=supplier.id, status="draft", notes="B secret order")
            session.add(order)
            session.flush()
            session.add(POLine(venue_id=venue.id, po_id=order.id, sku="B-ONLY-01", name="B-SECRET-BOTTLE", qty=1, unit_cost=1))
        lesson = session.scalar(select(Lesson).where(Lesson.venue_id == venue.id, Lesson.slug == "b-secret-lesson"))
        if lesson is None:
            lesson = Lesson(
                venue_id=venue.id,
                slug="b-secret-lesson",
                title="B secret lesson",
                role="waitstaff",
                category="wine",
                body="secret",
            )
            session.add(lesson)
            session.flush()
            quiz = Quiz(venue_id=venue.id, lesson_id=lesson.id, title="B secret quiz", questions=[])
            session.add(quiz)
            session.flush()
        else:
            quiz = session.scalar(select(Quiz).where(Quiz.venue_id == venue.id, Quiz.lesson_id == lesson.id))
        attempt = session.scalar(
            select(QuizAttempt).where(QuizAttempt.venue_id == venue.id, QuizAttempt.staff_name == "B secret staff")
        )
        if attempt is None:
            session.add(
                QuizAttempt(venue_id=venue.id, quiz_id=quiz.id, staff_name="B secret staff", answers=[], score=1)
            )
        tasting = session.scalar(select(Tasting).where(Tasting.venue_id == venue.id, Tasting.title == "B secret tasting"))
        if tasting is None:
            session.add(
                Tasting(
                    venue_id=venue.id,
                    supplier_id=supplier.id,
                    title="B secret tasting",
                    starts_at="2026-12-01T15:00",
                    ends_at="2026-12-01T17:00",
                    location="Other House",
                    notes="secret",
                    ics="BEGIN:VCALENDAR",
                )
            )
        user = _user(session, "venue-b-owner", "b@example.com", venue.id, OWNER)
        session.commit()
        pairing = session.scalar(select(Pairing).where(Pairing.venue_id == venue.id, Pairing.name == "B secret pairing"))
        return {
            "venue_id": venue.id,
            "organization_id": venue.organization_id,
            "user_id": user.id,
            "menu_id": menu.id,
            "list_id": beverage_list.id,
            "order_id": order.id,
            "tasting_id": tasting.id if tasting is not None else session.scalar(
                select(Tasting.id).where(Tasting.venue_id == venue.id, Tasting.title == "B secret tasting")
            ),
            "pairing_id": pairing.id,
            "demo": demo,
        }
    finally:
        session.close()


def _as(client: TestClient, monkeypatch, google_sub: str) -> None:
    client.cookies.set("madira_session", _session_cookie(monkeypatch, google_sub))


def test_two_venues_are_isolated(client: TestClient, monkeypatch):
    planted = _plant_other_venue()
    session = SessionLocal()
    try:
        house = session.scalar(select(InventoryItem).where(InventoryItem.venue_id == planted["demo"].venue_id, InventoryItem.sku == "W-MUS-01"))
        house_on_hand = house.on_hand
    finally:
        session.close()

    menus = client.get("/menus")
    assert menus.status_code == 200
    assert "B secret menu" not in menus.text
    assert client.get(f"/menus/{planted['menu_id']}").status_code == 404
    paired = client.post(f"/menus/{planted['menu_id']}/pair")
    assert paired.status_code == 404

    lists = client.get("/lists")
    assert lists.status_code == 200
    assert "B secret list" not in lists.text

    inventory = client.get("/inventory")
    assert inventory.status_code == 200
    assert "B-SECRET-BOTTLE" not in inventory.text
    assert "B muscadet" not in inventory.text
    missing = client.patch("/inventory/B-ONLY-01", json={"on_hand": 0})
    assert missing.status_code == 404
    patched = client.patch("/inventory/W-MUS-01", json={"on_hand": house_on_hand})
    assert patched.status_code == 200

    orders = client.get("/purchase-orders")
    assert orders.status_code == 200
    assert "B secret order" not in orders.text

    progress = client.get("/training/progress")
    assert progress.status_code == 200
    assert "B secret staff" not in progress.text

    tastings = client.get("/tastings")
    assert tastings.status_code == 200
    assert "B secret tasting" not in tastings.text
    assert client.get(f"/tastings/{planted['tasting_id']}/ics").status_code == 404

    session = SessionLocal()
    try:
        other = session.scalar(
            select(InventoryItem).where(InventoryItem.venue_id == planted["venue_id"], InventoryItem.sku == "W-MUS-01")
        )
        secret = session.scalar(
            select(InventoryItem).where(InventoryItem.venue_id == planted["venue_id"], InventoryItem.sku == "B-ONLY-01")
        )
        assert other.on_hand == 77
        assert secret.on_hand == 9
        pairing = session.get(Pairing, planted["pairing_id"])
        assert pairing is not None and pairing.name == "B secret pairing"
        removed = session.execute(
            delete(Pairing).where(Pairing.id == planted["pairing_id"], Pairing.venue_id == planted["demo"].venue_id)
        )
        renamed = session.execute(
            update(BeverageList)
            .where(BeverageList.id == planted["list_id"], BeverageList.venue_id == planted["demo"].venue_id)
            .values(name="hacked")
        )
        session.commit()
        assert removed.rowcount == 0
        assert renamed.rowcount == 0
        assert session.get(Pairing, planted["pairing_id"]) is not None
        assert session.get(BeverageList, planted["list_id"]).name == "B secret list"
    finally:
        session.close()

    _as(client, monkeypatch, "venue-b-owner")
    foreign = client.get("/menus")
    assert foreign.status_code == 200
    assert "B secret menu" in foreign.text
    assert client.get(f"/menus/{planted['menu_id']}").status_code == 200
    theirs = client.get("/inventory").json()
    names = {item["name"] for item in theirs["items"]}
    assert "B-SECRET-BOTTLE" in names
    assert "Muscadet Domaine de l'Ecu" not in names


def test_agent_tools_cannot_cross_venues(client: TestClient, monkeypatch):
    planted = _plant_other_venue()
    demo = planted["demo"]
    other = RequestContext(
        user_id=planted["user_id"],
        email="b@example.com",
        name="B",
        venue_id=planted["venue_id"],
        organization_id=planted["organization_id"],
        role=OWNER,
    )

    token = bind(demo)
    try:
        house = json.loads(get_inventory())
        assert "B-SECRET-BOTTLE" not in json.dumps(house)
        assert json.loads(update_stock("B-ONLY-01", 1))["error"]
        assert "B secret tasting" not in list_tastings()
        assert "b-secret-lesson" not in get_training_briefing()
    finally:
        reset(token)

    token = bind(other)
    try:
        cellar = json.loads(get_inventory())
        assert "B-SECRET-BOTTLE" in json.dumps(cellar)
        assert "Muscadet Domaine de l'Ecu" not in json.dumps(cellar)
        assert "B secret tasting" in list_tastings()
        changed = json.loads(update_stock("B-ONLY-01", 4))
        assert "error" not in changed
    finally:
        reset(token)

    session = SessionLocal()
    try:
        secret = session.scalar(
            select(InventoryItem).where(InventoryItem.venue_id == planted["venue_id"], InventoryItem.sku == "B-ONLY-01")
        )
        assert secret.on_hand == 4
        secret.on_hand = 0
        session.commit()
    finally:
        session.close()

    run = client.post("/agent/run", json={"message": "Draft a purchase order for low stock"})
    assert run.status_code == 200, run.text
    assert "B-SECRET-BOTTLE" not in run.text

    _as(client, monkeypatch, "venue-b-owner")
    other_run = client.post("/agent/run", json={"message": "Draft a purchase order for low stock"})
    assert other_run.status_code == 200, other_run.text
    assert "B-SECRET-BOTTLE" in other_run.text
    assert "Muscadet Domaine de l'Ecu" not in other_run.text


def test_no_session_outside_demo_mode_is_401(monkeypatch):
    monkeypatch.setenv("MADIRA_DEMO_MODE", "false")
    with TestClient(app) as fresh:
        fresh.cookies.clear()
        denied = fresh.get("/menus")
        assert denied.status_code == 401
        assert denied.json()["detail"] == "Sign in required."
        assert fresh.get("/settings/llm").status_code == 401
        assert fresh.post("/agent/run", json={"message": "hello"}).status_code == 401
        assert fresh.get("/health").status_code == 200
        assert fresh.get("/status").status_code == 200
        assert fresh.get("/fixtures/sample-menu").status_code == 200
        assert fresh.get("/auth/config").status_code == 200


def test_roles_follow_the_matrix(client: TestClient, monkeypatch):
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        roles = {
            "role-owner": (OWNER, "owner@example.com"),
            "role-sommelier": (SOMMELIER, "sommelier@example.com"),
            "role-manager": (MANAGER, "manager@example.com"),
            "role-staff": (STAFF, "staff@example.com"),
            "role-auditor": (AUDITOR, "auditor@example.com"),
        }
        for sub, (role, email) in roles.items():
            _user(session, sub, email, demo.venue_id, role)
        house = session.scalar(
            select(InventoryItem).where(InventoryItem.venue_id == demo.venue_id, InventoryItem.sku == "W-MUS-01")
        )
        on_hand = house.on_hand
    finally:
        session.close()

    def call(sub: str, method: str, path: str, **kwargs):
        _as(client, monkeypatch, sub)
        return getattr(client, method)(path, **kwargs)

    assert call("role-staff", "get", "/training").status_code == 200
    assert call("role-auditor", "get", "/training").status_code == 403

    assert call("role-staff", "patch", "/inventory/W-MUS-01", json={"on_hand": on_hand}).status_code == 403
    assert call("role-manager", "patch", "/inventory/W-MUS-01", json={"on_hand": on_hand}).status_code == 200

    assert call("role-manager", "post", "/lists/curate", json={"budget": 100, "target_margin": 3, "name": "nope"}).status_code == 403
    assert call("role-sommelier", "post", "/lists/curate", json={"budget": 100, "target_margin": 3, "name": "sommelier list"}).status_code == 200

    assert call("role-manager", "post", "/purchase-orders/draft").status_code == 403
    assert call("role-sommelier", "post", "/purchase-orders/draft").status_code == 200

    assert call("role-staff", "get", "/purchase-orders").status_code == 403
    assert call("role-auditor", "get", "/purchase-orders").status_code == 200

    assert call("role-sommelier", "get", "/settings/llm").status_code == 403
    assert call("role-owner", "get", "/settings/llm").status_code == 200


def test_owner_email_becomes_owner_on_the_default_venue(monkeypatch):
    monkeypatch.setenv("MADIRA_OWNER_EMAIL", "Ada@Restaurant.test")
    ensure_demo_tenant()
    upsert_google_user({"sub": "ada-sub", "email": "Ada@Restaurant.test", "name": "Ada", "picture": ""})
    upsert_google_user({"sub": "guest-sub", "email": "guest@restaurant.test", "name": "Guest", "picture": ""})

    session = SessionLocal()
    try:
        ada = session.scalar(select(User).where(User.google_sub == "ada-sub"))
        guest = session.scalar(select(User).where(User.google_sub == "guest-sub"))
        ada_role = session.scalar(select(Membership.role).where(Membership.user_id == ada.id))
        guest_role = session.scalar(select(Membership.role).where(Membership.user_id == guest.id))
        venue = session.scalar(select(Venue).where(Venue.slug == "maison-madira"))
        ada_venue = session.scalar(select(Membership.venue_id).where(Membership.user_id == ada.id))
        assert ada_role == OWNER
        assert ada_venue == venue.id
        assert guest_role is None

        staff = session.scalar(select(Membership).where(Membership.user_id == guest.id, Membership.venue_id == venue.id))
        if staff is None:
            session.add(Membership(user_id=guest.id, venue_id=venue.id, role=STAFF))
        else:
            staff.role = STAFF
        guest.email = "ada@restaurant.test"
        session.commit()
    finally:
        session.close()

    upsert_google_user({"sub": "guest-sub", "email": "ada@restaurant.test", "name": "Ada Two", "picture": ""})
    session = SessionLocal()
    try:
        guest = session.scalar(select(User).where(User.google_sub == "guest-sub"))
        role = session.scalar(select(Membership.role).where(Membership.user_id == guest.id))
        assert role == OWNER
    finally:
        session.close()


def test_cors_rejects_an_unlisted_origin(client: TestClient):
    from madira.config import FRONTEND_ORIGIN

    allowed = FRONTEND_ORIGIN.rstrip("/")
    evil = "https://evil.example"
    preflight = client.options(
        "/health",
        headers={"Origin": evil, "Access-Control-Request-Method": "GET"},
    )
    assert preflight.headers.get("access-control-allow-origin") != evil
    assert preflight.headers.get("access-control-allow-origin") != "*"
    simple = client.get("/health", headers={"Origin": evil})
    assert simple.status_code == 200
    assert simple.headers.get("access-control-allow-origin") != evil
    assert simple.headers.get("access-control-allow-origin") != "*"

    ok = client.options(
        "/health",
        headers={"Origin": allowed, "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers["access-control-allow-origin"] == allowed
    assert ok.headers["access-control-allow-credentials"] == "true"


def test_postgres_rls_hides_rows_when_the_setting_is_wrong():
    if engine.dialect.name != "postgresql":
        pytest.skip("row-level security is enforced on Postgres; SQLite relies on the venue filter")
    from sqlalchemy import text

    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        if session.scalar(select(Menu.id).where(Menu.venue_id == demo.venue_id)) is None:
            session.add(
                Menu(
                    venue_id=demo.venue_id,
                    name="RLS menu",
                    source_type="text",
                    raw_text="",
                    cuisine="",
                    price_tier="",
                )
            )
            session.commit()
    finally:
        session.close()

    autocommit = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        autocommit.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'madira_app') THEN
                        CREATE ROLE madira_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
                    END IF;
                END
                $$;
                """
            )
        )
        autocommit.execute(text("GRANT madira_app TO CURRENT_USER"))
        autocommit.execute(text("GRANT USAGE ON SCHEMA public TO madira_app"))
        autocommit.execute(text("GRANT SELECT ON menus TO madira_app"))
    finally:
        autocommit.close()

    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text("SET LOCAL ROLE madira_app"))
            conn.execute(text("SELECT set_config('app.venue_id', :venue_id, true)"), {"venue_id": "999999"})
            hidden = conn.execute(text("SELECT count(*) FROM menus")).scalar()
            print(f"RLS wrong app.venue_id count={hidden}")
            assert hidden == 0
            conn.execute(
                text("SELECT set_config('app.venue_id', :venue_id, true)"),
                {"venue_id": str(demo.venue_id)},
            )
            visible = conn.execute(text("SELECT count(*) FROM menus")).scalar()
            print(f"RLS matching app.venue_id count={visible}")
            assert visible >= 1
        finally:
            transaction.rollback()


def test_demo_mode_serves_the_floor_without_a_session(client: TestClient):
    assert os.environ.get("MADIRA_DEMO_MODE", "") == ""
    assert client.get("/inventory").status_code == 200
    assert "Muscadet" in client.get("/inventory").text
