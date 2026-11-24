"""Purchase orders: case rounding, Owner-only decisions, vault PDF, no outbound email."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from madira.auth import issue_session, utcnow
from madira.domain.compliance.service import verify_audit_chain
from madira.domain.procurement import orders
from madira.domain.procurement.email_adapter import VaultArchiveEmailAdapter, get_po_email_adapter
from madira.domain.procurement.orders import OrderError, cases_for_bottles, next_delivery_date
from madira.domain.session import session_scope
from madira.main import app
from madira.models import Approval, Document, Membership, PurchaseOrder, User, Venue
from madira.storage import get_storage
from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "purchasing-lifecycle-test-secret"


def test_case_rounding_minimum_and_delivery_day():
    assert cases_for_bottles(5, 12) == (1, 12)
    assert cases_for_bottles(12, 12) == (1, 12)
    assert cases_for_bottles(13, 6) == (3, 18)
    assert next_delivery_date(["Tue", "Thu"], 7, date(2026, 11, 23)) == date(2026, 12, 1)
    assert next_delivery_date([], 3, date(2026, 11, 23)) == date(2026, 11, 26)
    with pytest.raises(OrderError):
        orders.normalize_delivery_days(["Funday"])


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _cookie(client, monkeypatch, role: str) -> None:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    demo = ensure_demo_tenant()
    sub = f"po-{role.lower()}-{uuid.uuid4().hex[:8]}"
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


def test_owner_approval_archives_pdf_and_keeps_the_chain(client, monkeypatch):
    monkeypatch.setattr("smtplib.SMTP", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("smtp")))
    monkeypatch.delenv("MADIRA_PO_EMAIL_ENABLED", raising=False)
    assert isinstance(get_po_email_adapter(), VaultArchiveEmailAdapter)
    monkeypatch.setenv("MADIRA_PO_EMAIL_ENABLED", "true")
    assert isinstance(get_po_email_adapter(), VaultArchiveEmailAdapter)
    monkeypatch.delenv("MADIRA_PO_EMAIL_ENABLED", raising=False)

    demo = ensure_demo_tenant()
    sommelier = SimpleNamespace(user_id=None, email="sommelier@example.com", role=SOMMELIER)
    unmet = client.post(
        "/procurement/suppliers",
        json={
            "name": f"Case House {uuid.uuid4().hex[:6]}",
            "default_case_size": 6,
            "order_minimum_cents": 5000,
            "delivery_days": ["Tue", "Thu"],
            "lead_time_days": 7,
            "payment_terms": "Net 30",
        },
    )
    assert unmet.status_code == 200, unmet.text
    supplier_id = unmet.json()["supplier"]["id"]
    contact = client.post(
        f"/procurement/suppliers/{supplier_id}/contacts",
        json={"name": "Ada Case", "email": "ada.case@example.com", "role": "Buyer", "is_primary": True},
    )
    assert contact.status_code == 200, contact.text
    assert contact.json()["contact"]["is_primary"] is True
    duplicate = client.post(
        "/procurement/suppliers",
        json={"name": unmet.json()["supplier"]["name"], "default_case_size": 6},
    )
    assert duplicate.status_code == 409

    short = client.post(
        "/procurement/orders",
        json={
            "supplier_id": supplier_id,
            "lines": [
                {
                    "sku": "CASE-01",
                    "product_name": "House red",
                    "bottles": 5,
                    "case_size": 6,
                    "unit_cost_cents": 200,
                }
            ],
        },
    )
    assert short.status_code == 200, short.text
    short_body = short.json()
    assert short_body["lines"][0]["cases_ordered"] == 1
    assert short_body["lines"][0]["quantity_ordered"] == 6
    assert short_body["subtotal_cents"] == 1200
    assert short_body["minimum_met"] is False
    assert short_body["shortfall_cents"] == 3800
    assert short_body["expected_delivery_date"]
    assert "ApprovalCard" in json.dumps(short_body["a2ui_operations"])

    tiny = client.post(
        "/procurement/suppliers",
        json={"name": f"Tiny {uuid.uuid4().hex[:6]}", "default_case_size": 1, "order_minimum_cents": 0},
    )
    assert tiny.status_code == 200, tiny.text
    drafted = client.post(
        "/procurement/orders",
        json={
            "supplier_id": tiny.json()["supplier"]["id"],
            "lines": [{"sku": "TINY-10", "product_name": "Ten dollar bottle", "bottles": 1, "unit_cost_cents": 1000}],
        },
    )
    assert drafted.status_code == 200, drafted.text
    po_id = drafted.json()["id"]
    assert drafted.json()["subtotal_cents"] == 1000
    assert drafted.json()["approval"]["required_role"] == "owner"
    assert drafted.json()["approval"]["decision"] == "pending"
    assert drafted.json()["status"] == "draft"

    with pytest.raises(OrderError) as denied:
        orders.approve_purchase_order(demo.venue_id, uuid.UUID(po_id), sommelier)
    assert denied.value.status == 403
    with pytest.raises(OrderError) as rejected_role:
        orders.reject_purchase_order(demo.venue_id, uuid.UUID(po_id), SimpleNamespace(user_id=None, email="m@example.com", role=MANAGER))
    assert rejected_role.value.status == 403

    for role in (SOMMELIER, MANAGER, STAFF, AUDITOR):
        _cookie(client, monkeypatch, role)
        approved = client.post(f"/procurement/orders/{po_id}/approve", json={"comment": "no"})
        rejected = client.post(f"/procurement/orders/{po_id}/reject", json={"comment": "no"})
        assert approved.status_code == 403, role
        assert rejected.status_code == 403, role
    _cookie(client, monkeypatch, STAFF)
    assert client.get("/procurement/orders").status_code == 403
    _cookie(client, monkeypatch, AUDITOR)
    assert client.get(f"/procurement/orders/{po_id}").status_code == 200
    assert client.post(f"/procurement/orders/{po_id}/send").status_code == 403

    _owner(client)
    early = client.post(f"/procurement/orders/{po_id}/send")
    assert early.status_code == 409
    closed = client.post(f"/procurement/orders/{po_id}/close")
    assert closed.status_code == 409
    decision = client.post(f"/procurement/orders/{po_id}/approve", json={"comment": "Release it."})
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "approved"
    with session_scope() as session:
        row = session.scalar(sa.select(Approval).where(Approval.entity_id == uuid.UUID(po_id)))
        assert row is not None
        assert row.decision == "approved"
        assert row.required_role == "owner"
        assert row.comment == "Release it."
        assert row.decided_by_user_id == demo.user_id

    again = client.post(f"/procurement/orders/{po_id}/approve", json={})
    assert again.status_code == 409

    _cookie(client, monkeypatch, SOMMELIER)
    sent = client.post(f"/procurement/orders/{po_id}/send")
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["status"] == "sent"
    assert body["sent_via"] == "vault_archive"
    assert body["delivery_adapter_ref"] == f"vault-archive:{body['po_number']}"
    assert body["pdf_document_id"]
    second = client.post(f"/procurement/orders/{po_id}/send")
    assert second.status_code == 409
    canceled = client.post(f"/procurement/orders/{po_id}/cancel")
    assert canceled.status_code == 409

    _owner(client)
    pdf = client.get(f"/procurement/orders/{po_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF-")
    assert body["po_number"].encode() in pdf.content
    vault = client.get(f"/compliance/documents/{body['pdf_document_id']}/download")
    assert vault.status_code == 200
    assert vault.content == pdf.content
    digest = hashlib.sha256(pdf.content).hexdigest()
    with session_scope() as session:
        document = session.get(Document, uuid.UUID(body["pdf_document_id"]))
        assert document is not None
        assert document.doc_type == "purchase_order"
        assert document.sha256 == digest
        assert document.linked_entity_type == "purchase_order"
        assert get_storage().read(document.storage_key) == pdf.content
        stored = session.get(PurchaseOrder, uuid.UUID(po_id))
        assert stored is not None
        assert stored.sent_via == "vault_archive"
        assert verify_audit_chain(session, demo.venue_id)["valid"] is True

    actor = SimpleNamespace(user_id=demo.user_id, email=demo.email, role=OWNER)
    partial = orders.mark_part_received(demo.venue_id, uuid.UUID(po_id), actor)
    assert partial["status"] == "part_received"
    received = orders.mark_received(demo.venue_id, uuid.UUID(po_id), actor)
    assert received["status"] == "received"
    finished = client.post(f"/procurement/orders/{po_id}/close")
    assert finished.status_code == 200, finished.text
    assert finished.json()["status"] == "closed"
    assert client.post(f"/procurement/orders/{po_id}/close").status_code == 409

    other_org = demo.organization_id
    with session_scope() as session:
        foreign = Venue(organization_id=other_org, name="PO Other", slug=f"po-other-{uuid.uuid4().hex[:8]}")
        session.add(foreign)
        session.commit()
        foreign_id = foreign.id
    hidden_supplier = orders.create_supplier(
        foreign_id,
        {"name": "Foreign House", "default_case_size": 12, "order_minimum_cents": 0},
    )
    hidden = orders.create_purchase_order(
        foreign_id,
        uuid.UUID(hidden_supplier["supplier"]["id"]),
        [{"sku": "FOR-1", "product_name": "Foreign", "bottles": 1, "case_size": 1, "unit_cost_cents": 100}],
        actor,
    )
    assert client.get(f"/procurement/orders/{hidden['id']}").status_code == 404
    assert client.post(f"/procurement/orders/{hidden['id']}/approve", json={}).status_code == 404
    names = {row["name"] for row in client.get("/procurement/suppliers").json()["suppliers"]}
    assert "Foreign House" not in names

    fresh = client.post(
        "/procurement/orders",
        json={
            "supplier_id": tiny.json()["supplier"]["id"],
            "lines": [{"sku": "TINY-11", "product_name": "Another", "bottles": 1, "unit_cost_cents": 100}],
        },
    )
    assert fresh.status_code == 200, fresh.text
    fresh_id = fresh.json()["id"]
    declined = client.post(f"/procurement/orders/{fresh_id}/reject", json={"comment": "Not this week."})
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "canceled"
    assert declined.json()["approval"]["decision"] == "rejected"
    assert client.post(f"/procurement/orders/{fresh_id}/send").status_code == 409

    with session_scope() as session:
        chain = verify_audit_chain(session, demo.venue_id)
        assert chain["valid"] is True
        assert chain["checked_count"] > 0
        found = session.scalars(
            sa.select(PurchaseOrder.status).where(PurchaseOrder.id == uuid.UUID(po_id))
        ).one()
        assert found == "closed"


def test_migration_0012_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0012_purchasing_lifecycle.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0011_counts_and_par"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert source.count('_enable_rls("') == 2
    db = tmp_path / "purchasing.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "0012_purchasing_lifecycle")
engine = sa.create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0012_purchasing_lifecycle"
    tables = set(sa.inspect(conn).get_table_names())
    assert {"supplier_contacts", "approvals", "purchase_orders", "po_lines", "suppliers"} <= tables
    supplier_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(suppliers)"))}
    assert {"account_number", "order_minimum_cents", "default_case_size", "delivery_days", "lead_time_days", "payment_terms", "created_at"} <= supplier_cols
    order_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(purchase_orders)"))}
    assert {"po_number", "status", "expected_delivery_date", "subtotal_cents", "minimum_met", "pdf_document_id", "sent_via", "created_by_user_id"} <= order_cols
    line_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(po_lines)"))}
    assert {"po_id", "sku", "sku_id", "product_name", "case_size", "cases_ordered", "quantity_ordered", "quantity_received", "unit_cost_cents", "line_total_cents"} <= line_cols
    approval_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(approvals)"))}
    assert {"entity_type", "entity_id", "decision", "required_role", "decided_by_user_id"} <= approval_cols
    sql = conn.execute(sa.text("SELECT sql FROM sqlite_master WHERE name = 'documents'")).scalar_one()
    assert "purchase_order" in sql
command.downgrade(cfg, "0011_counts_and_par")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0011_counts_and_par"
    tables = set(sa.inspect(conn).get_table_names())
    assert "supplier_contacts" not in tables
    assert "approvals" not in tables
    assert "purchase_orders" in tables
    order_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(purchase_orders)"))}
    assert "po_number" not in order_cols
    sql = conn.execute(sa.text("SELECT sql FROM sqlite_master WHERE name = 'documents'")).scalar_one()
    assert "purchase_order" not in sql
command.upgrade(cfg, "0012_purchasing_lifecycle")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0012_purchasing_lifecycle"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
