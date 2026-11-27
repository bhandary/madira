"""Supplier profiles, allocations, offers, current-offer windows, curator costs, RBAC, and tenancy."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import select

from madira.agents.demo.model import DemoChatModel, classify_intent
from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.lists.pricing import ensure_default_rules, load_rules
from madira.domain.lists.service import _candidates
from madira.domain.procurement import offers
from madira.domain.procurement.offers import OfferError
from madira.main import app
from madira.models import AuditEvent, Membership, PriceSheet, Sku, Supplier, SupplierOffer, User, Venue
from madira.seed import seed
from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "supplier-offers-test-secret"
TODAY = date(2026, 6, 15)


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _pair(session, venue_id):
    sku = session.scalar(select(Sku).where(Sku.venue_id == venue_id, Sku.barcode == "W-MUS-01"))
    assert sku is not None and sku.variant is not None
    supplier = session.scalar(
        select(Supplier).where(Supplier.venue_id == venue_id, Supplier.name == "Kermit Lynch Wine Merchant")
    )
    assert supplier is not None
    return sku, sku.variant.product, supplier


def _other_supplier(session, venue_id):
    row = session.scalar(select(Supplier).where(Supplier.venue_id == venue_id, Supplier.name == "Skurnik Wines"))
    assert row is not None
    return row


def _member(session, google_sub: str, email: str, venue_id, role: str) -> None:
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


def _offer_row(venue_id, supplier_id, product_id, sku_id, *, price, start, end, created) -> SupplierOffer:
    return SupplierOffer(
        venue_id=venue_id,
        supplier_id=supplier_id,
        product_id=product_id,
        sku_id=sku_id,
        unit_description="750ml bottle",
        case_size=12,
        price_cents=price,
        currency="USD",
        valid_from=start,
        valid_to=end,
        source="manual",
        created_at=created,
    )


def _delete_offers(ids: list[uuid.UUID]) -> None:
    session = SessionLocal()
    try:
        for offer_id in ids:
            row = session.get(SupplierOffer, offer_id)
            if row is not None:
                session.delete(row)
        session.commit()
    finally:
        session.close()


def test_profile_allocation_and_offer_crud_write_audit_events():
    demo = _demo()
    session = SessionLocal()
    try:
        _sku, product, supplier = _pair(session, demo.venue_id)
        before = {
            "rep_name": supplier.rep_name,
            "rep_email": supplier.rep_email,
            "rep_phone": supplier.rep_phone or "",
            "delivery_days": list(supplier.delivery_days or []),
            "order_minimum_cents": int(supplier.order_minimum_cents or 0),
            "order_minimum_currency": supplier.order_minimum_currency,
            "payment_terms": supplier.payment_terms or "",
            "notes": supplier.notes or "",
        }
        supplier_id = supplier.id
        product_id = product.id
    finally:
        session.close()

    allocation_id = None
    offer_id = None
    try:
        saved = offers.update_profile(
            demo.venue_id,
            supplier_id,
            {
                "rep_name": "Claire Vasseur",
                "rep_email": "claire@kermit.example",
                "rep_phone": "510-555-0148",
                "delivery_days": ["tuesday", "Fri"],
                "order_minimum_cents": 25000,
                "order_minimum_currency": "USD",
                "payment_terms": "Net 15",
                "notes": "Call before Thursday.",
            },
        )
        assert saved["supplier"]["delivery_days"] == ["Tue", "Fri"]
        assert saved["supplier"]["order_minimum_label"] == "USD 250.00"
        desk = offers.supplier_desk(demo.venue_id, supplier_id)
        assert desk["supplier"]["rep_name"] == "Claire Vasseur"

        created = offers.create_allocation(
            demo.venue_id,
            supplier_id,
            {
                "product_id": str(product_id),
                "quantity": 6,
                "period_label": "Spring 2026",
                "period_start": "2026-03-01",
                "period_end": "2026-05-31",
            },
        )
        allocation_id = uuid.UUID(created["allocation"]["id"])
        updated = offers.update_allocation(demo.venue_id, allocation_id, {"quantity": 8})
        assert updated["allocation"]["quantity"] == 8

        offered = offers.create_offer(
            demo.venue_id,
            {
                "supplier_id": str(supplier_id),
                "product_id": str(product_id),
                "unit": "750ml bottle",
                "case_size": 12,
                "price_cents": 1950,
                "currency": "USD",
                "valid_from": "2026-06-01",
            },
        )
        offer_id = uuid.UUID(offered["offer"]["id"])
        assert offered["offer"]["price_label"] == "USD 19.50"
        changed = offers.update_offer(demo.venue_id, offer_id, {"price_cents": 2000})
        assert changed["offer"]["price_cents"] == 2000
        listed = offers.list_offers(demo.venue_id, product_id=product_id, supplier_id=supplier_id)
        assert any(row["id"] == str(offer_id) for row in listed["offers"])

        session = SessionLocal()
        try:
            actions = set(
                session.scalars(
                    select(AuditEvent.action).where(
                        AuditEvent.venue_id == demo.venue_id,
                        AuditEvent.entity_id.in_([supplier_id, allocation_id, offer_id]),
                    )
                ).all()
            )
        finally:
            session.close()
        assert "supplier.profile_updated" in actions
        assert "supplier_allocation.created" in actions
        assert "supplier_allocation.updated" in actions
        assert "supplier_offer.created" in actions
        assert "supplier_offer.updated" in actions
    finally:
        if offer_id is not None:
            offers.delete_offer(demo.venue_id, offer_id)
        if allocation_id is not None:
            offers.delete_allocation(demo.venue_id, allocation_id)
        offers.update_profile(demo.venue_id, supplier_id, before)
        session = SessionLocal()
        try:
            deleted = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.venue_id == demo.venue_id,
                    AuditEvent.entity_id == offer_id,
                    AuditEvent.action == "supplier_offer.deleted",
                )
            ) if offer_id is not None else None
        finally:
            session.close()
        assert offer_id is None or deleted is not None


def test_current_offer_is_the_latest_valid_window_per_supplier():
    demo = _demo()
    session = SessionLocal()
    ids: list[uuid.UUID] = []
    try:
        sku, product, kermit = _pair(session, demo.venue_id)
        skurnik = _other_supplier(session, demo.venue_id)
        sake = session.scalar(
            select(Supplier).where(Supplier.venue_id == demo.venue_id, Supplier.name == "World Sake Imports")
        )
        assert sake is not None
        rows = [
            _offer_row(
                demo.venue_id, kermit.id, product.id, sku.id,
                price=1000, start=date(2026, 1, 1), end=None, created=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            _offer_row(
                demo.venue_id, kermit.id, product.id, sku.id,
                price=3000, start=date(2026, 6, 1), end=date(2026, 6, 15), created=datetime(2026, 6, 2, tzinfo=timezone.utc),
            ),
            _offer_row(
                demo.venue_id, kermit.id, product.id, sku.id,
                price=2500, start=date(2026, 6, 1), end=date(2026, 6, 15), created=datetime(2026, 6, 3, tzinfo=timezone.utc),
            ),
            _offer_row(
                demo.venue_id, kermit.id, product.id, sku.id,
                price=4000, start=date(2026, 6, 10), end=None, created=datetime(2026, 6, 11, tzinfo=timezone.utc),
            ),
            _offer_row(
                demo.venue_id, kermit.id, product.id, sku.id,
                price=999, start=date(2026, 6, 16), end=None, created=datetime(2026, 6, 1, tzinfo=timezone.utc),
            ),
            _offer_row(
                demo.venue_id, kermit.id, product.id, sku.id,
                price=500, start=date(2026, 5, 1), end=date(2026, 6, 14), created=datetime(2026, 5, 2, tzinfo=timezone.utc),
            ),
            _offer_row(
                demo.venue_id, skurnik.id, product.id, sku.id,
                price=2200, start=date(2026, 3, 1), end=None, created=datetime(2026, 3, 2, tzinfo=timezone.utc),
            ),
            _offer_row(
                demo.venue_id, sake.id, product.id, sku.id,
                price=777, start=date(2026, 6, 1), end=date(2026, 6, 15), created=datetime(2026, 6, 1, tzinfo=timezone.utc),
            ),
        ]
        session.add_all(rows)
        session.commit()
        ids = [row.id for row in rows]
        product_id = product.id
        kermit_id = kermit.id
        skurnik_id = skurnik.id
        sake_id = sake.id
    finally:
        session.close()

    try:
        current = offers.list_current_offers(demo.venue_id, product_id=product_id, today=TODAY)
        by_supplier = {row["supplier_id"]: row for row in current["offers"] if row["id"] in {str(item) for item in ids}}
        assert set(by_supplier) == {str(kermit_id), str(skurnik_id), str(sake_id)}
        assert by_supplier[str(kermit_id)]["price_cents"] == 4000
        assert by_supplier[str(skurnik_id)]["price_cents"] == 2200
        assert by_supplier[str(sake_id)]["price_cents"] == 777
        earlier = offers.list_current_offers(demo.venue_id, product_id=product_id, supplier_id=kermit_id, today=date(2026, 6, 5))
        assert earlier["offers"][0]["price_cents"] == 2500
        after = offers.list_current_offers(demo.venue_id, product_id=product_id, supplier_id=sake_id, today=date(2026, 6, 16))
        assert after["offers"] == []
    finally:
        _delete_offers(ids)


def test_offers_replace_cellar_cost_for_the_curator_and_absence_leaves_it_alone():
    demo = _demo()
    session = SessionLocal()
    offer_id = None
    previous_cost = None
    sku_id = None
    try:
        sku, product, supplier = _pair(session, demo.venue_id)
        sku_id = sku.id
        previous_cost = int(sku.cost or 0)
        ensure_default_rules(session, demo.venue_id)
        session.commit()
        rules = load_rules(session, demo.venue_id)
        before = {pick.sku_id: pick.cost for pick in _candidates(session, demo.venue_id, rules)}
        assert sku_id in before
        assert before[sku_id] == previous_cost
        product_id = product.id
        supplier_id = supplier.id
    finally:
        session.close()

    try:
        created = offers.create_offer(
            demo.venue_id,
            {
                "supplier_id": str(supplier_id),
                "product_id": str(product_id),
                "sku_id": str(sku_id),
                "price_cents": 100,
                "valid_from": "2020-01-01",
            },
        )
        offer_id = uuid.UUID(created["offer"]["id"])
        session = SessionLocal()
        try:
            rules = load_rules(session, demo.venue_id)
            with_offer = {pick.sku_id: pick.cost for pick in _candidates(session, demo.venue_id, rules)}
            assert with_offer[sku_id] == 100
            for other_id, cost in before.items():
                if other_id != sku_id:
                    assert with_offer[other_id] == cost
            sku = session.get(Sku, sku_id)
            sku.cost = 0
            session.commit()
            rules = load_rules(session, demo.venue_id)
            zeroed = {pick.sku_id: pick.cost for pick in _candidates(session, demo.venue_id, rules)}
            assert zeroed[sku_id] == 100
        finally:
            session.close()
        offers.delete_offer(demo.venue_id, offer_id)
        offer_id = None
        session = SessionLocal()
        try:
            sku = session.get(Sku, sku_id)
            sku.cost = 0
            session.commit()
            rules = load_rules(session, demo.venue_id)
            excluded = {pick.sku_id: pick.cost for pick in _candidates(session, demo.venue_id, rules)}
            assert sku_id not in excluded
            sku.cost = previous_cost
            session.commit()
            restored = {pick.sku_id: pick.cost for pick in _candidates(session, demo.venue_id, rules)}
        finally:
            session.close()
        assert restored == before
    finally:
        if offer_id is not None:
            offers.delete_offer(demo.venue_id, offer_id)
        if sku_id is not None and previous_cost is not None:
            session = SessionLocal()
            try:
                sku = session.get(Sku, sku_id)
                if sku is not None:
                    sku.cost = previous_cost
                session.commit()
            finally:
                session.close()


def test_routes_follow_role_and_venue(monkeypatch):
    demo = _demo()
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    session = SessionLocal()
    try:
        _sku, product, supplier = _pair(session, demo.venue_id)
        other = Venue(
            organization_id=demo.organization_id,
            name="Other Offers",
            slug=f"other-offers-{uuid.uuid4().hex[:8]}",
        )
        session.add(other)
        session.flush()
        _member(session, "staff-offers", "staff-offers@example.com", demo.venue_id, STAFF)
        _member(session, "auditor-offers", "auditor-offers@example.com", demo.venue_id, AUDITOR)
        _member(session, "manager-offers", "manager-offers@example.com", demo.venue_id, MANAGER)
        _member(session, "sommelier-offers", "sommelier-offers@example.com", demo.venue_id, SOMMELIER)
        _member(session, "owner-other-offers", "owner-other-offers@example.com", other.id, OWNER)
        session.commit()
        supplier_id = supplier.id
        product_id = product.id
        other_id = other.id
        original = {
            "rep_name": supplier.rep_name or "",
            "rep_email": supplier.rep_email or "",
            "rep_phone": supplier.rep_phone or "",
            "delivery_days": list(supplier.delivery_days or []),
            "order_minimum_cents": int(supplier.order_minimum_cents or 0),
            "order_minimum_currency": supplier.order_minimum_currency or "USD",
            "payment_terms": supplier.payment_terms or "",
            "notes": supplier.notes or "",
        }
    finally:
        session.close()

    sheet_id = None
    offer_id = None
    allocation_id = None
    try:
        sheet = offers.ingest_price_sheet(
            demo.venue_id,
            supplier_id,
            filename="role.csv",
            body=b"name,sku,price\nChateau Nowhere 2015,,12.00\n",
            content_type="text/csv",
        )
        sheet_id = uuid.UUID(sheet["price_sheet"]["id"])
        created = offers.create_offer(
            demo.venue_id,
            {
                "supplier_id": str(supplier_id),
                "product_id": str(product_id),
                "price_cents": 1800,
                "valid_from": "2020-01-01",
            },
        )
        offer_id = uuid.UUID(created["offer"]["id"])
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE, issue_session("staff-offers"))
            denied = client.get(f"/procurement/suppliers/{supplier_id}/desk")
            assert denied.status_code == 403

            client.cookies.set(SESSION_COOKIE, issue_session("auditor-offers"))
            readable = client.get(f"/procurement/suppliers/{supplier_id}/desk")
            assert readable.status_code == 200
            history = client.get(f"/procurement/products/{product_id}/price-history")
            assert history.status_code == 200
            blocked = client.post(f"/procurement/price-sheets/{sheet_id}/apply")
            assert blocked.status_code == 403

            client.cookies.set(SESSION_COOKIE, issue_session("manager-offers"))
            patched = client.patch(
                f"/procurement/suppliers/{supplier_id}/profile",
                json={"notes": "Manager note"},
            )
            assert patched.status_code == 200, patched.text

            client.cookies.set(SESSION_COOKIE, issue_session("sommelier-offers"))
            allocated = client.post(
                f"/procurement/suppliers/{supplier_id}/allocations",
                json={"product_id": str(product_id), "quantity": 2, "period_label": "Fall"},
            )
            assert allocated.status_code == 200, allocated.text
            allocation_id = uuid.UUID(allocated.json()["allocation"]["id"])

            client.cookies.set(SESSION_COOKIE, issue_session("owner-other-offers"))
            missing = client.get(f"/procurement/suppliers/{supplier_id}/desk")
            assert missing.status_code == 404
            foreign = offers.list_current_offers(other_id, today=TODAY)
            assert all(row["id"] != str(offer_id) for row in foreign["offers"])
    finally:
        if allocation_id is not None:
            offers.delete_allocation(demo.venue_id, allocation_id)
        if offer_id is not None:
            offers.delete_offer(demo.venue_id, offer_id)
        offers.update_profile(demo.venue_id, supplier_id, original)
        if sheet_id is not None:
            session = SessionLocal()
            try:
                sheet_row = session.get(PriceSheet, sheet_id)
                if sheet_row is not None:
                    session.delete(sheet_row)
                session.commit()
            finally:
                session.close()


def test_demo_model_routes_offers_and_history_without_dropping_tastings():
    assert classify_intent("What is the price history for Muscadet?") == "supplier"
    assert classify_intent("Show the current offer from Kermit Lynch") == "supplier"
    model = DemoChatModel(role="supplier-scheduler")
    history = model.invoke([HumanMessage(content="PRICE_HISTORY product=Muscadet Domaine de l'Ecu")])
    assert history.tool_calls[0]["name"] == "get_price_history"
    assert history.tool_calls[0]["args"]["product"] == "Muscadet Domaine de l'Ecu"
    offers_call = model.invoke(
        [HumanMessage(content="SUPPLIER_OFFERS product=Muscadet Domaine de l'Ecu supplier=Kermit Lynch Wine Merchant")]
    )
    assert offers_call.tool_calls[0]["name"] == "get_supplier_offers"
    finished = model.invoke(
        [
            HumanMessage(content="SUPPLIER_OFFERS product=Muscadet Domaine de l'Ecu supplier="),
            AIMessage(
                content="",
                tool_calls=[{"name": "get_supplier_offers", "args": {"product": "Muscadet"}, "id": "call-1", "type": "tool_call"}],
            ),
            ToolMessage(content='{"offers":[]}', name="get_supplier_offers", tool_call_id="call-1"),
        ]
    )
    assert not finished.tool_calls
    assert "Current offers" in str(finished.content)
    tasting = model.invoke([HumanMessage(content="Schedule a tasting with Kermit Lynch Wine Merchant")])
    assert tasting.tool_calls[0]["name"] == "plan_tasting"
    head = DemoChatModel()
    wrapped = head._task_description("supplier-scheduler", "Show the price history for Muscadet Domaine de l'Ecu")
    assert wrapped.startswith("PRICE_HISTORY product=")


def test_migration_0020_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0020_supplier_offers.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0019_list_versions"' in source
    assert source.count('_enable_rls("') == 3
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "if not _is_postgres():" in source
    db = tmp_path / "supplier-offers.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "0019_list_versions")
engine = sa.create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "supplier_offers" not in tables
    assert "price_sheets" not in tables
    assert "supplier_allocations" not in tables
    columns = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(suppliers)"))}
    assert "rep_name" not in columns

command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0027_pairing_cache"
    tables = set(sa.inspect(conn).get_table_names())
    assert {"supplier_offers", "price_sheets", "supplier_allocations"} <= tables
    columns = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(suppliers)"))}
    assert {"rep_name", "rep_email", "rep_phone", "order_minimum_currency"} <= columns
    offers = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(supplier_offers)"))}
    assert {"venue_id", "supplier_id", "product_id", "sku_id", "price_cents", "currency", "valid_from", "valid_to", "source", "price_sheet_id"} <= offers

command.downgrade(cfg, "0019_list_versions")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0019_list_versions"
    tables = set(sa.inspect(conn).get_table_names())
    assert "supplier_offers" not in tables
    assert "price_sheets" not in tables
    assert "supplier_allocations" not in tables
    columns = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(suppliers)"))}
    assert "rep_name" not in columns
    assert "order_minimum_currency" not in columns

command.upgrade(cfg, "head")
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
