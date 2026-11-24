"""Receiving: vault the invoice, match three ways, then post stock."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from madira.auth import issue_session, utcnow
from madira.domain.catalog.service import ensure_sku
from madira.domain.compliance.service import verify_audit_chain
from madira.domain.inventory.ledger import public_qty
from madira.domain.procurement.receiving import ReceivingError, compute_three_way_match
from madira.domain.session import session_scope
from madira.main import app
from madira.models import AuditEvent, Document, InventoryItem, Membership, Sku, StockMovement, User, Venue
from madira.storage import get_storage
from madira.tenancy import AUDITOR, OWNER, STAFF, ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "receiving-invoice-test-secret"
PDF = b"%PDF-1.4\nreceiving invoice\n%%EOF\n"
JPEG = b"\xff\xd8\xff\x00receiving-photo"


def test_three_way_match_flags_short_over_vintage_and_price():
    lines, summary = compute_three_way_match(
        [
            {
                "id": "a",
                "sku": "A",
                "product_name": "Bottle A",
                "quantity_ordered": 10,
                "quantity_received": 0,
                "unit_cost_cents": 1500,
                "vintage": "2019",
            },
            {
                "id": "b",
                "sku": "B",
                "product_name": "Bottle B",
                "quantity_ordered": 2,
                "quantity_received": 0,
                "unit_cost_cents": 900,
                "vintage": "2021",
            },
        ],
        [
            {"sku": "A", "quantity": 10, "unit_cost_cents": 1800, "vintage": "2019"},
            {"sku": "B", "quantity": 2, "unit_cost_cents": 900, "vintage": "2021"},
        ],
        [
            {"po_line_id": "a", "sku": "A", "counted_qty": 6, "received_vintage": "2020"},
            {"po_line_id": "b", "sku": "B", "counted_qty": 3, "received_vintage": "2021"},
        ],
    )
    by_sku = {row["sku"]: row for row in lines}
    assert "short" in by_sku["A"]["flags"]
    assert "vintage_substitution" in by_sku["A"]["flags"]
    assert "price_change" in by_sku["A"]["flags"]
    assert by_sku["A"]["cost_delta_cents"] == 300
    assert "over" in by_sku["B"]["flags"]
    assert summary["has_discrepancies"] is True
    assert summary["cost_delta_cents"] == 300
    assert summary["counts"]["short"] == 1
    assert summary["counts"]["over"] == 1


def test_match_rejects_a_line_that_is_not_on_the_order():
    with pytest.raises(ReceivingError):
        compute_three_way_match(
            [{"id": "a", "sku": "A", "quantity_ordered": 1, "quantity_received": 0, "unit_cost_cents": 1, "vintage": None}],
            None,
            [{"sku": "NOPE", "counted_qty": 1}],
        )


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _cookie(client, monkeypatch, role: str) -> None:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    demo = ensure_demo_tenant()
    sub = f"rcv-{role.lower()}-{uuid.uuid4().hex[:8]}"
    now = utcnow()
    with session_scope() as session:
        user = User(google_sub=sub, email=f"{sub}@example.com", name=role, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, venue_id=demo.venue_id, role=role))
        session.commit()
    client.cookies.set("madira_session", issue_session(sub))


def _owner(client):
    client.cookies.delete("madira_session")


def _stock(barcode: str, name: str, cost: int, vintage: str) -> None:
    demo = ensure_demo_tenant()
    with session_scope() as session:
        ensure_sku(
            session,
            demo.venue_id,
            category="wine",
            name=name,
            barcode=barcode,
            cost=cost,
            vintage=vintage,
            par=0,
        )
        session.commit()


def test_receive_flow_vaults_invoices_posts_stock_and_keeps_the_chain(client, monkeypatch):
    demo = ensure_demo_tenant()
    suffix = uuid.uuid4().hex[:6].upper()
    sku_a = f"RCV-A-{suffix}"
    sku_b = f"RCV-B-{suffix}"
    _stock(sku_a, f"Receive A {suffix}", 1500, "2019")
    _stock(sku_b, f"Receive B {suffix}", 900, "2021")

    supplier = client.post(
        "/procurement/suppliers",
        json={"name": f"Receiving House {suffix}", "default_case_size": 1, "order_minimum_cents": 0},
    )
    assert supplier.status_code == 200, supplier.text
    supplier_id = supplier.json()["supplier"]["id"]
    drafted = client.post(
        "/procurement/orders",
        json={
            "supplier_id": supplier_id,
            "lines": [
                {"sku": sku_a, "product_name": "Bottle A", "bottles": 10, "case_size": 1, "unit_cost_cents": 1500},
                {"sku": sku_b, "product_name": "Bottle B", "bottles": 2, "case_size": 1, "unit_cost_cents": 900},
            ],
        },
    )
    assert drafted.status_code == 200, drafted.text
    po_id = drafted.json()["id"]
    early = client.post(
        f"/procurement/orders/{po_id}/receipts",
        json={"lines": [{"sku": sku_a, "counted_qty": 1}]},
    )
    assert early.status_code == 409

    approved = client.post(f"/procurement/orders/{po_id}/approve", json={"comment": "Receive it."})
    assert approved.status_code == 200, approved.text
    sent = client.post(f"/procurement/orders/{po_id}/send")
    assert sent.status_code == 200, sent.text
    sent_lines = {line["sku"]: line for line in sent.json()["lines"]}
    assert sent_lines[sku_a]["quantity_ordered"] == 10
    assert sent_lines[sku_a]["vintage"] == "2019"

    photo = client.post(
        f"/procurement/orders/{po_id}/invoices",
        files={"file": ("delivery.jpg", JPEG, "image/jpeg")},
        data={"invoice_number": f"PHOTO-{suffix}", "invoice_date": "2026-11-24"},
    )
    assert photo.status_code == 200, photo.text
    photo_body = photo.json()
    assert photo_body["extraction_mode"] == "demo"
    assert photo_body["status"] == "uploaded"
    assert {line["sku"] for line in photo_body["extracted_lines"]} == {sku_a, sku_b}
    assert photo_body["sha256"] == hashlib.sha256(JPEG).hexdigest()

    invoice_lines = [
        {
            "sku": sku_a,
            "product_name": "Bottle A",
            "quantity": 10,
            "unit_cost_cents": 1800,
            "vintage": "2019",
            "po_line_id": sent_lines[sku_a]["id"],
        },
        {
            "sku": sku_b,
            "product_name": "Bottle B",
            "quantity": 2,
            "unit_cost_cents": 900,
            "vintage": "2021",
            "po_line_id": sent_lines[sku_b]["id"],
        },
    ]
    filed = client.post(
        f"/procurement/orders/{po_id}/invoices",
        files={"file": ("delivery.pdf", PDF, "application/pdf")},
        data={
            "invoice_number": f"INV-{suffix}",
            "invoice_date": "2026-11-24",
            "tax_cents": "0",
            "lines_json": json.dumps(invoice_lines),
        },
    )
    assert filed.status_code == 200, filed.text
    invoice = filed.json()
    assert invoice["extraction_mode"] == "manual"
    assert invoice["subtotal_cents"] == 1800 * 10 + 900 * 2
    invoice_id = invoice["id"]
    digest = hashlib.sha256(PDF).hexdigest()
    assert invoice["sha256"] == digest

    direct = client.get(f"/procurement/invoices/{invoice_id}/document")
    assert direct.status_code == 200
    assert direct.content == PDF
    vault = client.get(f"/compliance/documents/{invoice['document_id']}/download")
    assert vault.status_code == 200
    assert vault.content == PDF
    photo_file = client.get(f"/procurement/invoices/{photo_body['id']}/document")
    assert photo_file.status_code == 200
    assert photo_file.content == JPEG
    with session_scope() as session:
        document = session.get(Document, uuid.UUID(invoice["document_id"]))
        assert document is not None
        assert document.doc_type == "invoice"
        assert document.sha256 == digest
        assert document.linked_entity_type == "invoice"
        assert str(document.linked_entity_id) == invoice_id
        assert get_storage().read(document.storage_key) == PDF
        photo_doc = session.get(Document, uuid.UUID(photo_body["document_id"]))
        assert photo_doc is not None
        assert photo_doc.sha256 == hashlib.sha256(JPEG).hexdigest()
        assert get_storage().read(photo_doc.storage_key) == JPEG

    staged = client.post(
        f"/procurement/orders/{po_id}/receipts",
        json={
            "invoice_id": invoice_id,
            "lines": [
                {"po_line_id": sent_lines[sku_a]["id"], "sku": sku_a, "counted_qty": 6, "received_vintage": "2020"},
                {"po_line_id": sent_lines[sku_b]["id"], "sku": sku_b, "counted_qty": 3, "received_vintage": "2021"},
            ],
        },
    )
    assert staged.status_code == 200, staged.text
    receipt = staged.json()
    assert receipt["status"] == "draft"
    assert receipt["discrepancy_summary"]["has_discrepancies"] is True
    assert receipt["discrepancy_summary"]["cost_delta_cents"] == 300
    flags = {flag for line in receipt["lines"] for flag in line["flags"]}
    assert {"short", "over", "vintage_substitution", "price_change"} <= flags
    assert "ReceivingChecklist" in json.dumps(receipt["a2ui_operations"])
    receipt_id = receipt["id"]
    stored_invoice = client.get(f"/procurement/invoices/{invoice_id}")
    assert stored_invoice.json()["status"] == "discrepancy"

    denied = client.post(f"/procurement/receipts/{receipt_id}/accept", json={"acknowledge_discrepancies": False})
    assert denied.status_code == 409
    detail = denied.json()["detail"]
    denied_flags = {flag for row in detail["flagged"] for flag in row["flags"]}
    assert {"short", "over", "vintage_substitution", "price_change"} <= denied_flags
    assert detail["discrepancy_summary"]["cost_delta_cents"] == 300

    _cookie(client, monkeypatch, AUDITOR)
    assert client.get(f"/procurement/invoices/{invoice_id}").status_code == 200
    assert client.get("/procurement/receipts").status_code == 200
    assert client.post(
        f"/procurement/orders/{po_id}/invoices",
        files={"file": ("no.pdf", PDF, "application/pdf")},
        data={"invoice_number": "NO", "invoice_date": "2026-11-24"},
    ).status_code == 403
    assert client.post(
        f"/procurement/orders/{po_id}/receipts",
        json={"lines": [{"sku": sku_a, "counted_qty": 1}]},
    ).status_code == 403
    assert client.post(f"/procurement/receipts/{receipt_id}/accept", json={"acknowledge_discrepancies": True}).status_code == 403
    _cookie(client, monkeypatch, STAFF)
    assert client.get("/procurement/invoices").status_code == 403
    assert client.get(f"/procurement/receipts/{receipt_id}").status_code == 403
    assert client.post(f"/procurement/receipts/{receipt_id}/accept", json={}).status_code == 403
    _owner(client)

    accepted = client.post(
        f"/procurement/receipts/{receipt_id}/accept",
        json={"acknowledge_discrepancies": True, "notes": "Short case, price checked."},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["purchase_order_status"] == "part_received"
    assert client.get(f"/procurement/invoices/{invoice_id}").json()["status"] == "accepted"

    second = client.post(
        f"/procurement/orders/{po_id}/receipts",
        json={"lines": [{"po_line_id": sent_lines[sku_a]["id"], "sku": sku_a, "counted_qty": 4, "received_vintage": "2019"}]},
    )
    assert second.status_code == 200, second.text
    assert second.json()["discrepancy_summary"]["has_discrepancies"] is False
    finished = client.post(
        f"/procurement/receipts/{second.json()['id']}/accept",
        json={"acknowledge_discrepancies": False},
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["purchase_order_status"] == "received"
    closed = client.post(f"/procurement/orders/{po_id}/close")
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"

    with session_scope() as session:
        stock_a = session.scalar(sa.select(Sku).where(Sku.venue_id == demo.venue_id, Sku.barcode == sku_a))
        stock_b = session.scalar(sa.select(Sku).where(Sku.venue_id == demo.venue_id, Sku.barcode == sku_b))
        assert stock_a is not None and stock_b is not None
        assert stock_a.cost == 1800
        assert stock_b.cost == 900
        on_a = session.scalar(sa.select(InventoryItem).where(InventoryItem.sku_id == stock_a.id))
        on_b = session.scalar(sa.select(InventoryItem).where(InventoryItem.sku_id == stock_b.id))
        assert on_a is not None and public_qty(on_a.on_hand) == 10
        assert on_b is not None and public_qty(on_b.on_hand) == 3
        movements = session.scalars(
            sa.select(StockMovement).where(StockMovement.venue_id == demo.venue_id, StockMovement.sku_id.in_([stock_a.id, stock_b.id]))
        ).all()
        assert movements
        assert {row.movement_type for row in movements} == {"receive"}
        assert {row.reason for row in movements} == {"receive"}
        assert {row.source_type for row in movements} == {"receipt"}
        assert sum(row.quantity for row in movements if row.sku_id == stock_a.id) == 10
        actions = set(
            session.scalars(sa.select(AuditEvent.action).where(AuditEvent.venue_id == demo.venue_id)).all()
        )
        assert {"invoice.uploaded", "receipt.staged", "receipt.accepted", "sku.cost_changed"} <= actions
        chain = verify_audit_chain(session, demo.venue_id)
        assert chain["valid"] is True
        assert chain["checked_count"] > 0

    other = Venue(organization_id=demo.organization_id, name="Receive Other", slug=f"rcv-other-{suffix}")
    with session_scope() as session:
        session.add(other)
        session.commit()
        foreign_id = other.id
    from madira.domain.procurement import orders as order_lifecycle

    hidden_supplier = order_lifecycle.create_supplier(foreign_id, {"name": "Foreign Receiver", "default_case_size": 1})
    hidden = order_lifecycle.create_purchase_order(
        foreign_id,
        uuid.UUID(hidden_supplier["supplier"]["id"]),
        [{"sku": "FOR-R", "product_name": "Foreign", "bottles": 1, "case_size": 1, "unit_cost_cents": 100}],
        type("Actor", (), {"user_id": None, "email": "owner@example.com", "role": OWNER})(),
    )
    assert client.get(f"/procurement/orders/{hidden['id']}").status_code == 404
    assert client.get(f"/procurement/invoices/{invoice_id}").status_code == 200
    missing = client.get(f"/procurement/invoices/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert client.get(f"/procurement/receipts/{uuid.uuid4()}").status_code == 404
    assert client.post(f"/procurement/orders/{hidden['id']}/receipts", json={"lines": [{"sku": "FOR-R", "counted_qty": 1}]}).status_code == 404


def test_vision_extraction_falls_back_and_can_succeed(client, monkeypatch):
    demo = ensure_demo_tenant()
    suffix = uuid.uuid4().hex[:6].upper()
    sku = f"VIS-{suffix}"
    _stock(sku, f"Vision {suffix}", 1000, "2018")
    supplier = client.post(
        "/procurement/suppliers",
        json={"name": f"Vision House {suffix}", "default_case_size": 1, "order_minimum_cents": 0},
    )
    assert supplier.status_code == 200, supplier.text
    drafted = client.post(
        "/procurement/orders",
        json={
            "supplier_id": supplier.json()["supplier"]["id"],
            "lines": [{"sku": sku, "product_name": "Vision bottle", "bottles": 2, "case_size": 1, "unit_cost_cents": 1000}],
        },
    )
    assert drafted.status_code == 200, drafted.text
    po_id = drafted.json()["id"]
    assert client.post(f"/procurement/orders/{po_id}/approve", json={}).status_code == 200
    assert client.post(f"/procurement/orders/{po_id}/send").status_code == 200

    monkeypatch.setattr("madira.domain.procurement.receiving._vision_ready", lambda: True)

    def boom(**kwargs):
        raise RuntimeError("vision down")

    monkeypatch.setattr("madira.domain.procurement.receiving._call_vision", boom)
    fallback = client.post(
        f"/procurement/orders/{po_id}/invoices",
        files={"file": ("shot.jpg", JPEG, "image/jpeg")},
        data={"invoice_number": f"FALL-{suffix}", "invoice_date": "2026-11-24"},
    )
    assert fallback.status_code == 200, fallback.text
    assert fallback.json()["extraction_mode"] == "demo"
    assert fallback.json()["extracted_lines"][0]["unit_cost_cents"] == 1000

    def read(**kwargs):
        return [{"sku": sku, "product_name": "Vision bottle", "quantity": 2, "unit_cost_cents": 1250, "vintage": "2018"}]

    monkeypatch.setattr("madira.domain.procurement.receiving._call_vision", read)
    seen = client.post(
        f"/procurement/orders/{po_id}/invoices",
        files={"file": ("shot.jpg", JPEG, "image/jpeg")},
        data={"invoice_number": f"SEE-{suffix}", "invoice_date": "2026-11-24"},
    )
    assert seen.status_code == 200, seen.text
    assert seen.json()["extraction_mode"] == "vision"
    assert seen.json()["extracted_lines"][0]["unit_cost_cents"] == 1250


def test_migration_0013_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0013_receiving_invoices.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0012_purchasing_lifecycle"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert source.count('_enable_rls("') == 3
    assert 'if not _is_postgres():' in source
    db = tmp_path / "receiving.db"
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
    assert version == "0013_receiving_invoices"
    tables = set(sa.inspect(conn).get_table_names())
    assert {"invoices", "receipts", "receipt_lines"} <= tables
    invoice_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(invoices)"))}
    assert {"venue_id", "supplier_id", "purchase_order_id", "invoice_number", "invoice_date", "document_id", "extracted_lines", "extraction_mode", "status"} <= invoice_cols
    receipt_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(receipts)"))}
    assert {"purchase_order_id", "invoice_id", "status", "discrepancies_acknowledged", "discrepancy_summary", "received_at", "accepted_at"} <= receipt_cols
    line_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(receipt_lines)"))}
    assert {"receipt_id", "po_line_id", "sku", "ordered_qty", "invoiced_qty", "counted_qty", "ordered_unit_cost_cents", "invoiced_unit_cost_cents", "flags", "bin_id"} <= line_cols
command.downgrade(cfg, "0012_purchasing_lifecycle")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0012_purchasing_lifecycle"
    tables = set(sa.inspect(conn).get_table_names())
    assert "invoices" not in tables
    assert "receipts" not in tables
    assert "receipt_lines" not in tables
command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0013_receiving_invoices"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
