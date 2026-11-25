"""Pricing rules are integer cents. Margin is computed when a list row is read."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from madira.db import SessionLocal, init_db
from madira.domain.lists.pricing import economics, price_for
from madira.domain.lists.service import curate, item_view
from madira.models import ListItem
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]


def test_default_bands_round_to_the_dollar():
    wine_low = price_for(1400, "wine")
    assert wine_low["bottle_price"] == 4900
    assert wine_low["glass_price"] == 1200
    assert economics(1400, 4900, 1200) == {"margin_pct": 71.4, "beverage_cost_pct": 28.6, "selling_price": 4900}

    assert price_for(1500, "wine")["bottle_price"] == 4500
    assert price_for(1500, "wine")["glass_price"] == 1100
    assert price_for(4000, "wine")["bottle_price"] == 10000
    assert price_for(4000, "wine")["glass_price"] == 2400
    assert price_for(10000, "wine")["bottle_price"] == 20000
    assert price_for(10000, "wine")["glass_price"] == 4800

    beer = price_for(240, "beer")
    assert beer["bottle_price"] == 700
    assert beer["glass_price"] == 200
    sake = price_for(3200, "sake")
    assert sake["bottle_price"] == 9600
    assert sake["glass_price"] == 2300
    spirit = price_for(2800, "spirit")
    assert spirit["bottle_price"] == 11200
    assert spirit["glass_price"] == 2200


def test_item_view_ignores_the_stored_margin():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    payload = curate(demo.venue_id, budget=12000, target_margin=3.2)
    session = SessionLocal()
    try:
        item = session.get(ListItem, payload["items"][0]["id"])
        item.margin_pct = 1
        session.commit()
        session.refresh(item)
        view = item_view(item)
    finally:
        session.close()
    priced = economics(view["cost"], view["bottle_price"], view["pour_price"])
    assert view["margin_pct"] == priced["margin_pct"]
    assert view["margin_pct"] != 1
    assert view["beverage_cost_pct"] == priced["beverage_cost_pct"]


def test_migration_0015_upgrades_downgrades_and_backfills(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0015_list_pricing_coverage.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0014_storage_zones"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert source.count('_enable_rls("') == 2
    assert "if not _is_postgres():" in source
    db = tmp_path / "pricing.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import uuid
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "0014_storage_zones")
engine = sa.create_engine(os.environ["DATABASE_URL"])
org = uuid.uuid4().hex
venue = uuid.uuid4().hex
product = uuid.uuid4().hex
variant = uuid.uuid4().hex
sku = uuid.uuid4().hex
beverage = uuid.uuid4().hex
item = uuid.uuid4().hex

def cols(conn, table):
    return list(conn.execute(sa.text(f"PRAGMA table_info({table})")))

def insert(conn, table, values):
    payload = {}
    for _cid, name, typ, notnull, default, pk in cols(conn, table):
        if name in values:
            payload[name] = values[name]
            continue
        if not notnull or default is not None or pk:
            continue
        kind = (typ or "").upper()
        if "INT" in kind or "NUM" in kind or "REAL" in kind or "FLOA" in kind:
            payload[name] = 0
        elif "JSON" in kind:
            payload[name] = "[]"
        else:
            payload[name] = ""
    names = ", ".join(payload)
    marks = ", ".join(f":{key}" for key in payload)
    conn.execute(sa.text(f"INSERT INTO {table} ({names}) VALUES ({marks})"), payload)

with engine.begin() as conn:
    insert(conn, "organizations", {"id": org, "name": "House", "slug": "house-pricing"})
    insert(conn, "venues", {"id": venue, "organization_id": org, "name": "House", "slug": "house-pricing", "currency": "USD"})
    insert(conn, "products", {"id": product, "organization_id": org, "category": "wine", "name": "House White", "producer": "House"})
    insert(conn, "product_variants", {"id": variant, "product_id": product, "vintage": "2022", "bottle_size": "750ml"})
    insert(conn, "skus", {"id": sku, "venue_id": venue, "product_variant_id": variant, "barcode": "HW-1", "cost": 1800, "currency": "USD"})
    insert(conn, "beverage_lists", {"id": beverage, "venue_id": venue, "name": "Old list", "budget": 100000, "currency": "USD", "target_margin": 3.2, "notes": ""})
    insert(conn, "list_items", {
        "id": item, "venue_id": venue, "list_id": beverage, "sku_id": sku,
        "section": "White", "position": 1, "cost": 1800, "pour_price": 1600, "bottle_price": 6200,
        "currency": "USD", "margin_pct": 70,
    })

command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0025_sensors_reminders"
    tables = set(sa.inspect(conn).get_table_names())
    assert {"pricing_rules", "list_sections"} <= tables
    section = conn.execute(sa.text("SELECT name, list_id FROM list_sections")).one()
    assert section.name == "White"
    linked = conn.execute(sa.text("SELECT section_id, section FROM list_items")).one()
    assert linked.section == "White"
    assert linked.section_id is not None
    lists = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(beverage_lists)"))}
    assert {"target_beverage_cost_pct", "concept", "price_tier"} <= lists
    zones = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(storage_zones)"))}
    assert "capacity_bottles" in zones
    variants = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(product_variants)"))}
    assert {"drink_from_year", "drink_by_year"} <= variants
    skus = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(skus)"))}
    assert "best_by" in skus

command.downgrade(cfg, "0014_storage_zones")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0014_storage_zones"
    tables = set(sa.inspect(conn).get_table_names())
    assert "pricing_rules" not in tables
    assert "list_sections" not in tables
    items = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(list_items)"))}
    assert "section_id" not in items
    assert "section" in items

command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0025_sensors_reminders"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
