"""Catalog: migration dedupes the three drink tables, SKUs stay in their venue, roles hold."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.auth import issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.catalog.service import ensure_sku
from madira.main import app
from madira.models import Membership, Sku, User, Venue
from madira.money import DEFAULT_CURRENCY
from madira.seed import seed
from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, ensure_demo_tenant

BACKEND = Path(__file__).resolve().parents[1]
AUTH_SECRET = "catalog-test-secret"


def test_migration_dedupes_duplicates_across_the_three_tables(tmp_path):
    db = tmp_path / "catalog.db"
    script = r"""
import uuid
from sqlalchemy import Integer, String, Uuid, create_engine, select, text
from sqlalchemy import Column, Float, Table, MetaData
from alembic import command
from madira.db import _alembic_config
from madira.models import InventoryItem, ListItem, Pairing, Product, Sku, Venue

cfg = _alembic_config()
command.upgrade(cfg, "0003_uuid_money_time")
engine = create_engine(__import__("os").environ["DATABASE_URL"])
meta = MetaData()
organizations = Table("organizations", meta, Column("id", Uuid), Column("name", String), Column("slug", String))
venues = Table(
    "venues", meta,
    Column("id", Uuid), Column("organization_id", Uuid), Column("name", String), Column("slug", String),
)
menus = Table(
    "menus", meta,
    Column("id", Uuid), Column("venue_id", Uuid), Column("name", String), Column("source_type", String),
    Column("raw_text", String), Column("cuisine", String), Column("price_tier", String),
)
dishes = Table(
    "dishes", meta,
    Column("id", Uuid), Column("venue_id", Uuid), Column("menu_id", Uuid), Column("name", String),
    Column("course", String), Column("description", String), Column("flavor_profile", String),
    Column("price", Integer), Column("currency", String),
)
lists = Table(
    "beverage_lists", meta,
    Column("id", Uuid), Column("venue_id", Uuid), Column("name", String), Column("budget", Integer),
    Column("currency", String), Column("target_margin", Float), Column("notes", String),
)
pairings = Table(
    "pairings", meta,
    Column("id", Uuid), Column("venue_id", Uuid), Column("dish_id", Uuid), Column("category", String),
    Column("name", String), Column("producer", String), Column("region", String), Column("style", String),
    Column("vintage", String), Column("rationale", String), Column("price_tier", String),
    Column("glass_price", Integer), Column("bottle_price", Integer), Column("currency", String),
)
list_items = Table(
    "list_items", meta,
    Column("id", Uuid), Column("venue_id", Uuid), Column("list_id", Uuid), Column("category", String),
    Column("name", String), Column("producer", String), Column("region", String), Column("style", String),
    Column("vintage", String), Column("cost", Integer), Column("pour_price", Integer),
    Column("bottle_price", Integer), Column("currency", String), Column("margin_pct", Float),
)
inventory = Table(
    "inventory_items", meta,
    Column("id", Uuid), Column("venue_id", Uuid), Column("sku", String), Column("name", String),
    Column("category", String), Column("on_hand", Integer), Column("par", Integer),
    Column("unit_cost", Integer), Column("currency", String), Column("depletion_30d", Integer),
    Column("unit", String),
)

def uid(value):
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))

with engine.begin() as conn:
    conn.execute(text("PRAGMA foreign_keys=ON"))
    org_a = uid(conn.execute(text("SELECT id FROM organizations WHERE slug = 'maison-madira'")).scalar())
    venue_a = uid(conn.execute(text("SELECT id FROM venues WHERE slug = 'maison-madira'")).scalar())
    org_c = uuid.uuid4()
    venue_b = uuid.uuid4()
    venue_c = uuid.uuid4()
    conn.execute(organizations.insert(), {"id": org_c, "name": "Other Org", "slug": "other-org"})
    conn.execute(venues.insert(), [
        {"id": venue_b, "organization_id": org_a, "name": "Catalog B", "slug": "catalog-b"},
        {"id": venue_c, "organization_id": org_c, "name": "Catalog C", "slug": "catalog-c"},
    ])

    def menu_for(venue_id):
        menu_id = uuid.uuid4()
        dish_id = uuid.uuid4()
        conn.execute(menus.insert(), {
            "id": menu_id, "venue_id": venue_id, "name": "menu", "source_type": "text",
            "raw_text": "", "cuisine": "", "price_tier": "",
        })
        conn.execute(dishes.insert(), {
            "id": dish_id, "venue_id": venue_id, "menu_id": menu_id, "name": "dish",
            "course": "", "description": "", "flavor_profile": "", "price": 0, "currency": "USD",
        })
        return dish_id

    dish_a = menu_for(venue_a)
    dish_b = menu_for(venue_b)
    dish_c = menu_for(venue_c)
    list_a = uuid.uuid4()
    conn.execute(lists.insert(), {
        "id": list_a, "venue_id": venue_a, "name": "list", "budget": 0,
        "currency": "USD", "target_margin": 1, "notes": "",
    })

    def pairing(venue_id, dish_id, *, name, producer, region, style, vintage, rationale):
        conn.execute(pairings.insert(), {
            "id": uuid.uuid4(), "venue_id": venue_id, "dish_id": dish_id, "category": "wine",
            "name": name, "producer": producer, "region": region, "style": style, "vintage": vintage,
            "rationale": rationale, "price_tier": "$$", "glass_price": 1600, "bottle_price": 6200,
            "currency": "USD",
        })

    def list_item(name, producer, region, style, vintage, cost):
        conn.execute(list_items.insert(), {
            "id": uuid.uuid4(), "venue_id": venue_a, "list_id": list_a, "category": "wine",
            "name": name, "producer": producer, "region": region, "style": style, "vintage": vintage,
            "cost": cost, "pour_price": 1600, "bottle_price": 6200, "currency": "USD", "margin_pct": 70,
        })

    def stock(venue_id, code, name, on_hand, par, cost):
        conn.execute(inventory.insert(), {
            "id": uuid.uuid4(), "venue_id": venue_id, "sku": code, "name": name, "category": "wine",
            "on_hand": on_hand, "par": par, "unit_cost": cost, "currency": "USD",
            "depletion_30d": 1, "unit": "btl",
        })

    shared = dict(name="Shared Bottle", producer="House", region="Loire", style="Melon", vintage="2022")
    pairing(venue_a, dish_a, rationale="shared-a", **shared)
    pairing(venue_a, dish_a, rationale="shared-a", **shared)
    pairing(venue_b, dish_b, rationale="shared-b", **shared)
    pairing(venue_c, dish_c, rationale="shared-c", **shared)
    list_item(cost=500, **shared)
    stock(venue_a, "AAA", "Shared Bottle", 7, 4, 1250)
    stock(venue_b, "BBB", "Shared Bottle", 3, 2, 800)
    twin = dict(name="Twin", producer="House", region="Loire", style="Melon", vintage="2020")
    pairing(venue_a, dish_a, rationale="twin-a", **twin)
    list_item(cost=111, **twin)
    pairing(venue_a, dish_a, name="Solo", producer="Other", region="", style="", vintage="nv", rationale="solo-a")

command.upgrade(cfg, "head")
from madira.db import SessionLocal
from sqlalchemy import func, inspect

def counts():
    session = SessionLocal()
    try:
        products = session.scalars(select(Product)).all()
        assert len(products) == 4, [row.name for row in products]
        assert session.scalar(select(func.count()).select_from(Product)) == 4
        venue_a = session.scalar(select(Venue).where(Venue.slug == "maison-madira"))
        venue_b = session.scalar(select(Venue).where(Venue.slug == "catalog-b"))
        venue_c = session.scalar(select(Venue).where(Venue.slug == "catalog-c"))
        shared = [row for row in products if row.name == "Shared Bottle" and row.organization_id == venue_a.organization_id]
        assert len(shared) == 1
        assert shared[0].producer == "House"
        assert shared[0].region == "Loire"
        assert shared[0].style == "Melon"
        assert shared[0].body == ""
        assert shared[0].aroma_families == []
        assert len(shared[0].variants) == 1
        assert shared[0].variants[0].vintage == "2022"
        assert shared[0].variants[0].bottle_size == ""
        by_venue = {sku.venue_id: sku for sku in shared[0].variants[0].skus}
        assert set(by_venue) == {venue_a.id, venue_b.id}
        assert by_venue[venue_a.id].barcode == "AAA"
        assert by_venue[venue_a.id].par == 4
        assert by_venue[venue_a.id].cost == 1250
        assert by_venue[venue_a.id].currency == "USD"
        assert by_venue[venue_b.id].barcode == "BBB"
        assert by_venue[venue_b.id].par == 2
        assert by_venue[venue_b.id].cost == 800
        pairings_a = session.scalars(select(Pairing).where(Pairing.rationale == "shared-a")).all()
        assert len(pairings_a) == 2
        assert {row.sku_id for row in pairings_a} == {by_venue[venue_a.id].id}
        listed = session.scalar(select(ListItem).where(ListItem.cost == 500))
        assert listed.sku_id == by_venue[venue_a.id].id
        on_hand = session.scalar(select(InventoryItem).where(InventoryItem.sku_id == by_venue[venue_a.id].id))
        assert on_hand.on_hand == 7
        assert on_hand.unit == "btl"
        other_org = [row for row in products if row.name == "Shared Bottle" and row.organization_id == venue_c.organization_id]
        assert len(other_org) == 1
        assert other_org[0].id != shared[0].id
        pairing_c = session.scalar(select(Pairing).where(Pairing.rationale == "shared-c"))
        assert pairing_c.sku_id != by_venue[venue_a.id].id
        assert pairing_c.sku.venue_id == venue_c.id
        twin_rows = session.scalars(select(Pairing).where(Pairing.rationale == "twin-a")).all()
        twin_list = session.scalar(select(ListItem).where(ListItem.cost == 111))
        assert len(twin_rows) == 1
        assert twin_rows[0].sku_id == twin_list.sku_id
        assert twin_rows[0].sku.barcode == ""
        solo = session.scalar(select(Pairing).where(Pairing.rationale == "solo-a"))
        assert solo.sku_id not in {by_venue[venue_a.id].id, twin_rows[0].sku_id}
        columns = {col["name"] for col in inspect(session.connection()).get_columns("products")}
        assert "embedding" not in columns
        assert "name" not in {col["name"] for col in inspect(session.connection()).get_columns("pairings")}
        assert session.scalar(select(func.count()).select_from(Sku)) == 5
    finally:
        session.close()

counts()
command.downgrade(cfg, "0003_uuid_money_time")
with engine.connect() as conn:
    names = inspect(conn).get_table_names()
    assert "products" not in names
    assert "skus" not in names
    assert "product_variants" not in names
    restored = conn.execute(text(
        "SELECT name, producer, region, style, vintage FROM pairings WHERE rationale = 'shared-a'"
    )).all()
    assert len(restored) == 2
    assert all(tuple(row) == ("Shared Bottle", "House", "Loire", "Melon", "2022") for row in restored)
    cellars = conn.execute(text(
        "SELECT sku, name, on_hand, par, unit_cost, currency FROM inventory_items ORDER BY sku"
    )).all()
    assert ("AAA", "Shared Bottle", 7, 4, 1250, "USD") in [tuple(row) for row in cellars]
    assert ("BBB", "Shared Bottle", 3, 2, 800, "USD") in [tuple(row) for row in cellars]
    listed = conn.execute(text(
        "SELECT name, producer, vintage, cost FROM list_items WHERE cost = 500"
    )).one()
    assert tuple(listed) == ("Shared Bottle", "House", "2022", 500)

command.upgrade(cfg, "head")
counts()
"""
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = str(BACKEND)
    completed = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.fixture
def client():
    init_db()
    seed()
    with TestClient(app) as test_client:
        yield test_client


def _cookie(monkeypatch, google_sub: str) -> str:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    return issue_session(google_sub)


def _as(client: TestClient, monkeypatch, google_sub: str) -> None:
    client.cookies.set("madira_session", _cookie(monkeypatch, google_sub))


def _member(session, google_sub: str, email: str, venue_id, role: str) -> None:
    user = session.scalar(select(User).where(User.google_sub == google_sub))
    now = utcnow()
    if user is None:
        user = User(google_sub=google_sub, email=email, name=email, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
    membership = session.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id)
    )
    if membership is None:
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=role))
    else:
        membership.role = role


def test_two_venues_stay_isolated_for_skus(client: TestClient, monkeypatch):
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "catalog-other"))
        if venue is None:
            venue = Venue(organization_id=demo.organization_id, name="Catalog Other", slug="catalog-other")
            session.add(venue)
            session.flush()
        secret = ensure_sku(
            session,
            venue.id,
            category="wine",
            name="Cellar Secret",
            barcode="B-SECRET-99",
            par=3,
            cost=250,
            currency=DEFAULT_CURRENCY,
        )
        shared_a = ensure_sku(
            session,
            demo.venue_id,
            category="wine",
            name="Shared Pour",
            vintage="2021",
            barcode="A-SHARE",
            par=1,
            cost=100,
            currency=DEFAULT_CURRENCY,
            body="medium",
            acidity="high",
            tannin="low",
            sweetness="dry",
            oak="none",
            intensity="pronounced",
            aroma_families=["citrus", "saline"],
        )
        shared_b = ensure_sku(
            session,
            venue.id,
            category="wine",
            name="Shared Pour",
            vintage="2021",
            barcode="B-SHARE",
            par=2,
            cost=200,
            currency=DEFAULT_CURRENCY,
        )
        _member(session, "catalog-b-owner", "b@example.com", venue.id, OWNER)
        secret_id = secret.id
        secret_product_id = secret.variant.product_id
        shared_a_id = shared_a.id
        shared_b_id = shared_b.id
        session.commit()
    finally:
        session.close()

    listed = client.get("/skus")
    assert listed.status_code == 200
    codes = {row["barcode"] for row in listed.json()["skus"]}
    assert "W-MUS-01" in codes
    assert "A-SHARE" in codes
    assert "B-SHARE" not in codes
    assert "B-SECRET-99" not in codes
    assert client.get(f"/skus/{secret_id}").status_code == 404
    assert client.get(f"/skus/{shared_b_id}").status_code == 404

    products = client.get("/products")
    assert products.status_code == 200
    body = products.json()["products"]
    names = {row["name"] for row in body}
    assert "Muscadet Domaine de l'Ecu" in names
    assert "Shared Pour" in names
    assert "Cellar Secret" not in names
    assert client.get(f"/products/{secret_product_id}").status_code == 404
    shared = next(row for row in body if row["name"] == "Shared Pour")
    assert shared["body"] == "medium"
    assert shared["acidity"] == "high"
    assert shared["tannin"] == "low"
    assert shared["sweetness"] == "dry"
    assert shared["oak"] == "none"
    assert shared["intensity"] == "pronounced"
    assert shared["aroma_families"] == ["citrus", "saline"]
    assert {row["sku_id"] for row in shared["variants"]} == {str(shared_a_id)}
    assert "embedding" not in shared

    _as(client, monkeypatch, "catalog-b-owner")
    theirs = client.get("/skus")
    assert theirs.status_code == 200
    their_codes = {row["barcode"] for row in theirs.json()["skus"]}
    assert their_codes == {"B-SHARE", "B-SECRET-99"}
    assert client.get(f"/skus/{shared_a_id}").status_code == 404
    their_products = client.get("/products").json()["products"]
    assert {row["name"] for row in their_products} == {"Shared Pour", "Cellar Secret"}
    their_shared = next(row for row in their_products if row["name"] == "Shared Pour")
    assert {row["sku_id"] for row in their_shared["variants"]} == {str(shared_b_id)}


def test_catalog_endpoints_enforce_roles(client: TestClient, monkeypatch):
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        roles = {
            "catalog-owner": (OWNER, "catalog-owner@example.com"),
            "catalog-sommelier": (SOMMELIER, "catalog-sommelier@example.com"),
            "catalog-manager": (MANAGER, "catalog-manager@example.com"),
            "catalog-staff": (STAFF, "catalog-staff@example.com"),
            "catalog-auditor": (AUDITOR, "catalog-auditor@example.com"),
        }
        for sub, (role, email) in roles.items():
            _member(session, sub, email, demo.venue_id, role)
        stock = session.scalar(select(Sku).where(Sku.venue_id == demo.venue_id, Sku.barcode == "W-MUS-01"))
        sku_id = stock.id
        product_id = stock.variant.product_id
        session.commit()
    finally:
        session.close()

    def call(sub: str, path: str):
        _as(client, monkeypatch, sub)
        return client.get(path)

    assert call("catalog-staff", "/products").status_code == 200
    assert call("catalog-staff", f"/products/{product_id}").status_code == 200
    assert call("catalog-staff", "/skus").status_code == 403
    assert call("catalog-staff", f"/skus/{sku_id}").status_code == 403
    assert call("catalog-staff", "/skus").json()["detail"] == "This role cannot do that."

    assert call("catalog-auditor", "/products").status_code == 403
    assert call("catalog-auditor", f"/products/{product_id}").status_code == 403
    assert call("catalog-auditor", "/products").json()["detail"] == "This role cannot do that."
    assert call("catalog-auditor", "/skus").status_code == 200
    sku_body = call("catalog-auditor", f"/skus/{sku_id}")
    assert sku_body.status_code == 200
    assert sku_body.json()["barcode"] == "W-MUS-01"
    assert sku_body.json()["cost"] == 1800
    assert sku_body.json()["par"] == 12
    assert sku_body.json()["currency"] == "USD"
    assert sku_body.json()["name"] == "Muscadet Domaine de l'Ecu"

    for sub in ("catalog-owner", "catalog-sommelier", "catalog-manager"):
        assert call(sub, "/products").status_code == 200
        assert call(sub, f"/products/{product_id}").status_code == 200
        assert call(sub, "/skus").status_code == 200
        assert call(sub, f"/skus/{sku_id}").status_code == 200

    missing = call("catalog-owner", f"/products/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "product not found"
    missing_sku = call("catalog-owner", f"/skus/{uuid.uuid4()}")
    assert missing_sku.status_code == 404
    assert missing_sku.json()["detail"] == "sku not found"
