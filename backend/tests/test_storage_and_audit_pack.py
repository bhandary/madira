"""Storage zones, excursion alerts, and the audit-pack export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import uuid
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from madira.agents.orchestrator import SUBAGENT_SPECS
from madira.agents.tools import COMPLIANCE_TOOLS, get_storage_zones_status
from madira.auth import issue_session, utcnow
from madira.domain.catalog.service import ensure_sku
from madira.domain.compliance.service import verify_audit_chain
from madira.domain.procurement.orders import mark_received
from madira.domain.procurement.receiving import upload_invoice
from madira.domain.session import session_scope
from madira.main import app
from madira.models import ConditionReading, Membership, StorageZone, User, Venue
from madira.seed import seed
from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, bind, ensure_demo_tenant, reset

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "storage-audit-pack-test-secret"
PDF = b"%PDF-1.4\nstorage audit invoice\n%%EOF\n"


def _cookie(client, monkeypatch, role: str, venue_id=None) -> None:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    demo = ensure_demo_tenant()
    target = demo.venue_id if venue_id is None else venue_id
    sub = f"zone-{role.lower()}-{uuid.uuid4().hex[:8]}"
    now = utcnow()
    with session_scope() as session:
        user = User(google_sub=sub, email=f"{sub}@example.com", name=role, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, venue_id=target, role=role))
        session.commit()
    client.cookies.set("madira_session", issue_session(sub))


def _owner(client) -> None:
    client.cookies.delete("madira_session")


def _window() -> tuple[str, str]:
    today = date.today()
    return (today - timedelta(days=2)).isoformat(), today.isoformat()


def _query(start: str, end: str, fmt: str | None = None) -> str:
    path = f"/compliance/audit-pack/preview?start_date={start}&end_date={end}"
    if fmt is None:
        return path
    return f"/compliance/audit-pack/export?start_date={start}&end_date={end}&format={fmt}"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_zones_excursions_audit_pack_and_auditor_access(client, monkeypatch):
    demo = ensure_demo_tenant()
    suffix = uuid.uuid4().hex[:6].upper()
    sku = f"ZN-{suffix[:2]}-{suffix[2:4]}"
    with session_scope() as session:
        ensure_sku(session, demo.venue_id, category="wine", name=f"Zone Bottle {suffix}", barcode=sku, cost=1200, vintage="2020", par=0)
        session.commit()

    place = client.post("/inventory/locations", json={"name": f"Zone Cellar {suffix}", "kind": "cellar"})
    assert place.status_code == 200, place.text
    location_id = place.json()["location"]["id"]
    spot = client.post("/inventory/bins", json={"location_id": location_id, "code": f"Z{suffix[:4]}", "label": "Rack"})
    assert spot.status_code == 200, spot.text
    bin_id = spot.json()["bin"]["id"]
    received = client.post(
        "/inventory/movements",
        json={
            "sku": sku,
            "location_id": location_id,
            "bin_id": bin_id,
            "quantity": "4",
            "movement_type": "receive",
            "unit_cost_cents": 1200,
            "reason": "zone stock",
        },
    )
    assert received.status_code == 200, received.text

    created = client.post(
        "/inventory/storage-zones",
        json={
            "name": f"Probe {suffix}",
            "location_id": location_id,
            "target_temp_min_c": "12",
            "target_temp_max_c": "14",
            "target_humidity_min_pct": "60",
            "target_humidity_max_pct": "75",
            "notes": "Probe band",
        },
    )
    assert created.status_code == 200, created.text
    zone_id = created.json()["zone"]["id"]
    duplicate = client.post(
        "/inventory/storage-zones",
        json={
            "name": f"Probe {suffix}",
            "location_id": location_id,
            "target_temp_min_c": 12,
            "target_temp_max_c": 14,
            "target_humidity_min_pct": 60,
            "target_humidity_max_pct": 75,
        },
    )
    assert duplicate.status_code == 409

    calm = client.post(f"/inventory/storage-zones/{zone_id}/readings", json={"temp_c": 13, "humidity_pct": 68})
    assert calm.status_code == 200, calm.text
    assert calm.json()["excursion"] is None
    assert calm.json()["reading"]["in_range"] is True

    hot = client.post(
        f"/inventory/storage-zones/{zone_id}/readings",
        json={"temp_c": 20, "humidity_pct": 40, "notes": "Door left open"},
    )
    assert hot.status_code == 200, hot.text
    excursion = hot.json()["excursion"]
    assert excursion["metric"] == "temp_and_humidity"
    assert excursion["status"] == "open"
    affected = excursion["affected_skus"]
    assert any(row["sku"] == sku and row["bin_code"] == f"Z{suffix[:4]}" and row["on_hand"] == 4 for row in affected)

    listed = client.get("/inventory/storage-zones")
    assert listed.status_code == 200, listed.text
    zone = next(row for row in listed.json()["zones"] if row["id"] == zone_id)
    assert zone["status"] == "excursion"
    assert zone["excursion"]["id"] == excursion["id"]

    ack = client.post(f"/inventory/excursions/{excursion['id']}/acknowledge", json={"resolution_note": "Door closed"})
    assert ack.status_code == 200, ack.text
    assert ack.json()["excursion"]["status"] == "acknowledged"
    again = client.post(f"/inventory/excursions/{excursion['id']}/acknowledge", json={})
    assert again.status_code == 409

    from madira.models import AuditEvent

    with session_scope() as session:
        actions = set(session.scalars(sa.select(AuditEvent.action).where(AuditEvent.venue_id == demo.venue_id)).all())
    assert {"storage.reading_recorded", "storage.excursion_detected", "storage.excursion_acknowledged"} <= actions

    supplier = client.post(
        "/procurement/suppliers",
        json={"name": f"Pack House {suffix}", "default_case_size": 1, "order_minimum_cents": 0},
    )
    assert supplier.status_code == 200, supplier.text
    drafted = client.post(
        "/procurement/orders",
        json={
            "supplier_id": supplier.json()["supplier"]["id"],
            "lines": [{"sku": sku, "product_name": "Zone Bottle", "bottles": 2, "case_size": 1, "unit_cost_cents": 1200}],
        },
    )
    assert drafted.status_code == 200, drafted.text
    po_id = drafted.json()["id"]
    po_number = drafted.json()["po_number"]
    assert client.post(f"/procurement/orders/{po_id}/approve", json={"comment": "Pack it."}).status_code == 200
    sent = client.post(f"/procurement/orders/{po_id}/send")
    assert sent.status_code == 200, sent.text
    ctx = ensure_demo_tenant()
    received_po = mark_received(ctx.venue_id, uuid.UUID(po_id), ctx)
    assert received_po["status"] == "received"

    shrink = client.post(
        "/inventory/movements",
        json={
            "sku": sku,
            "location_id": location_id,
            "bin_id": bin_id,
            "quantity": "-1",
            "movement_type": "count_adjustment",
            "unit_cost_cents": 1200,
            "reason": "short count",
        },
    )
    assert shrink.status_code == 200, shrink.text
    poured = client.post(
        "/inventory/movements",
        json={
            "sku": sku,
            "location_id": location_id,
            "bin_id": bin_id,
            "quantity": "-1",
            "movement_type": "comp",
            "unit_cost_cents": 1200,
            "reason": "owner glass",
        },
    )
    assert poured.status_code == 200, poured.text

    start, end = _window()
    preview = client.get(_query(start, end))
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert any(row["purchase_order_id"] == po_id for row in body["missing_invoice_gaps"])
    assert body["retention"]["document_retention_years"] == 7
    assert body["chain"]["valid"] is True
    assert body["venue"]["name"] == "Maison Madira"

    gaps = client.get("/compliance/gaps")
    assert gaps.status_code == 200, gaps.text
    assert any(row["purchase_order_id"] == po_id for row in gaps.json()["missing_invoice_gaps"])
    assert gaps.json()["chain"]["valid"] is True

    invoice = upload_invoice(
        demo.venue_id,
        uuid.UUID(po_id),
        filename=f"pack-{suffix}.pdf",
        content_type="application/pdf",
        body=PDF,
        invoice_number=f"PACK-{suffix}",
        invoice_date=date.today().isoformat(),
        lines=[{"sku": sku, "quantity": 2, "unit_cost_cents": 1200, "description": "Zone Bottle"}],
        actor=ctx,
    )
    assert invoice["purchase_order_id"] == po_id
    cleared = client.get(_query(start, end))
    assert cleared.status_code == 200, cleared.text
    assert all(row["purchase_order_id"] != po_id for row in cleared.json()["missing_invoice_gaps"])
    assert any(row["invoice_number"] == f"PACK-{suffix}" for row in cleared.json()["invoice_register"])

    journal = client.get(_query(start, end, "journal_csv"))
    assert journal.status_code == 200, journal.text
    assert "text/csv" in journal.headers["content-type"]
    assert "journal_entries.csv" in journal.headers["content-disposition"]
    parsed = list(csv.DictReader(io.StringIO(journal.text)))
    assert parsed
    assert list(parsed[0]) == [
        "Date",
        "Reference",
        "Description",
        "Account",
        "Debit",
        "Credit",
        "Supplier",
        "Currency",
        "DocumentHash",
    ]
    accounts = {row["Account"] for row in parsed}
    assert {"Inventory Asset", "Accounts Payable", "Inventory Shrinkage", "Comps, Breakage & Waste"} <= accounts
    debit = sum(Decimal(row["Debit"] or "0") for row in parsed)
    credit = sum(Decimal(row["Credit"] or "0") for row in parsed)
    assert debit == credit
    assert any(row["Reference"] == f"PACK-{suffix}" for row in parsed)

    pdf = client.get(_query(start, end, "summary_pdf"))
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF-")
    assert b"Maison Madira" in pdf.content
    assert start.encode() in pdf.content
    assert end.encode() in pdf.content
    assert b"Retention:" in pdf.content
    assert b"7 years" in pdf.content

    bundle = client.get(_query(start, end, "zip"))
    assert bundle.status_code == 200, bundle.text
    assert "application/zip" in bundle.headers["content-type"]
    assert bundle.content[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        names = set(archive.namelist())
        assert names == {
            "audit_pack_summary.pdf",
            "journal_entries.csv",
            "purchases_by_supplier.csv",
            "invoice_register.csv",
            "inventory_valuation.csv",
            "variance_and_shrinkage.csv",
            "comp_breakage_waste.csv",
            "manifest.json",
        }
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["document_retention_years"] == 7
        for name, meta in manifest["files"].items():
            assert meta["sha256"] == hashlib.sha256(archive.read(name)).hexdigest()
        assert archive.read("audit_pack_summary.pdf").startswith(b"%PDF-")

    with session_scope() as session:
        chain = verify_audit_chain(session, demo.venue_id)
        from madira.models import AuditEvent

        exported = session.scalar(
            sa.select(AuditEvent).where(
                AuditEvent.venue_id == demo.venue_id,
                AuditEvent.action == "compliance.audit_pack_exported",
            )
        )
    assert chain["valid"] is True
    assert exported is not None

    _cookie(client, monkeypatch, AUDITOR)
    assert client.get(_query(start, end)).status_code == 200
    assert client.get(_query(start, end, "zip")).status_code == 200
    assert client.get("/compliance/gaps").status_code == 200
    assert client.get("/inventory/storage-zones").status_code == 200
    denied = client.post(f"/inventory/storage-zones/{zone_id}/readings", json={"temp_c": 13, "humidity_pct": 68})
    assert denied.status_code == 403

    _cookie(client, monkeypatch, STAFF)
    assert client.get(_query(start, end)).status_code == 403
    assert client.get("/compliance/gaps").status_code == 403
    assert client.get("/inventory/storage-zones").status_code == 403
    assert client.post(f"/inventory/storage-zones/{zone_id}/readings", json={"temp_c": 13, "humidity_pct": 68}).status_code == 403

    _cookie(client, monkeypatch, SOMMELIER)
    allowed = client.post(f"/inventory/storage-zones/{zone_id}/readings", json={"temp_c": 13.2, "humidity_pct": 70})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["excursion"] is None

    _cookie(client, monkeypatch, MANAGER)
    assert client.get(_query(start, end)).status_code == 200

    other = Venue(organization_id=demo.organization_id, name=f"Zone Other {suffix}", slug=f"zone-other-{suffix.lower()}")
    with session_scope() as session:
        session.add(other)
        session.commit()
        foreign_id = other.id
    _cookie(client, monkeypatch, OWNER, foreign_id)
    hidden = client.post(f"/inventory/storage-zones/{zone_id}/readings", json={"temp_c": 13, "humidity_pct": 68})
    assert hidden.status_code == 404
    assert client.get(f"/inventory/storage-zones/{zone_id}/readings").status_code == 404
    _owner(client)

    bad = client.get(f"/compliance/audit-pack/export?start_date={end}&end_date={start}&format=zip")
    assert bad.status_code == 422
    unknown = client.get(_query(start, end, "xlsx"))
    assert unknown.status_code == 422


def test_seeded_zones_stay_in_range_and_do_not_grow_on_a_second_seed():
    seed()
    demo = ensure_demo_tenant()
    with session_scope() as session:
        zones = session.scalars(sa.select(StorageZone).where(StorageZone.venue_id == demo.venue_id)).all()
        names = {row.name for row in zones}
        assert {"Main Cellar", "Bar & Cold Box"} <= names
        before = session.scalar(sa.select(sa.func.count()).select_from(ConditionReading))
    seed()
    with session_scope() as session:
        after = session.scalar(sa.select(sa.func.count()).select_from(ConditionReading))
        cellar = session.scalar(
            sa.select(StorageZone).where(StorageZone.venue_id == demo.venue_id, StorageZone.name == "Main Cellar")
        )
        bar = session.scalar(
            sa.select(StorageZone).where(StorageZone.venue_id == demo.venue_id, StorageZone.name == "Bar & Cold Box")
        )
        assert cellar is not None and cellar.location_id is not None
        assert bar is not None and bar.location_id is not None
        assert Decimal(cellar.target_temp_min_c) == Decimal("12.00")
        assert Decimal(bar.target_temp_max_c) == Decimal("10.00")
    assert after == before


def test_compliance_auditor_tools_are_read_only():
    names = [tool.__name__ for tool in COMPLIANCE_TOOLS]
    assert names == ["get_audit_pack_summary", "find_compliance_gaps", "get_storage_zones_status"]
    spec = next(row for row in SUBAGENT_SPECS if row["name"] == "compliance-auditor")
    assert [tool.__name__ for tool in spec["tools"]] == names
    assert "read-only" in spec["system_prompt"].lower()
    ctx = ensure_demo_tenant()
    token = bind(ctx)
    try:
        payload = json.loads(get_storage_zones_status())
    finally:
        reset(token)
    encoded = json.dumps(payload)
    assert "ZoneConditionCard" in encoded
    assert "Main Cellar" in encoded


def test_migration_0014_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0014_storage_zones.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0013_receiving_invoices"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert source.count('_enable_rls("') == 3
    assert "if not _is_postgres():" in source
    db = tmp_path / "storage.db"
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
    assert version == "0014_storage_zones"
    tables = set(sa.inspect(conn).get_table_names())
    assert {"storage_zones", "condition_readings", "condition_excursions"} <= tables
    zone_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(storage_zones)"))}
    assert {"venue_id", "location_id", "name", "target_temp_min_c", "target_temp_max_c", "target_humidity_min_pct", "target_humidity_max_pct", "notes", "created_at"} <= zone_cols
    reading_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(condition_readings)"))}
    assert {"venue_id", "zone_id", "temp_c", "humidity_pct", "source", "recorded_by_user_id", "recorded_at", "notes"} <= reading_cols
    excursion_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(condition_excursions)"))}
    assert {"venue_id", "zone_id", "reading_id", "metric", "measured_temp_c", "measured_humidity_pct", "affected_skus", "status", "acknowledged_by_user_id", "acknowledged_at", "resolution_note", "created_at"} <= excursion_cols
command.downgrade(cfg, "0013_receiving_invoices")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0013_receiving_invoices"
    tables = set(sa.inspect(conn).get_table_names())
    assert "storage_zones" not in tables
    assert "condition_readings" not in tables
    assert "condition_excursions" not in tables
command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0014_storage_zones"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
