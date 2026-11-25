"""Sourcing briefs come from list gaps. The model only phrases the rationale."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.errors import DraftFailed
from madira.domain.sourcing.service import build_brief, link_want_item
from madira.domain.tastings.service import add_sample, create_session
from madira.main import app
from madira.models import Membership, Supplier, SupplierOffer, User, Venue
from madira.seed import seed
from madira.tenancy import AUDITOR, MANAGER, STAFF, ensure_demo_tenant
from datetime import date
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "sourcing-brief-test-secret"


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _member(session, google_sub, email, venue_id, role):
    user = session.scalar(select(User).where(User.google_sub == google_sub))
    now = utcnow()
    if user is None:
        user = User(google_sub=google_sub, email=email, name=email, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
    membership = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id))
    if membership is None:
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=role))
    else:
        membership.role = role


def test_brief_uses_service_gaps_and_a_phrased_rationale():
    demo = _demo()
    session = SessionLocal()
    try:
        venue = Venue(organization_id=demo.organization_id, name="Gap Cellar", slug=f"gap-cellar-{uuid.uuid4().hex[:8]}")
        session.add(venue)
        session.commit()
        venue_id = venue.id
    finally:
        session.close()
    brief = build_brief(venue_id)["brief"]
    assert brief["title"] == "Sourcing brief"
    assert brief["status"] == "draft"
    assert len(brief["items"]) == 10
    for item in brief["items"]:
        assert item["category"] in {"wine", "beer", "spirits", "sake"}
        assert item["style"]
        assert item["quantity_hint"] == 12
        assert item["dishes"] == []
        assert "12" not in item["rationale"]
        assert item["style"] in item["rationale"]
        assert item["price_band"] in {"value", "mid", "reserve"}
    visible = build_brief(demo.venue_id)
    with TestClient(app) as client:
        listed = client.get("/sourcing/briefs")
        assert listed.status_code == 200
        assert listed.json()["briefs"][0]["id"] == visible["brief"]["id"]


def test_want_item_links_to_a_sample_and_an_offer():
    demo = _demo()
    brief = build_brief(demo.venue_id)["brief"]
    item_id = brief["items"][0]["id"]
    created = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title="Link tasting",
        starts_at="2026-12-09T15:00",
    )
    sample = add_sample(demo.venue_id, created["draft"]["id"])["sample"]
    session = SessionLocal()
    try:
        supplier = session.scalar(select(Supplier).where(Supplier.venue_id == demo.venue_id, Supplier.name == "Kermit Lynch Wine Merchant"))
        from madira.models import Product, ProductVariant, Sku

        product = Product(
            organization_id=demo.organization_id,
            category="wine",
            producer="Link House",
            name=f"Link bottle {uuid.uuid4().hex[:6]}",
        )
        session.add(product)
        session.flush()
        variant = ProductVariant(product_id=product.id, vintage="2022", bottle_size="750ml")
        session.add(variant)
        session.flush()
        sku = Sku(venue_id=demo.venue_id, product_variant_id=variant.id, barcode=f"LINK-{uuid.uuid4().hex[:8]}")
        session.add(sku)
        session.flush()
        offer = SupplierOffer(
            venue_id=demo.venue_id,
            supplier_id=supplier.id,
            product_id=product.id,
            sku_id=sku.id,
            price_cents=1500,
            currency="USD",
            valid_from=date(2026, 1, 1),
            source="manual",
        )
        session.add(offer)
        session.commit()
        offer_id = offer.id
    finally:
        session.close()
    linked = link_want_item(demo.venue_id, uuid.UUID(item_id), sample_id=sample["id"], offer_id=offer_id)
    found = next(row for row in linked["brief"]["items"] if row["id"] == item_id)
    assert found["sample_id"] == sample["id"]
    assert found["offer_id"] == str(offer_id)


def test_live_brief_does_not_use_the_demo_phrasing(monkeypatch):
    demo = _demo()
    session = SessionLocal()
    try:
        other = Venue(organization_id=demo.organization_id, name="Live Sourcing", slug=f"live-sourcing-{uuid.uuid4().hex[:8]}")
        session.add(other)
        session.commit()
        other_id = other.id
    finally:
        session.close()
    monkeypatch.delenv("MADIRA_DEMO_MODE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-not-a-fixture")
    from madira.llm_runtime import resolve_runtime

    assert resolve_runtime().demo_mode is False

    def explode(_prompt, *, kind):
        raise RuntimeError("connection refused")

    def demo_boom(_prompt):
        raise AssertionError("demo fixtures must not run when the model is live")

    monkeypatch.setattr("madira.domain.sourcing.service.live_complete", explode)
    monkeypatch.setattr("madira.domain.sourcing.service.demo_phrase", demo_boom)
    with pytest.raises(DraftFailed) as caught:
        build_brief(other_id)
    assert "RuntimeError" in caught.value.message
    assert "AssertionError" not in caught.value.message


def test_sourcing_roles_and_other_venues():
    demo = _demo()
    session = SessionLocal()
    try:
        other = Venue(organization_id=demo.organization_id, name="Other Sourcing", slug=f"other-sourcing-{uuid.uuid4().hex[:8]}")
        session.add(other)
        _member(session, "staff-sourcing", "staff-sourcing@example.com", demo.venue_id, STAFF)
        _member(session, "auditor-sourcing", "auditor-sourcing@example.com", demo.venue_id, AUDITOR)
        _member(session, "manager-sourcing", "manager-sourcing@example.com", demo.venue_id, MANAGER)
        session.commit()
        other_id = other.id
    finally:
        session.close()
    hidden = build_brief(other_id)

    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "ana")
        assert client.get("/sourcing/briefs").status_code == 403
        client.cookies.set("madira_demo_persona", "owner")
        assert client.get(f"/sourcing/briefs/{hidden['brief']['id']}").status_code == 404

    previous = os.environ.get("MADIRA_AUTH_SECRET")
    os.environ["MADIRA_AUTH_SECRET"] = AUTH_SECRET
    try:
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE, issue_session("auditor-sourcing"))
            assert client.get("/sourcing/briefs").status_code == 200
            assert client.post("/sourcing/briefs").status_code == 403
            client.cookies.set(SESSION_COOKIE, issue_session("manager-sourcing"))
            created = client.post("/sourcing/briefs")
            assert created.status_code == 200, created.text
            assert created.json()["brief"]["items"]
    finally:
        if previous is None:
            os.environ.pop("MADIRA_AUTH_SECRET", None)
        else:
            os.environ["MADIRA_AUTH_SECRET"] = previous


def test_migration_0022_up_and_down(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0022_sourcing.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0021_tasting_sessions"' in source
    assert source.count('_enable_rls("') == 3
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "venue_isolation" in source
    assert "if not _is_postgres():" in source
    db = tmp_path / "sourcing.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "head")
engine = sa.create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0026_usage_metering"
    tables = set(sa.inspect(conn).get_table_names())
    assert "sourcing_briefs" in tables
    assert "want_items" in tables
    assert "rep_followups" in tables
    columns = {col["name"] for col in sa.inspect(conn).get_columns("samples")}
    assert "pass_reason" in columns
    assert "purchase_order_id" in columns
    assert "list_version_id" in columns

command.downgrade(cfg, "0021_tasting_sessions")
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "sourcing_briefs" not in tables
    assert "want_items" not in tables
    assert "rep_followups" not in tables
    columns = {col["name"] for col in sa.inspect(conn).get_columns("samples")}
    assert "pass_reason" not in columns
    assert "tasting_sessions" in tables

command.upgrade(cfg, "head")
with engine.connect() as conn:
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0026_usage_metering"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
