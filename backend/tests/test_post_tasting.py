"""Post-tasting decisions open a draft order or a draft list, and a pass stores a reason."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.procurement.orders import create_purchase_order
from madira.domain.sourcing.service import tasting_history
from madira.domain.tastings.service import TastingError, add_sample, create_session, set_decision
from madira.main import app
from madira.models import (
    Approval,
    AuditEvent,
    BeverageList,
    Document,
    Invoice,
    ListEntry,
    ListVersion,
    Membership,
    POLine,
    Product,
    ProductVariant,
    PurchaseOrder,
    Sku,
    Supplier,
    SupplierOffer,
    User,
    Venue,
)
from madira.seed import seed
from madira.tenancy import AUDITOR, MANAGER, STAFF, ensure_demo_tenant

AUTH_SECRET = "post-tasting-test-secret"


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _bottle(session, venue, organization_id, name):
    product = Product(organization_id=organization_id, category="wine", producer="House", name=name)
    session.add(product)
    session.flush()
    variant = ProductVariant(product_id=product.id, vintage="2022", bottle_size="750ml")
    session.add(variant)
    session.flush()
    sku = Sku(venue_id=venue.id, product_variant_id=variant.id, barcode=f"PT-{uuid.uuid4().hex[:8]}")
    session.add(sku)
    session.flush()
    return product, sku


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


def _pour(demo, title, product_id, quoted=1800):
    created = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title=title,
        starts_at="2026-12-01T15:00",
    )
    session_id = created["draft"]["id"]
    sample = add_sample(
        demo.venue_id,
        session_id,
        product_id=product_id,
        quoted_price_cents=quoted,
        currency="USD",
    )["sample"]
    return session_id, sample


def test_buy_creates_a_draft_and_a_second_decision_does_not_add_a_line():
    demo = _demo()
    session = SessionLocal()
    try:
        venue = session.get(Venue, demo.venue_id)
        product, sku = _bottle(session, venue, demo.organization_id, f"Decision Muscadet {uuid.uuid4().hex[:6]}")
        session.commit()
        product_id = product.id
        sku_id = sku.id
    finally:
        session.close()

    session_id, sample = _pour(demo, "Buy tasting", product_id)
    decided = set_decision(demo.venue_id, session_id, uuid.UUID(sample["id"]), "buy")
    assert decided["sample"]["decision"] == "buy"
    assert decided["sample"]["purchase_order_status"] == "draft"
    po_id = uuid.UUID(decided["sample"]["purchase_order_id"])

    session = SessionLocal()
    try:
        order = session.get(PurchaseOrder, po_id)
        assert order.status == "draft"
        assert order.sent_at is None
        lines = session.scalars(select(POLine).where(POLine.po_id == order.id, POLine.sku_id == sku_id)).all()
        assert len(lines) == 1
        assert int(lines[0].unit_cost_cents) == 1800
        approval = session.scalar(select(Approval).where(Approval.entity_id == order.id))
        assert approval.decision == "pending"
        actions = set(session.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == uuid.UUID(sample["id"]))).all())
    finally:
        session.close()
    assert "sample.bought" in actions

    again = set_decision(demo.venue_id, session_id, uuid.UUID(sample["id"]), "buy")
    assert again["sample"]["purchase_order_id"] == str(po_id)
    session = SessionLocal()
    try:
        assert session.scalar(select(func.count()).select_from(POLine).where(POLine.po_id == po_id, POLine.sku_id == sku_id)) == 1
    finally:
        session.close()

    other_session, second = _pour(demo, "Buy tasting again", product_id, quoted=1900)
    repeated = set_decision(demo.venue_id, other_session, uuid.UUID(second["id"]), "buy")
    assert repeated["sample"]["purchase_order_id"] == str(po_id)
    session = SessionLocal()
    try:
        assert session.scalar(select(func.count()).select_from(POLine).where(POLine.po_id == po_id, POLine.sku_id == sku_id)) == 1
    finally:
        session.close()


def test_buy_appends_to_an_open_draft_and_uses_the_current_offer():
    demo = _demo()
    session = SessionLocal()
    try:
        venue = session.get(Venue, demo.venue_id)
        held, held_sku = _bottle(session, venue, demo.organization_id, f"Held bottle {uuid.uuid4().hex[:6]}")
        offered, offered_sku = _bottle(session, venue, demo.organization_id, f"Offered bottle {uuid.uuid4().hex[:6]}")
        supplier = session.scalar(select(Supplier).where(Supplier.venue_id == venue.id, Supplier.name == "Kermit Lynch Wine Merchant"))
        session.add(
            SupplierOffer(
                venue_id=venue.id,
                supplier_id=supplier.id,
                product_id=offered.id,
                sku_id=offered_sku.id,
                price_cents=2200,
                currency="USD",
                valid_from=date(2026, 1, 1),
                source="manual",
            )
        )
        session.commit()
        supplier_id = supplier.id
        held_barcode = held_sku.barcode
        held_sku_id = held_sku.id
        offered_id = offered.id
    finally:
        session.close()

    opened = create_purchase_order(
        demo.venue_id,
        supplier_id,
        [{"sku": held_barcode, "sku_id": str(held_sku_id), "cases_ordered": 1, "unit_cost_cents": 1000}],
        None,
        "Open draft",
    )
    created = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title="Offer tasting",
        starts_at="2026-12-02T15:00",
    )
    sample = add_sample(demo.venue_id, created["draft"]["id"], product_id=offered_id)["sample"]
    assert sample["quoted_price_cents"] is None
    decided = set_decision(demo.venue_id, created["draft"]["id"], uuid.UUID(sample["id"]), "buy")
    assert decided["sample"]["purchase_order_id"] == str(opened["id"])
    po_id = uuid.UUID(opened["id"])
    session = SessionLocal()
    try:
        lines = session.scalars(select(POLine).where(POLine.po_id == po_id)).all()
        assert len(lines) == 2
        offered_line = next(line for line in lines if int(line.unit_cost_cents) == 2200)
        assert offered_line.sku_id is not None
        order = session.get(PurchaseOrder, po_id)
        assert order.status == "draft"
    finally:
        session.close()


def test_list_creates_a_draft_version_and_pass_stores_a_reason():
    demo = _demo()
    session = SessionLocal()
    try:
        venue = session.get(Venue, demo.venue_id)
        product, sku = _bottle(session, venue, demo.organization_id, f"List bottle {uuid.uuid4().hex[:6]}")
        beverage = BeverageList(venue_id=venue.id, name=f"Tasting picks {uuid.uuid4().hex[:6]}", budget=0, currency="USD", target_margin=3.0)
        session.add(beverage)
        session.commit()
        product_id = product.id
        sku_id = sku.id
        list_id = beverage.id
    finally:
        session.close()

    session_id, sample = _pour(demo, "List tasting", product_id, quoted=1600)
    with pytest.raises(TastingError, match="reason"):
        set_decision(demo.venue_id, session_id, uuid.UUID(sample["id"]), "pass", "")
    listed = set_decision(demo.venue_id, session_id, uuid.UUID(sample["id"]), "list")
    assert listed["sample"]["decision"] == "list"
    version_id = uuid.UUID(listed["sample"]["list_version_id"])
    session = SessionLocal()
    try:
        version = session.get(ListVersion, version_id)
        assert version.status == "draft"
        assert version.list_id == list_id
        assert version.public_token is None
        assert session.scalar(select(ListEntry.id).where(ListEntry.version_id == version.id, ListEntry.sku_id == sku_id)) is not None
        actions = set(session.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == uuid.UUID(sample["id"]))).all())
    finally:
        session.close()
    assert "sample.listed" in actions
    again = set_decision(demo.venue_id, session_id, uuid.UUID(sample["id"]), "list")
    assert again["sample"]["list_version_id"] == str(version_id)

    passed = set_decision(demo.venue_id, session_id, uuid.UUID(sample["id"]), "pass", "Too ripe for the crab.")
    assert passed["sample"]["decision"] == "pass"
    assert passed["sample"]["pass_reason"] == "Too ripe for the crab."
    session = SessionLocal()
    try:
        assert session.scalar(select(func.count()).select_from(ListVersion).where(ListVersion.id == version_id)) == 1
        assert "sample.passed" in set(
            session.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == uuid.UUID(sample["id"]))).all()
        )
    finally:
        session.close()


def test_unmatched_buy_is_blocked_and_history_counts_the_order_and_invoice():
    demo = _demo()
    created = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title="Unmatched tasting",
        starts_at="2026-12-03T15:00",
    )
    bare = add_sample(demo.venue_id, created["draft"]["id"])["sample"]
    with pytest.raises(TastingError, match="catalog product"):
        set_decision(demo.venue_id, created["draft"]["id"], uuid.UUID(bare["id"]), "buy")
    with pytest.raises(TastingError, match="catalog product"):
        set_decision(demo.venue_id, created["draft"]["id"], uuid.UUID(bare["id"]), "list")

    session = SessionLocal()
    try:
        venue = session.get(Venue, demo.venue_id)
        product, sku = _bottle(session, venue, demo.organization_id, f"History bottle {uuid.uuid4().hex[:6]}")
        supplier = session.scalar(select(Supplier).where(Supplier.venue_id == venue.id, Supplier.name == "Kermit Lynch Wine Merchant"))
        document = Document(
            org_id=venue.organization_id,
            venue_id=venue.id,
            doc_type="invoice",
            filename="history.txt",
            content_type="text/plain",
            size_bytes=4,
            storage_key=f"history/{uuid.uuid4().hex}",
            sha256="ab" * 32,
        )
        session.add(document)
        session.flush()
        session.commit()
        product_id = product.id
        barcode = sku.barcode
        supplier_id = supplier.id
        document_id = document.id
    finally:
        session.close()

    session_id, sample = _pour(demo, "History tasting", product_id)
    decided = set_decision(demo.venue_id, session_id, uuid.UUID(sample["id"]), "buy")
    session = SessionLocal()
    try:
        session.add(
            Invoice(
                venue_id=demo.venue_id,
                supplier_id=supplier_id,
                invoice_number=f"H-{uuid.uuid4().hex[:6]}",
                invoice_date="2026-12-04",
                document_id=document_id,
                extraction_mode="manual",
                extracted_lines=[{"sku": barcode, "product_name": "History bottle", "quantity": 3, "unit_cost_cents": 1800}],
            )
        )
        session.commit()
    finally:
        session.close()
    history = tasting_history(demo.venue_id, product_id=product_id)
    assert len(history["rows"]) == 1
    row = history["rows"][0]
    assert row["tasted"] == 1
    assert row["buy"] == 1
    assert row["bought_bottles"] == 12
    assert row["invoiced_bottles"] == 3
    assert row["last_cost_label"]
    assert decided["sample"]["purchase_order_status"] == "draft"


def test_decision_roles_and_venue_isolation():
    demo = _demo()
    session = SessionLocal()
    try:
        venue = session.get(Venue, demo.venue_id)
        product, _sku = _bottle(session, venue, demo.organization_id, f"Role bottle {uuid.uuid4().hex[:6]}")
        other = Venue(organization_id=demo.organization_id, name="Other Decisions", slug=f"other-decisions-{uuid.uuid4().hex[:8]}")
        session.add(other)
        session.flush()
        session.add(Supplier(venue_id=other.id, name="Other House", kind="distributor"))
        _member(session, "staff-decisions", "staff-decisions@example.com", demo.venue_id, STAFF)
        _member(session, "auditor-decisions", "auditor-decisions@example.com", demo.venue_id, AUDITOR)
        _member(session, "manager-decisions", "manager-decisions@example.com", demo.venue_id, MANAGER)
        session.commit()
        product_id = product.id
        other_id = other.id
    finally:
        session.close()

    hidden = create_session(other_id, supplier_name="Other House", title="Hidden decision tasting", starts_at="2026-12-04T15:00")
    session_id, sample = _pour(demo, "Role tasting", product_id)

    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "ana")
        denied = client.post(
            f"/tastings/{session_id}/samples/{sample['id']}/decision",
            json={"decision": "buy"},
        )
        assert denied.status_code == 403
        client.cookies.set("madira_demo_persona", "owner")
        foreign = client.post(
            f"/tastings/{hidden['draft']['id']}/samples/{uuid.uuid4()}/decision",
            json={"decision": "pass", "reason": "no"},
        )
        assert foreign.status_code == 404

    monkeypatch_secret = __import__("os").environ.get("MADIRA_AUTH_SECRET")
    __import__("os").environ["MADIRA_AUTH_SECRET"] = AUTH_SECRET
    try:
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE, issue_session("auditor-decisions"))
            blocked = client.post(
                f"/tastings/{session_id}/samples/{sample['id']}/decision",
                json={"decision": "buy"},
            )
            assert blocked.status_code == 403
            client.cookies.set(SESSION_COOKIE, issue_session("manager-decisions"))
            allowed = client.post(
                f"/tastings/{session_id}/samples/{sample['id']}/decision",
                json={"decision": "pass", "reason": "Not for this menu."},
            )
            assert allowed.status_code == 200, allowed.text
            assert allowed.json()["sample"]["decision"] == "pass"
    finally:
        if monkeypatch_secret is None:
            __import__("os").environ.pop("MADIRA_AUTH_SECRET", None)
        else:
            __import__("os").environ["MADIRA_AUTH_SECRET"] = monkeypatch_secret
