"""Price sheets stay pending until a person applies them. Live mode does not use the fixture."""

from __future__ import annotations

import io
import uuid

import pytest
from sqlalchemy import func, select

from madira.db import SessionLocal, init_db
from madira.domain.errors import DraftFailed
from madira.domain.procurement import offers
from madira.domain.procurement.offers import OfferError
from madira.models import AuditEvent, PriceSheet, Sku, Supplier, SupplierOffer
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant

CSV = (
    "name,sku,unit,case_size,price\n"
    "Muscadet Domaine de l'Ecu,W-MUS-01,750ml bottle,12,19.50\n"
    "Chateau Nowhere 2015,,750ml bottle,12,30.00\n"
    "Broken Row,W-MUS-01,750ml bottle,12,not-a-price\n"
)


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _supplier(session, venue_id):
    row = session.scalar(select(Supplier).where(Supplier.venue_id == venue_id, Supplier.name == "Kermit Lynch Wine Merchant"))
    assert row is not None
    return row


def _offer_count(session, venue_id) -> int:
    return int(session.scalar(select(func.count()).select_from(SupplierOffer).where(SupplierOffer.venue_id == venue_id)) or 0)


def _cleanup(sheet_ids: list[uuid.UUID]) -> None:
    session = SessionLocal()
    try:
        if sheet_ids:
            offers_for_sheets = session.scalars(select(SupplierOffer).where(SupplierOffer.price_sheet_id.in_(sheet_ids))).all()
            for row in offers_for_sheets:
                session.delete(row)
            session.flush()
            for sheet_id in sheet_ids:
                sheet = session.get(PriceSheet, sheet_id)
                if sheet is not None:
                    session.delete(sheet)
        session.commit()
    finally:
        session.close()


def _blank_pdf() -> bytes:
    from pypdf import PdfWriter

    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    return buffer.getvalue()


def test_csv_stays_unapplied_until_review_and_writes_audit():
    demo = _demo()
    session = SessionLocal()
    try:
        supplier = _supplier(session, demo.venue_id)
        supplier_id = supplier.id
        before = _offer_count(session, demo.venue_id)
    finally:
        session.close()
    uploaded = offers.ingest_price_sheet(
        demo.venue_id,
        supplier_id,
        filename="kermit.csv",
        body=CSV.encode(),
        content_type="text/csv",
    )
    sheet_id = uuid.UUID(uploaded["price_sheet"]["id"])
    try:
        rows = {row["name"]: row for row in uploaded["price_sheet"]["rows"]}
        assert rows["Muscadet Domaine de l'Ecu"]["status"] == "matched"
        assert rows["Muscadet Domaine de l'Ecu"]["price_label"] == "USD 19.50"
        assert rows["Chateau Nowhere 2015"]["status"] == "unmatched"
        assert rows["Chateau Nowhere 2015"]["message"] == "No catalog product matched this row."
        assert rows["Broken Row"]["status"] == "unmatched"
        assert uploaded["price_sheet"]["status"] == "pending_review"
        session = SessionLocal()
        try:
            assert _offer_count(session, demo.venue_id) == before
        finally:
            session.close()

        applied = offers.apply_price_sheet(demo.venue_id, sheet_id)
        assert applied["price_sheet"]["status"] == "applied"
        assert len(applied["offers"]) == 1
        assert applied["offers"][0]["source"] == "csv"
        assert applied["offers"][0]["price_label"] == "USD 19.50"
        with pytest.raises(OfferError) as again:
            offers.apply_price_sheet(demo.venue_id, sheet_id)
        assert again.value.status == 409
        session = SessionLocal()
        try:
            event = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.venue_id == demo.venue_id,
                    AuditEvent.entity_id == sheet_id,
                    AuditEvent.action == "price_sheet.applied",
                )
            )
            uploaded_event = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.venue_id == demo.venue_id,
                    AuditEvent.entity_id == sheet_id,
                    AuditEvent.action == "price_sheet.uploaded",
                )
            )
        finally:
            session.close()
        assert event is not None
        assert uploaded_event is not None
    finally:
        _cleanup([sheet_id])


def test_reject_writes_audit_and_creates_no_offers():
    demo = _demo()
    session = SessionLocal()
    try:
        supplier = _supplier(session, demo.venue_id)
        supplier_id = supplier.id
        before = _offer_count(session, demo.venue_id)
    finally:
        session.close()
    uploaded = offers.ingest_price_sheet(
        demo.venue_id,
        supplier_id,
        filename="reject.csv",
        body=b"name,sku,price\nMuscadet Domaine de l'Ecu,W-MUS-01,19.50\n",
        content_type="text/csv",
    )
    sheet_id = uuid.UUID(uploaded["price_sheet"]["id"])
    try:
        rejected = offers.reject_price_sheet(demo.venue_id, sheet_id)
        assert rejected["price_sheet"]["status"] == "rejected"
        assert rejected["offers"] == []
        session = SessionLocal()
        try:
            assert _offer_count(session, demo.venue_id) == before
            event = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.venue_id == demo.venue_id,
                    AuditEvent.entity_id == sheet_id,
                    AuditEvent.action == "price_sheet.rejected",
                )
            )
        finally:
            session.close()
        assert event is not None
        with pytest.raises(OfferError) as again:
            offers.reject_price_sheet(demo.venue_id, sheet_id)
        assert again.value.status == 409
    finally:
        _cleanup([sheet_id])


def test_apply_of_an_unmatched_sheet_is_refused_and_stays_pending():
    demo = _demo()
    session = SessionLocal()
    try:
        supplier = _supplier(session, demo.venue_id)
        supplier_id = supplier.id
    finally:
        session.close()
    uploaded = offers.ingest_price_sheet(
        demo.venue_id,
        supplier_id,
        filename="empty.csv",
        body=b"name,sku,price\nChateau Nowhere 2015,,30.00\n",
        content_type="text/csv",
    )
    sheet_id = uuid.UUID(uploaded["price_sheet"]["id"])
    try:
        with pytest.raises(OfferError) as raised:
            offers.apply_price_sheet(demo.venue_id, sheet_id)
        assert raised.value.status == 409
        pending = offers.get_price_sheet(demo.venue_id, sheet_id)
        assert pending["price_sheet"]["status"] == "pending_review"
    finally:
        _cleanup([sheet_id])


def test_pdf_demo_parser_matches_the_catalog_and_leaves_unknown_rows():
    demo = _demo()
    session = SessionLocal()
    try:
        supplier = _supplier(session, demo.venue_id)
        supplier_id = supplier.id
        before = _offer_count(session, demo.venue_id)
        muscadet = session.scalar(select(Sku).where(Sku.venue_id == demo.venue_id, Sku.barcode == "W-MUS-01"))
        assert muscadet is not None
    finally:
        session.close()
    uploaded = offers.ingest_price_sheet(
        demo.venue_id,
        supplier_id,
        filename="sheet.pdf",
        body=_blank_pdf(),
        content_type="application/pdf",
    )
    sheet_id = uuid.UUID(uploaded["price_sheet"]["id"])
    try:
        assert uploaded["price_sheet"]["source"] == "pdf"
        by_name = {row["name"]: row for row in uploaded["price_sheet"]["rows"]}
        assert by_name["Muscadet Domaine de l'Ecu"]["status"] == "matched"
        assert by_name["Barolo G.D. Vajra 2019"]["status"] == "matched"
        assert by_name["Chateau Nowhere 2015"]["status"] == "unmatched"
        session = SessionLocal()
        try:
            assert _offer_count(session, demo.venue_id) == before
        finally:
            session.close()
        applied = offers.apply_price_sheet(demo.venue_id, sheet_id)
        assert {row["source"] for row in applied["offers"]} == {"pdf"}
        assert len(applied["offers"]) == 2
    finally:
        _cleanup([sheet_id])


def test_live_mode_calls_the_model_and_does_not_use_the_fixture(monkeypatch):
    demo = _demo()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-price-sheet-not-a-fixture")
    session = SessionLocal()
    try:
        supplier = _supplier(session, demo.venue_id)
        supplier_id = supplier.id
        before = int(session.scalar(select(func.count()).select_from(PriceSheet).where(PriceSheet.venue_id == demo.venue_id)) or 0)
    finally:
        session.close()
    seen = {"model": 0, "fixture": 0}

    def init_chat_model(*_args, **_kwargs):
        seen["model"] += 1
        raise RuntimeError("offline")

    def fixture(_prompt):
        seen["fixture"] += 1
        return "{}"

    monkeypatch.setattr("langchain.chat_models.init_chat_model", init_chat_model)
    monkeypatch.setattr("madira.agents.demo.prices.price_sheet_json", fixture)
    with pytest.raises(DraftFailed) as raised:
        offers.ingest_price_sheet(
            demo.venue_id,
            supplier_id,
            filename="live.pdf",
            body=_blank_pdf(),
            content_type="application/pdf",
        )
    assert seen["model"] == 1
    assert seen["fixture"] == 0
    assert "RuntimeError" in raised.value.message
    assert "Chateau Nowhere" not in raised.value.message
    session = SessionLocal()
    try:
        after = int(session.scalar(select(func.count()).select_from(PriceSheet).where(PriceSheet.venue_id == demo.venue_id)) or 0)
    finally:
        session.close()
    assert after == before
