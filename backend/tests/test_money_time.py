"""Minor-unit money, rounding, and timezone-aware tasting times."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select, text

from madira.db import SessionLocal, init_db
from madira.domain.procurement.service import build_ics
from madira.fixtures_data import curate_list
from madira.models import Supplier, Tasting
from madira.money import bottle_multiple, format_whole, pour_multiple, to_minor
from madira.seed import seed
from madira.tenancy import bind, ensure_demo_tenant, reset
from madira.timestamps import format_wall, parse_stamp

BACKEND = Path(__file__).resolve().parents[1]


def test_to_minor_rounds_half_away_from_zero():
    assert to_minor(0) == 0
    assert to_minor(1) == 100
    assert to_minor(18) == 1800
    assert to_minor(2.4) == 240
    assert to_minor(3.1) == 310
    assert to_minor(3.4) == 340
    assert to_minor("1.004") == 100
    assert to_minor("1.005") == 101
    assert to_minor(Decimal("1.225")) == 123
    assert to_minor(Decimal("1.235")) == 124
    assert to_minor(Decimal("-1.225")) == -123


def test_list_math_stays_in_minor_units_and_displays_the_same_dollars():
    payload = curate_list(budget=12000, target_margin=3.2)
    assert payload["budget"] == 1_200_000
    assert payload["currency"] == "USD"
    assert payload["spent"] == 519_760
    assert payload["remaining"] == 1_200_000 - 519_760
    assert payload["spent"] == sum(item["line_cost"] for item in payload["items"])
    assert payload["target_margin"] == 3.2
    assert "Buys stay at $5,198 of $12,000." in payload["notes"]
    assert "3.2x" in payload["notes"]
    muscadet = payload["items"][0]
    assert muscadet["cost"] == 1800
    assert muscadet["line_cost"] == 1800 * 12
    assert muscadet["pour_multiple"] == 4.44
    assert muscadet["margin_pct"] == 77.5
    kolsch = next(item for item in payload["items"] if item["name"] == "Kölsch")
    assert kolsch["cost"] == 240
    assert kolsch["line_cost"] == 240 * 24
    assert format_whole(payload["spent"]) == "5,198"
    assert format_whole(payload["budget"]) == "12,000"
    assert float(pour_multiple(1600, 1800)) == 4.44
    assert float(bottle_multiple(4800, 1800)) == 2.67


def test_purchase_line_total_is_an_integer_product():
    unit = to_minor(3.4)
    qty = 6
    assert unit * qty == 2040
    assert format_whole(unit * qty) == "20"


def test_tasting_clock_round_trips_and_ics_text_is_unchanged():
    init_db()
    seed()
    ctx = ensure_demo_tenant()
    token = bind(ctx)
    start = "2026-12-01T15:00"
    end = "2026-12-01T17:00"
    notes = "Draft hold — export .ics, do not send invites."
    title = "Clock round trip"
    location = "Maison Madira cellar"
    ics = build_ics(title, start, end, location, notes)
    session = SessionLocal()
    try:
        supplier = session.scalar(select(Supplier).where(Supplier.venue_id == ctx.venue_id))
        assert supplier is not None
        tasting = Tasting(
            venue_id=ctx.venue_id,
            supplier_id=supplier.id,
            title=title,
            starts_at=parse_stamp(start),
            ends_at=parse_stamp(end),
            location=location,
            notes=notes,
            ics=ics,
        )
        session.add(tasting)
        session.commit()
        tasting_id = tasting.id
    finally:
        session.close()
        reset(token)

    session = SessionLocal()
    try:
        loaded = session.get(Tasting, tasting_id)
        assert loaded is not None
        assert loaded.starts_at == parse_stamp(start)
        assert loaded.ends_at == parse_stamp(end)
        assert loaded.starts_at.tzinfo is not None
        assert loaded.starts_at.utcoffset() == timezone.utc.utcoffset(None)
        assert format_wall(loaded.starts_at) == start
        assert format_wall(loaded.ends_at) == end
        assert loaded.ics == ics
        assert loaded.ics == build_ics(title, format_wall(loaded.starts_at), format_wall(loaded.ends_at), location, notes)
        assert "DTSTART:20261201T1500" in loaded.ics
        assert "DTEND:20261201T1700" in loaded.ics
    finally:
        session.close()


def test_upgrade_from_tenancy_keeps_rows_then_round_trips_an_empty_database(tmp_path):
    db = tmp_path / "legacy.db"
    empty = tmp_path / "empty.db"
    script = r"""
import os
from sqlalchemy import create_engine, func, select, text
from alembic import command
from madira.db import _alembic_config
from madira.models import BeverageList, InventoryItem, Tasting, Venue
from madira.timestamps import parse_stamp

url = os.environ["DATABASE_URL"]
cfg = _alembic_config()
command.upgrade(cfg, "0002_tenancy")
engine = create_engine(url)
with engine.begin() as conn:
    if url.startswith("sqlite"):
        conn.execute(text("PRAGMA foreign_keys=ON"))
    venue_id = conn.execute(text("SELECT id FROM venues WHERE slug = 'maison-madira'")).scalar()
    org_id = conn.execute(text("SELECT id FROM organizations WHERE slug = 'maison-madira'")).scalar()
    conn.execute(
        text("INSERT INTO users (google_sub, email, name, picture) VALUES ('sub-1', 'a@b.c', 'A', '')")
    )
    user_id = conn.execute(text("SELECT id FROM users WHERE google_sub = 'sub-1'")).scalar()
    conn.execute(
        text("INSERT INTO memberships (user_id, venue_id, role) VALUES (:user_id, :venue_id, 'Owner')"),
        {"user_id": user_id, "venue_id": venue_id},
    )
    conn.execute(
        text(
            "INSERT INTO suppliers (name, kind, contact_email, notes, venue_id) "
            "VALUES ('Kermit Lynch Wine Merchant', 'importer', 't@example.com', '', :venue_id)"
        ),
        {"venue_id": venue_id},
    )
    supplier_id = conn.execute(text("SELECT id FROM suppliers")).scalar()
    conn.execute(
        text(
            "INSERT INTO inventory_items (sku, name, category, supplier_id, on_hand, par, unit_cost, depletion_30d, unit, venue_id) "
            "VALUES ('B-STT-01', 'Old Rasputin', 'beer', :supplier_id, 14, 12, 3.4, 16, 'btl', :venue_id)"
        ),
        {"supplier_id": supplier_id, "venue_id": venue_id},
    )
    conn.execute(
        text(
            "INSERT INTO beverage_lists (name, budget, target_margin, notes, venue_id) "
            "VALUES ('House list', 12000, 3.2, 'spot', :venue_id)"
        ),
        {"venue_id": venue_id},
    )
    conn.execute(
        text(
            "INSERT INTO tastings (supplier_id, title, starts_at, ends_at, location, notes, ics, venue_id) "
            "VALUES (:supplier_id, 'New Loire', '2026-12-01T15:00', '2026-12-01T17:00', 'cellar', 'n', 'BEGIN:VCALENDAR', :venue_id)"
        ),
        {"supplier_id": supplier_id, "venue_id": venue_id},
    )
    before = {
        name: conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
        for name in ("organizations", "venues", "users", "memberships", "suppliers", "inventory_items", "beverage_lists", "tastings")
    }
    assert before["organizations"] == 1
    assert before["inventory_items"] == 1
    assert org_id is not None

command.upgrade(cfg, "head")
from madira.db import SessionLocal
session = SessionLocal()
try:
    for model, count in (
        (Venue, before["venues"]),
        (InventoryItem, before["inventory_items"]),
        (BeverageList, before["beverage_lists"]),
        (Tasting, before["tastings"]),
    ):
        assert session.scalar(select(func.count()).select_from(model)) == count
    item = session.scalar(select(InventoryItem).where(InventoryItem.sku == "B-STT-01"))
    assert item.unit_cost == 340
    assert item.currency == "USD"
    assert item.venue_id == session.scalar(select(Venue.id).where(Venue.slug == "maison-madira"))
    listing = session.scalar(select(BeverageList))
    assert listing.budget == 1_200_000
    assert listing.currency == "USD"
    assert listing.target_margin == 3.2
    tasting = session.scalar(select(Tasting))
    assert tasting.starts_at == parse_stamp("2026-12-01T15:00")
    assert tasting.ends_at == parse_stamp("2026-12-01T17:00")
    assert tasting.ics == "BEGIN:VCALENDAR"
    assert tasting.venue_id == item.venue_id
    assert item.supplier_id is not None
finally:
    session.close()
"""
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = str(BACKEND)
    completed = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr

    empty_script = r"""
import os
from alembic import command
from madira.db import _alembic_config
cfg = _alembic_config()
command.upgrade(cfg, "head")
command.downgrade(cfg, "base")
command.upgrade(cfg, "head")
from sqlalchemy import create_engine, text
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    orgs = conn.execute(text("SELECT COUNT(*) FROM organizations")).scalar()
    suppliers = conn.execute(text("SELECT COUNT(*) FROM suppliers")).scalar()
assert version == "0003_uuid_money_time"
assert orgs == 1
assert suppliers == 0
"""
    env["DATABASE_URL"] = f"sqlite:///{empty}"
    completed = subprocess.run([sys.executable, "-c", empty_script], env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
