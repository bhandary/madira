"""Samples: scores, stored decisions, pricing rules, pairings, and label scans."""

from __future__ import annotations

import base64
import uuid
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from madira.auth import SESSION_COOKIE, issue_session
from madira.db import SessionLocal, init_db
from madira.domain.lists.pricing import economics, load_rules, price_for
from madira.domain.tastings.service import add_sample, create_session, get_session, score_sample, set_decision, set_label_completer
from madira.llm_runtime import resolve_runtime
from madira.main import app
from madira.models import (
    AuditEvent,
    Dish,
    Menu,
    MenuVersion,
    Product,
    ProductVariant,
    PurchaseOrder,
    Sku,
    Supplier,
    SupplierOffer,
)
from madira.seed import seed
from madira.tenancy import DEMO_USER_SUB, ensure_demo_tenant

AUTH_SECRET = "sample-cards-test-secret"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _bottle(session, venue, organization_id, supplier_id, name, *, body="", acidity=""):
    product = Product(
        organization_id=organization_id,
        category="wine",
        producer="House",
        name=name,
        body=body,
        acidity=acidity,
    )
    session.add(product)
    session.flush()
    variant = ProductVariant(product_id=product.id, vintage="2022", bottle_size="750ml")
    session.add(variant)
    session.flush()
    sku = Sku(venue_id=venue.id, product_variant_id=variant.id, barcode=f"S-{uuid.uuid4().hex[:8]}")
    session.add(sku)
    session.flush()
    return product, sku


def test_score_and_decision_are_stored_without_an_order():
    demo = _demo()
    created = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title="Score tasting",
        starts_at="2026-12-08T15:00",
    )
    session_id = created["draft"]["id"]
    sample = add_sample(demo.venue_id, session_id, note="first pour")["sample"]
    scored = score_sample(demo.venue_id, uuid.UUID(sample["id"]), 84, "clean")
    assert scored["sample"]["score"] == 84
    assert scored["sample"]["note"] == "clean"

    session = SessionLocal()
    try:
        before = session.scalar(select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.venue_id == demo.venue_id))
    finally:
        session.close()
    decided = set_decision(demo.venue_id, session_id, uuid.UUID(sample["id"]), "buy")
    assert decided["sample"]["decision"] == "buy"
    session = SessionLocal()
    try:
        after = session.scalar(select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.venue_id == demo.venue_id))
        actions = set(
            session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.venue_id == demo.venue_id,
                    AuditEvent.entity_id == uuid.UUID(sample["id"]),
                )
            )
        )
    finally:
        session.close()
    assert after == before
    assert "sample.scored" in actions
    assert "sample.decision" in actions


def test_list_price_comes_from_the_quote_or_the_current_offer():
    demo = _demo()
    session = SessionLocal()
    try:
        from madira.models import Venue

        venue = session.get(Venue, demo.venue_id)
        supplier = session.scalar(
            select(Supplier).where(Supplier.venue_id == demo.venue_id, Supplier.name == "Kermit Lynch Wine Merchant")
        )
        quoted_product, _sku = _bottle(session, venue, venue.organization_id, supplier.id, f"Quoted {uuid.uuid4().hex[:6]}")
        offer_product, offer_sku = _bottle(session, venue, venue.organization_id, supplier.id, f"Offered {uuid.uuid4().hex[:6]}")
        offer = SupplierOffer(
            venue_id=demo.venue_id,
            supplier_id=supplier.id,
            product_id=offer_product.id,
            sku_id=offer_sku.id,
            price_cents=2200,
            currency="USD",
            valid_from=date(2020, 1, 1),
            source="manual",
            created_at=datetime.now(timezone.utc),
        )
        session.add(offer)
        session.commit()
        quoted_id = quoted_product.id
        offer_product_id = offer_product.id
        supplier_id = supplier.id
        rules = load_rules(session, demo.venue_id)
    finally:
        session.close()

    created = create_session(demo.venue_id, supplier_id=supplier_id, title="Price tasting", starts_at="2026-12-09T15:00")
    session_id = created["draft"]["id"]
    quoted = add_sample(demo.venue_id, session_id, product_id=quoted_id, quoted_price_cents=1800, currency="USD")["sample"]
    expected = price_for(1800, "wine", rules)
    econ = economics(1800, expected["bottle_price"], expected["glass_price"])
    assert quoted["list_price"]["source"] == "quoted"
    assert quoted["list_price"]["cost_cents"] == 1800
    assert quoted["list_price"]["bottle_price"] == expected["bottle_price"]
    assert quoted["list_price"]["glass_price"] == expected["glass_price"]
    assert quoted["list_price"]["margin_pct"] == econ["margin_pct"]
    assert quoted["list_price"]["bottle_label"]
    assert quoted["list_price"]["margin_label"].endswith("%")

    offered = add_sample(demo.venue_id, session_id, product_id=offer_product_id)["sample"]
    offer_price = price_for(2200, "wine", rules)
    assert offered["list_price"]["source"] == "offer"
    assert offered["list_price"]["cost_cents"] == 2200
    assert offered["list_price"]["bottle_price"] == offer_price["bottle_price"]

    bare = add_sample(demo.venue_id, session_id)["sample"]
    assert bare["list_price"]["note"] == "No quoted price or current offer."
    assert bare["list_price"]["bottle_price"] is None


def test_pairs_with_uses_the_pairing_service_and_says_when_there_is_no_profile():
    demo = _demo()
    session = SessionLocal()
    version_id = None
    try:
        from madira.models import Venue

        venue = session.get(Venue, demo.venue_id)
        supplier = session.scalar(select(Supplier).where(Supplier.venue_id == demo.venue_id).limit(1))
        profiled, _sku = _bottle(
            session,
            venue,
            venue.organization_id,
            supplier.id,
            f"Crab wine {uuid.uuid4().hex[:6]}",
            body="light",
            acidity="high",
        )
        blank, _blank_sku = _bottle(session, venue, venue.organization_id, supplier.id, f"Blank wine {uuid.uuid4().hex[:6]}")
        menu = Menu(venue_id=demo.venue_id, name="Sample pairing menu", source_type="text", raw_text="crab")
        session.add(menu)
        session.flush()
        version = MenuVersion(
            venue_id=demo.venue_id,
            menu_id=menu.id,
            number=1,
            source_type="text",
            status="confirmed",
            confirmed_by=demo.user_id,
            confirmed_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            raw_text="crab",
        )
        session.add(version)
        session.flush()
        version_id = version.id
        session.add(
            Dish(
                venue_id=demo.venue_id,
                menu_id=menu.id,
                menu_version_id=version.id,
                name="Dungeness crab, yuzu",
                course="first",
                richness=1,
                acidity=5,
                sweetness=0,
                spice=0,
                umami=2,
            )
        )
        session.commit()
        profiled_id = profiled.id
        blank_id = blank.id
        supplier_id = supplier.id
    finally:
        session.close()

    try:
        created = create_session(demo.venue_id, supplier_id=supplier_id, title="Pairing tasting", starts_at="2026-12-10T15:00")
        session_id = created["draft"]["id"]
        matched = add_sample(demo.venue_id, session_id, product_id=profiled_id)["sample"]
        names = [dish["name"] for dish in matched["pairs_with"]["dishes"]]
        assert "Dungeness crab, yuzu" in names
        assert matched["pairs_with"]["dishes"][0]["confidence"] in {"medium", "high"}
        assert matched["pairs_with"]["profile"]
        empty = add_sample(demo.venue_id, session_id, product_id=blank_id)["sample"]
        assert empty["pairs_with"]["dishes"] == []
        assert empty["pairs_with"]["note"] == "This product has no structured flavor profile."
    finally:
        session = SessionLocal()
        try:
            version = session.get(MenuVersion, version_id) if version_id else None
            if version is not None:
                version.status = "draft"
                version.confirmed_by = None
                version.confirmed_at = None
                session.commit()
        finally:
            session.close()


def test_unmatched_label_stays_unmatched_and_live_mode_does_not_use_fixtures(monkeypatch):
    demo = _demo()
    created = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title="Label tasting",
        starts_at="2026-12-11T15:00",
    )
    session_id = created["draft"]["id"]
    with TestClient(app) as client:
        mystery = client.post(
            f"/tastings/{session_id}/samples/label",
            files={"file": ("mystery-label.png", PNG, "image/png")},
        )
        assert mystery.status_code == 200, mystery.text
        assert mystery.json()["sample"]["matched"] is False
        assert mystery.json()["sample"]["product_id"] is None

        known = client.post(
            f"/tastings/{session_id}/samples/label",
            files={"file": ("Muscadet Domaine de l'Ecu.png", PNG, "image/png")},
        )
        assert known.status_code == 200, known.text
        assert known.json()["sample"]["matched"] is True
        assert known.json()["sample"]["product_name"] == "Muscadet Domaine de l'Ecu"

    before = len(get_session(demo.venue_id, session_id)["samples"])
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-not-a-fixture")
    assert resolve_runtime().demo_mode is False

    def explode(_prompt, _image=None):
        raise RuntimeError("connection refused")

    def demo_boom(_prompt, _image=None):
        raise AssertionError("demo fixtures must not run when the model is live")

    monkeypatch.setattr("madira.domain.tastings.service.live_complete", explode)
    monkeypatch.setattr("madira.domain.tastings.service.demo_complete", demo_boom)
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, issue_session(DEMO_USER_SUB))
        failed = client.post(
            f"/tastings/{session_id}/samples/label",
            files={"file": ("mystery-label.png", PNG, "image/png")},
        )
        assert failed.status_code == 502
        assert "AssertionError" not in failed.text
        assert "Muscadet" not in failed.text
    assert len(get_session(demo.venue_id, session_id)["samples"]) == before

    def invented(_prompt, _image=None):
        return '{"name":"Chateau Nowhere","producer":"","barcode":""}'

    set_label_completer(invented)
    try:
        from madira.domain.tastings.service import scan_label

        scanned = scan_label(
            demo.venue_id,
            session_id,
            filename="mystery-label.png",
            content_type="image/png",
            body=PNG,
        )
    finally:
        set_label_completer(None)
    assert scanned["sample"]["matched"] is False
    assert scanned["sample"]["product_id"] is None
