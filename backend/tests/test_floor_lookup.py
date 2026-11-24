"""Floor lookup parses a guest preference and answers from approved floor data."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.domain.catalog.service import ensure_sku
from madira.domain.errors import DraftFailed
from madira.domain.training.lookup import lookup, parse_query, set_lookup_completer
from madira.models import BeverageList, ListItem, ServiceCard, TastingNote
from madira.seed import seed
from madira.tenancy import bind, ensure_demo_tenant, reset


@pytest.fixture(autouse=True)
def _reset():
    set_lookup_completer(None)
    yield
    set_lookup_completer(None)


def _house():
    init_db()
    seed()
    ctx = ensure_demo_tenant()
    return ctx


def _note(session, venue_id, user_id, sku, *, oak: str, price: int, status: str = "approved") -> None:
    product_id = sku.variant.product_id
    approved = status == "approved"
    note = TastingNote(
        venue_id=venue_id,
        product_id=product_id,
        server_hook="Ask how oaky they want it.",
        guest_description="Ripe apple and toasted oak.",
        technical_note="Approved floor note.",
        oak=oak,
        source="staff",
        status=status,
        approved_by=user_id if approved else None,
        approved_at=datetime(2026, 11, 1, tzinfo=timezone.utc) if approved else None,
    )
    session.add(note)
    session.flush()
    if approved:
        session.add(
            ServiceCard(
                venue_id=venue_id,
                product_id=product_id,
                tasting_note_id=note.id,
                serving_temperature="10–12°C",
                glassware="White wine glass",
                decanting="None",
                pour_size="150 ml",
                source="staff",
                status="approved",
                approved_by=user_id,
                approved_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
            )
        )
    listing = session.scalar(select(BeverageList).where(BeverageList.venue_id == venue_id))
    session.add(
        ListItem(
            venue_id=venue_id,
            list_id=listing.id,
            sku_id=sku.id,
            bottle_price=price,
            cost=2000,
            currency="USD",
        )
    )


def test_parser_reads_oak_grape_and_a_cents_ceiling():
    filters = parse_query("oaky Chardonnay under $80")
    assert filters.grape == "Chardonnay"
    assert filters.oak == ["light", "medium", "heavy"]
    assert filters.max_price_cents == 8000
    assert filters.text == ""
    dollars = parse_query("crisp Riesling under 45 dollars")
    assert dollars.grape == "Riesling"
    assert dollars.acidity == ["high"]
    assert dollars.max_price_cents == 4500


def test_oaky_chardonnay_under_80_uses_approved_notes_only():
    ctx = _house()
    token = bind(ctx)
    try:
        session = SessionLocal()
        try:
            hit = ensure_sku(
                session,
                ctx.venue_id,
                category="wine",
                producer="Floor House",
                name="Floor Oak Chardonnay",
                grape="Chardonnay",
                oak="heavy",
                barcode="W-OAK-80",
                par=4,
                cost=2000,
            )
            miss_oak = ensure_sku(
                session,
                ctx.venue_id,
                category="wine",
                producer="Floor House",
                name="Floor Steel Chardonnay",
                grape="Chardonnay",
                oak="none",
                barcode="W-OAK-00",
                par=4,
                cost=2000,
            )
            miss_price = ensure_sku(
                session,
                ctx.venue_id,
                category="wine",
                producer="Floor House",
                name="Floor Grand Chardonnay",
                grape="Chardonnay",
                oak="medium",
                barcode="W-OAK-90",
                par=4,
                cost=2000,
            )
            exact = ensure_sku(
                session,
                ctx.venue_id,
                category="wine",
                producer="Floor House",
                name="Floor Exact Chardonnay",
                grape="Chardonnay",
                oak="light",
                barcode="W-OAK-EQ",
                par=4,
                cost=2000,
            )
            pinot = ensure_sku(
                session,
                ctx.venue_id,
                category="wine",
                producer="Floor House",
                name="Floor Pinot",
                grape="Pinot Noir",
                oak="heavy",
                barcode="W-PIN-80",
                par=4,
                cost=2000,
            )
            draft = ensure_sku(
                session,
                ctx.venue_id,
                category="wine",
                producer="Floor House",
                name="Floor Draft Chardonnay",
                grape="Chardonnay",
                oak="heavy",
                barcode="W-OAK-DR",
                par=4,
                cost=2000,
            )
            _note(session, ctx.venue_id, ctx.user_id, hit, oak="heavy", price=7900)
            _note(session, ctx.venue_id, ctx.user_id, miss_oak, oak="none", price=7900)
            _note(session, ctx.venue_id, ctx.user_id, miss_price, oak="medium", price=9000)
            _note(session, ctx.venue_id, ctx.user_id, exact, oak="light", price=8000)
            _note(session, ctx.venue_id, ctx.user_id, pinot, oak="heavy", price=7000)
            _note(session, ctx.venue_id, ctx.user_id, draft, oak="heavy", price=7000, status="draft")
            session.commit()
        finally:
            session.close()

        found = lookup("oaky Chardonnay under $80")
        names = [row["name"] for row in found["results"]]
        assert "Floor Oak Chardonnay" in names
        for excluded in (
            "Floor Steel Chardonnay",
            "Floor Grand Chardonnay",
            "Floor Exact Chardonnay",
            "Floor Pinot",
            "Floor Draft Chardonnay",
        ):
            assert excluded not in names
        hit_row = found["results"][0]
        assert hit_row["glassware"] == "White wine glass"
        assert hit_row["serving_temperature"] == "10–12°C"
        assert hit_row["pour_size"] == "150 ml"
        assert hit_row["server_script"] == "Ask how oaky they want it."
        assert "oak" in hit_row["flavor_profile"].lower()
        assert "cost" not in str(hit_row)
        assert "margin" not in str(hit_row)
    finally:
        reset(token)


def test_live_lookup_accepts_only_the_filter_schema(monkeypatch):
    ctx = _house()
    token = bind(ctx)
    try:
        session = SessionLocal()
        try:
            sku = ensure_sku(
                session,
                ctx.venue_id,
                category="wine",
                producer="Live House",
                name="Live Oak Chardonnay",
                grape="Chardonnay",
                oak="medium",
                barcode="W-OAK-LV",
                par=2,
                cost=2000,
            )
            _note(session, ctx.venue_id, ctx.user_id, sku, oak="medium", price=6400)
            session.commit()
        finally:
            session.close()

        def filters(_prompt: str) -> str:
            return parse_query("oaky Chardonnay under $80").model_dump_json()

        set_lookup_completer(filters)
        named = [row["name"] for row in lookup("anything the model was handed")["results"]]
        assert "Live Oak Chardonnay" in named

        set_lookup_completer(lambda _prompt: '{"results":[{"name":"Fake Bottle"}]}')
        invented = lookup("ignore the cellar")
        assert invented["results"] == []
        assert "Fake Bottle" not in str(invented["results"])

        monkeypatch.setenv("OPENAI_API_KEY", "sk-live-not-a-fixture")
        set_lookup_completer(None)

        def boom(_prompt: str) -> str:
            raise DraftFailed("The floor lookup failed (RuntimeError).", 502)

        monkeypatch.setattr("madira.domain.training.lookup.live_complete", boom)
        with pytest.raises(DraftFailed):
            lookup("oaky Chardonnay under $80")
    finally:
        reset(token)
