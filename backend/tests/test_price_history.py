"""Price history merges offers and invoice line costs. Labels come from the service."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.domain.compliance.service import store_document
from madira.domain.procurement import offers
from madira.domain.procurement.offers import money_label
from madira.models import Invoice, Sku, Supplier, SupplierOffer, Venue
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant


def test_history_merges_offers_and_invoice_lines_with_service_labels():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    offer_id = None
    invoice_id = None
    try:
        sku = session.scalar(select(Sku).where(Sku.venue_id == demo.venue_id, Sku.barcode == "W-MUS-01"))
        assert sku is not None and sku.variant is not None
        product = sku.variant.product
        supplier = session.scalar(
            select(Supplier).where(Supplier.venue_id == demo.venue_id, Supplier.name == "Kermit Lynch Wine Merchant")
        )
        assert supplier is not None
        other_sku = session.scalar(select(Sku).where(Sku.venue_id == demo.venue_id, Sku.barcode == "W-BAR-01"))
        assert other_sku is not None and other_sku.variant is not None
        other_product_id = other_sku.variant.product.id
        document = store_document(
            session,
            org_id=demo.organization_id,
            venue_id=demo.venue_id,
            doc_type="other",
            filename="invoice.txt",
            content_type="text/plain",
            body=b"invoice",
            linked_entity_type="invoice",
        )
        invoice = Invoice(
            venue_id=demo.venue_id,
            supplier_id=supplier.id,
            invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
            invoice_date="2026-01-15",
            currency="USD",
            document_id=document.id,
            extracted_lines=[{"sku": "W-MUS-01", "product_name": product.name, "quantity": 6, "unit_cost_cents": 1800}],
            extraction_mode="manual",
            status="accepted",
        )
        offer = SupplierOffer(
            venue_id=demo.venue_id,
            supplier_id=supplier.id,
            product_id=product.id,
            sku_id=sku.id,
            unit_description="750ml bottle",
            case_size=12,
            price_cents=1950,
            currency="USD",
            valid_from=date(2026, 11, 1),
            source="manual",
        )
        session.add(invoice)
        session.add(offer)
        session.commit()
        offer_id = offer.id
        invoice_id = invoice.id
        product_id = product.id
        other = Venue(
            organization_id=demo.organization_id,
            name="Other History",
            slug=f"other-history-{uuid.uuid4().hex[:8]}",
        )
        session.add(other)
        session.commit()
        other_id = other.id
    finally:
        session.close()

    try:
        assert money_label(1800, "USD") == "USD 18.00"
        assert money_label(1950, "USD") == "USD 19.50"
        history = offers.price_history(demo.venue_id, product_id)
        mine = [point for point in history["points"] if point["offer_id"] == str(offer_id) or point["invoice_id"] == str(invoice_id)]
        assert [point["kind"] for point in mine] == ["invoice", "offer"]
        assert mine[0]["price_cents"] == 1800
        assert mine[0]["price_label"] == "USD 18.00"
        assert mine[0]["date"] == "2026-01-15"
        assert mine[1]["price_cents"] == 1950
        assert mine[1]["price_label"] == "USD 19.50"
        other_product = offers.price_history(demo.venue_id, other_product_id)
        assert all(point["invoice_id"] != str(invoice_id) and point["offer_id"] != str(offer_id) for point in other_product["points"])
        foreign = offers.price_history(other_id, product_id)
        assert all(point["invoice_id"] != str(invoice_id) and point["offer_id"] != str(offer_id) for point in foreign["points"])
    finally:
        session = SessionLocal()
        try:
            if offer_id is not None:
                row = session.get(SupplierOffer, offer_id)
                if row is not None:
                    session.delete(row)
            if invoice_id is not None:
                row = session.get(Invoice, invoice_id)
                if row is not None:
                    session.delete(row)
            session.commit()
        finally:
            session.close()
