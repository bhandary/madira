"""A rep follow-up is a stored draft. Madira does not send it."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from madira.db import SessionLocal, init_db
from madira.domain.errors import DraftFailed
from madira.domain.sourcing.service import draft_followup, set_thanks_completer
from madira.domain.tastings.service import add_sample, create_session, set_decision
from madira.main import app
from madira.models import POLine, Product, ProductVariant, PurchaseOrder, RepFollowup, Sku, Venue
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant
from sqlalchemy import func, select


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _bottle(session, venue, organization_id, name):
    product = Product(organization_id=organization_id, category="wine", producer="House", name=name)
    session.add(product)
    session.flush()
    variant = ProductVariant(product_id=product.id, vintage="2023", bottle_size="750ml")
    session.add(variant)
    session.flush()
    sku = Sku(venue_id=venue.id, product_variant_id=variant.id, barcode=f"RF-{uuid.uuid4().hex[:8]}")
    session.add(sku)
    session.flush()
    return product, sku


def test_followup_is_a_draft_and_nothing_is_sent(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("the follow-up must not be sent")

    monkeypatch.setattr("madira.domain.procurement.email_adapter.get_po_email_adapter", refuse)
    demo = _demo()
    session = SessionLocal()
    try:
        venue = session.get(Venue, demo.venue_id)
        product, _sku = _bottle(session, venue, demo.organization_id, f"Followup bottle {uuid.uuid4().hex[:6]}")
        session.commit()
        product_id = product.id
    finally:
        session.close()
    created = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title="Follow-up tasting",
        starts_at="2026-12-06T15:00",
    )
    session_id = created["draft"]["id"]
    sample = add_sample(demo.venue_id, session_id, product_id=product_id, quoted_price_cents=1800, currency="USD")["sample"]
    decided = set_decision(demo.venue_id, session_id, uuid.UUID(sample["id"]), "buy")
    number = decided["sample"]["purchase_order_number"]
    assert number

    set_thanks_completer(lambda _prompt: '{"thanks":"Please order 99999 bottles."}')
    try:
        drafted = draft_followup(demo.venue_id, session_id)
    finally:
        set_thanks_completer(None)
    followup = drafted["followup"]
    assert followup["sent"] is False
    assert number in followup["body"]
    assert "99999" not in followup["body"]
    assert "Madira did not send it." in followup["body"]
    assert followup["mailto"].startswith("mailto:")
    assert "subject=" in followup["mailto"]

    session = SessionLocal()
    try:
        order = session.get(PurchaseOrder, uuid.UUID(decided["sample"]["purchase_order_id"]))
        assert order.status == "draft"
        assert order.sent_at is None
        assert order.sent_via is None
        assert session.scalar(select(func.count()).select_from(RepFollowup).where(RepFollowup.session_id == session_id)) == 1
        stored_id = followup["id"]
    finally:
        session.close()

    session = SessionLocal()
    try:
        line_count = session.scalar(select(func.count()).select_from(POLine).where(POLine.po_id == order.id))
    finally:
        session.close()
    second = draft_followup(demo.venue_id, session_id)
    assert second["followup"]["id"] == stored_id
    session = SessionLocal()
    try:
        assert session.scalar(select(func.count()).select_from(RepFollowup).where(RepFollowup.session_id == session_id)) == 1
        assert session.scalar(select(func.count()).select_from(POLine).where(POLine.po_id == order.id)) == line_count
        kept = session.get(PurchaseOrder, order.id)
        assert kept.status == "draft"
        assert kept.sent_at is None
    finally:
        session.close()

    with TestClient(app) as client:
        listed = client.get(f"/tastings/{session_id}/follow-up")
        assert listed.status_code == 200
        assert listed.json()["followup"]["sent"] is False


def test_live_followup_does_not_use_the_demo_sentence(monkeypatch):
    demo = _demo()
    created = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title="Live follow-up",
        starts_at="2026-12-07T15:00",
    )
    session_id = created["draft"]["id"]
    monkeypatch.delenv("MADIRA_DEMO_MODE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-not-a-fixture")
    from madira.llm_runtime import resolve_runtime

    assert resolve_runtime().demo_mode is False

    def explode(_prompt, *, kind):
        raise RuntimeError("connection refused")

    def demo_boom(_prompt):
        raise AssertionError("demo fixtures must not run when the model is live")

    monkeypatch.setattr("madira.domain.sourcing.service.live_complete", explode)
    monkeypatch.setattr("madira.domain.sourcing.service.demo_thanks", demo_boom)
    with pytest.raises(DraftFailed) as caught:
        draft_followup(demo.venue_id, session_id)
    assert "RuntimeError" in caught.value.message
    assert "AssertionError" not in caught.value.message
    session = SessionLocal()
    try:
        assert session.scalar(select(func.count()).select_from(RepFollowup).where(RepFollowup.session_id == session_id)) == 0
    finally:
        session.close()
