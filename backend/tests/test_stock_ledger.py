"""Stock ledger invariants, depletion, QR labels, RBAC, and the 0010 migration."""

from __future__ import annotations

import os
import random
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import DatabaseError

from madira.auth import issue_session, utcnow
from madira.domain.session import session_scope
from madira.domain.compliance.service import verify_audit_chain
from madira.domain.errors import NotFound
from madira.domain.inventory import ledger
from madira.domain.inventory.ledger import Rejected, as_qty
from madira.main import app
from madira.models import AuditEvent, InventoryItem, Membership, Sku, StockMovement, User
from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "stock-ledger-test-secret"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _venue():
    org_id = uuid.uuid4()
    venue_id = uuid.uuid4()
    with session_scope() as session:
        session.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"
            ),
            {"id": org_id.hex, "name": f"Ledger {org_id.hex[:6]}", "slug": f"ledger-{org_id.hex[:10]}"},
        )
        session.execute(
            sa.text(
                "INSERT INTO venues (id, organization_id, name, slug, currency) "
                "VALUES (:id, :org, :name, :slug, 'USD')"
            ),
            {
                "id": venue_id.hex,
                "org": org_id.hex,
                "name": "Ledger Cellar",
                "slug": f"ledger-{venue_id.hex[:10]}",
            },
        )
        session.commit()
    return venue_id


def _sku(venue_id, barcode: str, *, par: int = 6, cost: int = 1000) -> str:
    from madira.domain.catalog.service import ensure_sku

    with session_scope() as session:
        stock = ensure_sku(session, venue_id, category="wine", name=barcode, barcode=barcode, par=par, cost=cost)
        session.commit()
        return stock.barcode


def _location(venue_id, name: str, kind: str = "cellar") -> uuid.UUID:
    with session_scope() as session:
        place = ledger.ensure_location(session, venue_id, name, kind)
        session.commit()
        return place.id


def _sum(session, venue_id, sku_id=None) -> Decimal:
    stmt = sa.select(sa.func.coalesce(sa.func.sum(StockMovement.quantity), 0)).where(
        StockMovement.venue_id == venue_id
    )
    if sku_id is not None:
        stmt = stmt.where(StockMovement.sku_id == sku_id)
    return as_qty(session.scalar(stmt))


def _cache(session, venue_id, sku_id) -> Decimal:
    return as_qty(
        session.scalar(
            sa.select(InventoryItem.on_hand).where(
                InventoryItem.venue_id == venue_id, InventoryItem.sku_id == sku_id
            )
        )
    )


def test_depletion_uses_sales_inside_the_window_and_ignores_older_sales():
    venue_id = _venue()
    barcode = _sku(venue_id, f"DEP-{uuid.uuid4().hex[:8]}")
    cellar = _location(venue_id, "Main Cellar")
    now = _now()
    with session_scope() as session:
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("10"),
            movement_type="opening_balance",
            created_at=now - timedelta(days=40),
        )
        old = ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("-4"),
            movement_type="sale",
            created_at=now - timedelta(days=31),
        )
        recent = ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("-1.5"),
            movement_type="sale",
            created_at=now - timedelta(days=2),
        )
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("-9"),
            movement_type="breakage",
            created_at=now - timedelta(days=1),
        )
        sku_id = session.scalar(sa.select(Sku.id).where(Sku.barcode == barcode))
        assert ledger.depletion_by_sku(session, venue_id, now=now)[sku_id] == Decimal("1.5")
        session.commit()
        assert old.id != recent.id


def test_depletion_falls_back_to_counts_and_shrinkage_without_sales():
    venue_id = _venue()
    barcode = _sku(venue_id, f"SHR-{uuid.uuid4().hex[:8]}")
    cellar = _location(venue_id, "Main Cellar")
    bar = _location(venue_id, "Main Bar", "bar")
    now = _now()
    with session_scope() as session:
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("20"),
            movement_type="opening_balance",
            created_at=now - timedelta(days=40),
        )
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("-2"),
            movement_type="count_adjustment",
            created_at=now - timedelta(days=31),
        )
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("-2"),
            movement_type="count_adjustment",
            created_at=now - timedelta(days=3),
        )
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("1"),
            movement_type="count_adjustment",
            created_at=now - timedelta(days=2),
        )
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("-0.5"),
            movement_type="comp",
            created_at=now - timedelta(days=1),
        )
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("-1"),
            movement_type="breakage",
            created_at=now - timedelta(hours=4),
        )
        ledger.transfer_stock(
            session,
            venue_id=venue_id,
            sku=barcode,
            from_location_id=cellar,
            to_location_id=bar,
            quantity=Decimal("3"),
            created_at=now - timedelta(hours=2),
        )
        sku_id = session.scalar(sa.select(Sku.id).where(Sku.barcode == barcode))
        assert ledger.depletion_by_sku(session, venue_id, now=now)[sku_id] == Decimal("3.5")
        session.commit()


def test_random_movements_keep_the_cache_locations_and_audit_chain():
    venue_id = _venue()
    barcode = _sku(venue_id, f"RND-{uuid.uuid4().hex[:8]}")
    cellar = _location(venue_id, "Main Cellar")
    bar = _location(venue_id, "Main Bar", "bar")
    rng = random.Random(20261124)
    kinds = ["receive", "sale", "breakage", "comp", "count_adjustment", "return", "faulty_bottle", "transfer"]
    seen: dict[str, tuple] = {}
    with session_scope() as session:
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("40"),
            movement_type="opening_balance",
        )
        for _ in range(36):
            kind = rng.choice(kinds)
            qty = Decimal(rng.randint(1, 20)) / Decimal(10)
            before = _sum(session, venue_id)
            if kind == "transfer":
                ledger.transfer_stock(
                    session,
                    venue_id=venue_id,
                    sku=barcode,
                    from_location_id=cellar,
                    to_location_id=bar,
                    quantity=qty,
                )
                assert _sum(session, venue_id) == before
            else:
                signed = qty
                if kind in {"sale", "breakage", "comp", "faulty_bottle"}:
                    signed = -qty
                elif kind == "count_adjustment" and rng.random() < 0.5:
                    signed = -qty
                ledger.post_movement(
                    session,
                    venue_id=venue_id,
                    sku=barcode,
                    location_id=cellar if rng.random() < 0.6 else bar,
                    quantity=signed,
                    movement_type=kind,
                )
            for row in session.scalars(sa.select(StockMovement).where(StockMovement.venue_id == venue_id)):
                key = str(row.id)
                current = (as_qty(row.quantity), row.movement_type, str(row.sku_id))
                if key in seen:
                    assert seen[key] == current
                else:
                    seen[key] = current
        sku_id = session.scalar(sa.select(Sku.id).where(Sku.barcode == barcode))
        total = _sum(session, venue_id, sku_id)
        assert _cache(session, venue_id, sku_id) == total
        places = ledger.balances_by_sku(session, venue_id)[sku_id]
        assert sum(places.values(), Decimal("0")) == total
        chain = verify_audit_chain(session, venue_id)
        assert chain["valid"] is True
        movement_ids = {
            str(value)
            for value in session.scalars(sa.select(StockMovement.id).where(StockMovement.venue_id == venue_id))
        }
        audited = {
            str(row.entity_id)
            for row in session.scalars(
                sa.select(AuditEvent).where(AuditEvent.venue_id == venue_id, AuditEvent.entity_type == "stock_movement")
            )
        }
        assert movement_ids <= audited
        session.commit()


def test_the_ledger_rejects_updates_and_deletes():
    venue_id = _venue()
    barcode = _sku(venue_id, f"IMM-{uuid.uuid4().hex[:8]}")
    cellar = _location(venue_id, "Main Cellar")
    with session_scope() as session:
        movement = ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=cellar,
            quantity=Decimal("2"),
            movement_type="receive",
        )
        session.commit()
        movement_id = movement.id
        original = as_qty(movement.quantity)

    with session_scope() as session:
        row = session.get(StockMovement, movement_id)
        row.quantity = original + Decimal("1")
        with pytest.raises(DatabaseError):
            session.commit()
        session.rollback()
        fresh = session.get(StockMovement, movement_id)
        assert as_qty(fresh.quantity) == original
        session.delete(fresh)
        with pytest.raises(DatabaseError):
            session.commit()


def test_sign_rules_and_cross_venue_locations():
    venue_id = _venue()
    other = _venue()
    barcode = _sku(venue_id, f"SGN-{uuid.uuid4().hex[:8]}")
    cellar = _location(venue_id, "Main Cellar")
    foreign = _location(other, "Other Cellar")
    with session_scope() as session:
        with pytest.raises(Rejected):
            ledger.post_movement(
                session,
                venue_id=venue_id,
                sku=barcode,
                location_id=cellar,
                quantity=Decimal("-1"),
                movement_type="receive",
            )
        with pytest.raises(NotFound):
            ledger.post_movement(
                session,
                venue_id=venue_id,
                sku=barcode,
                location_id=foreign,
                quantity=Decimal("1"),
                movement_type="receive",
            )
        session.rollback()


def test_seeded_cellar_matches_the_demo_fixtures(tmp_path):
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "MADIRA_API_KEY"):
        env.pop(key, None)
    env["MADIRA_DEMO_MODE"] = "true"
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'seed.db'}"
    env["PYTHONPATH"] = "backend"
    script = """
import os
from decimal import Decimal
import sqlalchemy as sa
from madira.db import init_db
from madira.domain.session import session_scope
from madira.domain.compliance.service import verify_audit_chain
from madira.domain.inventory import ledger
from madira.domain.inventory.service import rows
from madira.models import Bin, Location, StockMovement
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant
from madira.agents.demo.fixtures import INVENTORY

init_db()
seed()
venue_id = ensure_demo_tenant().venue_id
with session_scope() as session:
    snapshot = {row["sku"]: row for row in rows(session, venue_id)}
    places = session.scalars(sa.select(Location).where(Location.venue_id == venue_id)).all()
    bins = session.scalars(sa.select(Bin).where(Bin.venue_id == venue_id)).all()
    assert {place.name for place in places} >= {"Main Cellar", "Main Bar", "Walk-In Cooler"}
    by_code = {row.code: row for row in bins}
    for code in ("CEL-A1", "CEL-A2", "BAR-01", "WLK-01"):
        assert by_code[code].qr_payload == f"madira:bin:{venue_id}:{code}"
    lows = 0
    for fixture in INVENTORY:
        row = snapshot[fixture["sku"]]
        assert Decimal(str(row["on_hand"])) == Decimal(fixture["on_hand"])
        assert Decimal(str(row["depletion_30d"])) == Decimal(fixture["depletion_30d"])
        assert row["reorder_qty"] == max(fixture["par"] - fixture["on_hand"], 0)
        assert sum((Decimal(str(place["quantity"])) for place in row["locations"]), Decimal(0)) == Decimal(fixture["on_hand"])
        if row["low"]:
            lows += 1
    assert lows == 9
    chain = verify_audit_chain(session, venue_id)
    assert chain["valid"] is True
    assert session.scalar(sa.select(sa.func.count()).select_from(StockMovement).where(StockMovement.venue_id == venue_id)) > 0
print("seed-ok")
"""
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "seed-ok" in proc.stdout


def test_migration_backfills_opening_balances(tmp_path):
    db = tmp_path / "migrate.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os, uuid
from decimal import Decimal
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "0009_audit_and_vault")
engine = sa.create_engine(os.environ["DATABASE_URL"])
org = uuid.uuid4()
venue = uuid.uuid4()
other = uuid.uuid4()
product = uuid.uuid4()
variant = uuid.uuid4()
sku = uuid.uuid4()
zero_sku = uuid.uuid4()
neg_sku = uuid.uuid4()
with engine.begin() as conn:
    demo = conn.execute(sa.text("SELECT id FROM venues WHERE slug = 'maison-madira'")).scalar_one()
    demo_org = conn.execute(sa.text("SELECT organization_id FROM venues WHERE id = :id"), {"id": demo}).scalar_one()
    conn.execute(sa.text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'Other', :slug)"), {"id": org.hex, "slug": "other-" + org.hex[:8]})
    conn.execute(
        sa.text("INSERT INTO venues (id, organization_id, name, slug, currency) VALUES (:id, :org, 'Other', :slug, 'USD')"),
        {"id": other.hex, "org": org.hex, "slug": "other-v-" + other.hex[:8]},
    )
    def catalog(venue_id, org_id, product_id, variant_id, sku_id, barcode, par):
        conn.execute(
            sa.text(
                "INSERT INTO products (id, organization_id, category, producer, name, region, country, style, grape, "
                "body, acidity, tannin, sweetness, oak, intensity, aroma_families) "
                "VALUES (:id, :org, 'wine', '', :name, '', '', '', '', '', '', '', '', '', '', '[]')"
            ),
            {"id": product_id.hex, "org": org_id, "name": barcode},
        )
        conn.execute(
            sa.text(
                "INSERT INTO product_variants (id, product_id, vintage, bottle_size) "
                "VALUES (:id, :product, '', '750ml')"
            ),
            {"id": variant_id.hex, "product": product_id.hex},
        )
        conn.execute(
            sa.text(
                "INSERT INTO skus (id, venue_id, product_variant_id, barcode, bin_label, par, cost, currency) "
                "VALUES (:id, :venue, :variant, :barcode, '', :par, 1800, 'USD')"
            ),
            {"id": sku_id.hex, "variant": variant_id.hex, "venue": venue_id, "barcode": barcode, "par": par},
        )
    catalog(demo, demo_org, product, variant, sku, "MIG-POS", 12)
    zero_product, zero_variant = uuid.uuid4(), uuid.uuid4()
    catalog(demo, demo_org, zero_product, zero_variant, zero_sku, "MIG-ZERO", 4)
    neg_product, neg_variant = uuid.uuid4(), uuid.uuid4()
    catalog(other.hex, org.hex, neg_product, neg_variant, neg_sku, "MIG-NEG", 2)
    conn.execute(
        sa.text(
            "INSERT INTO inventory_items (id, venue_id, sku_id, on_hand, depletion_30d, unit) "
            "VALUES (:id, :venue, :sku, :on_hand, :dep, 'btl')"
        ),
        {"id": uuid.uuid4().hex, "venue": demo, "sku": sku.hex, "on_hand": 14, "dep": 16},
    )
    conn.execute(
        sa.text(
            "INSERT INTO inventory_items (id, venue_id, sku_id, on_hand, depletion_30d, unit) "
            "VALUES (:id, :venue, :sku, 0, 1, 'btl')"
        ),
        {"id": uuid.uuid4().hex, "venue": demo, "sku": zero_sku.hex},
    )
    conn.execute(
        sa.text(
            "INSERT INTO inventory_items (id, venue_id, sku_id, on_hand, depletion_30d, unit) "
            "VALUES (:id, :venue, :sku, -2, 0, 'btl')"
        ),
        {"id": uuid.uuid4().hex, "venue": other.hex, "sku": neg_sku.hex},
    )

command.upgrade(cfg, "head")
with engine.begin() as conn:
    cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(inventory_items)"))}
    assert "depletion_30d" not in cols
    movements = conn.execute(sa.text("SELECT venue_id, sku_id, quantity, movement_type FROM stock_movements")).all()
    by_sku = {}
    for venue_id, sku_id, quantity, movement_type in movements:
        by_sku.setdefault(sku_id.replace("-", ""), []).append((Decimal(str(quantity)), movement_type))
    assert by_sku[sku.hex] == [(Decimal("14.00"), "opening_balance")] or by_sku[sku.hex] == [(Decimal("14"), "opening_balance")]
    assert zero_sku.hex not in by_sku
    assert by_sku[neg_sku.hex][0][0] == Decimal("-2.00") or by_sku[neg_sku.hex][0][0] == Decimal("-2")
    assert by_sku[neg_sku.hex][0][1] == "count_adjustment"
    cellars = conn.execute(sa.text("SELECT venue_id, name FROM locations")).all()
    assert any(name == "Main Cellar" for _, name in cellars)

command.downgrade(cfg, "0009_audit_and_vault")
command.upgrade(cfg, "head")
with engine.begin() as conn:
    total = conn.execute(sa.text("SELECT COALESCE(SUM(quantity), 0) FROM stock_movements WHERE sku_id = :sku"), {"sku": sku.hex}).scalar_one()
    cached = conn.execute(sa.text("SELECT on_hand FROM inventory_items WHERE sku_id = :sku"), {"sku": sku.hex}).scalar_one()
    assert Decimal(str(total)) == Decimal(str(cached)) == Decimal("14")
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout


def _cookie(client, monkeypatch, role: str) -> None:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    demo = ensure_demo_tenant()
    sub = f"ledger-{role.lower()}-{uuid.uuid4().hex[:8]}"
    now = utcnow()
    with session_scope() as session:
        user = User(google_sub=sub, email=f"{sub}@example.com", name=role, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, venue_id=demo.venue_id, role=role))
        session.commit()
    client.cookies.set("madira_session", issue_session(sub))


def test_inventory_api_locations_bins_qr_and_isolation(client):
    venue_id = ensure_demo_tenant().venue_id
    created = client.post("/inventory/locations", json={"name": f"Cage {uuid.uuid4().hex[:6]}", "kind": "storage"})
    assert created.status_code == 200, created.text
    location_id = created.json()["location"]["id"]
    listed = client.get("/inventory/locations")
    assert listed.status_code == 200
    assert any(row["id"] == location_id for row in listed.json()["locations"])

    other = _venue()
    foreign = str(_location(other, "Foreign"))
    missing = client.post(
        "/inventory/bins",
        json={"location_id": foreign, "code": "NOPE"},
    )
    assert missing.status_code == 404

    bin_code = f"QR{uuid.uuid4().hex[:6].upper()}"
    made = client.post("/inventory/bins", json={"location_id": location_id, "code": bin_code, "label": "Door"})
    assert made.status_code == 200, made.text
    body = made.json()["bin"]
    assert body["qr_payload"] == f"madira:bin:{venue_id}:{bin_code}"
    label = client.get(f"/inventory/bins/{body['id']}/qr")
    assert label.status_code == 200
    assert "image/svg+xml" in label.headers["content-type"]
    assert b"<svg" in label.content
    assert body["qr_payload"].encode() in label.content
    payload = client.get(f"/inventory/bins/{body['id']}/qr", params={"format": "json"})
    assert payload.json()["qr_payload"] == body["qr_payload"]
    assert "<svg" in payload.json()["svg"]
    assert client.get(f"/inventory/bins/{uuid.uuid4()}/qr").status_code == 404

    bad = client.post(
        "/inventory/movements",
        json={"sku": "W-MUS-01", "location_id": location_id, "quantity": 1, "movement_type": "sale"},
    )
    assert bad.status_code == 422
    good = client.post(
        "/inventory/movements",
        json={
            "sku": "W-MUS-01",
            "location_id": location_id,
            "quantity": "-0.5",
            "movement_type": "sale",
            "reason": "By the glass",
        },
    )
    assert good.status_code == 200, good.text
    assert good.json()["movement"]["quantity"] == -0.5
    found = client.get("/inventory/movements", params={"sku": "W-MUS-01", "movement_type": "sale", "location_id": location_id})
    assert found.status_code == 200
    assert any(row["reason"] == "By the glass" for row in found.json()["movements"])
    assert client.get("/inventory/movements", params={"location_id": foreign}).status_code == 404

    places = client.get("/inventory/locations").json()["locations"]
    names = {row["name"]: row["id"] for row in places}
    before = next(row for row in client.get("/inventory").json()["items"] if row["sku"] == "W-MUS-01")
    moved = client.post(
        "/inventory/transfers",
        json={
            "sku": "W-MUS-01",
            "from_location_id": names["Main Cellar"],
            "to_location_id": names["Main Bar"],
            "quantity": "1",
        },
    )
    assert moved.status_code == 200, moved.text
    after = next(row for row in client.get("/inventory").json()["items"] if row["sku"] == "W-MUS-01")
    assert after["on_hand"] == before["on_hand"]
    before_places = {row["location_name"]: row["quantity"] for row in before["locations"]}
    after_places = {row["location_name"]: row["quantity"] for row in after["locations"]}
    assert after_places["Main Cellar"] == before_places["Main Cellar"] - 1
    assert after_places["Main Bar"] == before_places["Main Bar"] + 1
    assert after["depletion_30d"] == before["depletion_30d"]
    assert "valuation_cents" in after


def test_count_decrement_draws_stock_without_going_negative():
    venue_id = _venue()
    barcode = _sku(venue_id, f"NEG-{uuid.uuid4().hex[:8]}")
    cellar = _location(venue_id, "Main Cellar", "cellar")
    bar = _location(venue_id, "Main Bar", "bar")
    walk_in = _location(venue_id, "Walk-In Cooler", "walk_in")
    with session_scope() as session:
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=bar,
            quantity=Decimal("2"),
            movement_type="opening_balance",
        )
        ledger.post_movement(
            session,
            venue_id=venue_id,
            sku=barcode,
            location_id=walk_in,
            quantity=Decimal("2"),
            movement_type="opening_balance",
        )
        session.commit()
        sku_id = session.scalar(sa.select(Sku.id).where(Sku.venue_id == venue_id, Sku.barcode == barcode))
        ledger.apply_count(session, venue_id, barcode, 1)
        session.commit()
        places = ledger.balances_by_sku(session, venue_id)[sku_id]
        assert places.get(cellar, Decimal("0")) == Decimal("0")
        assert places[bar] == Decimal("0")
        assert places[walk_in] == Decimal("1")
        assert sum(places.values(), Decimal("0")) == Decimal("1")
        assert all(amount >= 0 for amount in places.values())
        adjustments = session.scalars(
            sa.select(StockMovement).where(
                StockMovement.venue_id == venue_id,
                StockMovement.sku_id == sku_id,
                StockMovement.movement_type == "count_adjustment",
            )
        ).all()
        assert {(row.location_id, as_qty(row.quantity)) for row in adjustments} == {
            (bar, Decimal("-2")),
            (walk_in, Decimal("-1")),
        }
        events = session.scalars(
            sa.select(AuditEvent)
            .where(AuditEvent.venue_id == venue_id, AuditEvent.action == "inventory.adjust")
            .order_by(AuditEvent.seq.asc())
        ).all()
        assert [event.before_json["on_hand"] for event in events] == [4, 4]
        assert [event.after_json["on_hand"] for event in events] == [1, 1]
        chain = verify_audit_chain(session, venue_id)
        assert chain["valid"] is True


def test_rbac_staff_cannot_read_and_auditor_cannot_write(client, monkeypatch):
    _cookie(client, monkeypatch, STAFF)
    assert client.get("/inventory").status_code == 403
    assert client.post("/inventory/locations", json={"name": "Nope", "kind": "other"}).status_code == 403
    _cookie(client, monkeypatch, AUDITOR)
    assert client.get("/inventory").status_code == 200
    assert client.get("/inventory/movements").status_code == 200
    assert client.post("/inventory/locations", json={"name": "Nope", "kind": "other"}).status_code == 403
    assert client.patch("/inventory/W-MUS-01", json={"on_hand": 4}).status_code == 403
    _cookie(client, monkeypatch, MANAGER)
    assert client.post("/inventory/locations", json={"name": f"Mgr {uuid.uuid4().hex[:4]}", "kind": "other"}).status_code == 200
    _cookie(client, monkeypatch, SOMMELIER)
    assert client.get("/inventory/locations").status_code == 200
    _cookie(client, monkeypatch, OWNER)
    patched = client.patch("/inventory/W-MUS-01", json={"on_hand": 4})
    assert patched.status_code == 200, patched.text
    with session_scope() as session:
        chain = verify_audit_chain(session, ensure_demo_tenant().venue_id)
    assert chain["valid"] is True
