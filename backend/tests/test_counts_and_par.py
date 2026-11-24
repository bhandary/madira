"""Phone counts, offline replay, variance approval, and par proposals."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from types import SimpleNamespace

import sqlalchemy as sa
from fastapi.testclient import TestClient

from madira.agents.tools import get_count_variance, propose_par_changes
from madira.auth import issue_session, utcnow
from madira.domain.compliance.service import verify_audit_chain
from madira.domain.inventory import counts, ledger, par
from madira.domain.inventory.ledger import Rejected, as_qty
from madira.domain.session import session_scope
from madira.main import app
from madira.models import AuditEvent, CountLine, InventoryItem, Membership, ParProposal, Sku, StockMovement, User
from madira.tenancy import AUDITOR, MANAGER, OWNER, STAFF, RequestContext, bind, ensure_demo_tenant, reset

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "counts-par-test-secret"


def _actor(email: str = "counter@example.com"):
    return SimpleNamespace(user_id=None, email=email)


def _formula(depletion: str, lead: int = 7, safety: int = 4) -> int:
    daily = Decimal(depletion) / Decimal(30)
    raw = daily * Decimal(lead + safety)
    return max(1, int(raw.to_integral_value(rounding=ROUND_CEILING)))


def _venue():
    org_id = uuid.uuid4()
    venue_id = uuid.uuid4()
    with session_scope() as session:
        session.execute(
            sa.text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": org_id.hex, "name": f"Counts {org_id.hex[:6]}", "slug": f"counts-{org_id.hex[:10]}"},
        )
        session.execute(
            sa.text(
                "INSERT INTO venues (id, organization_id, name, slug, currency) "
                "VALUES (:id, :org, :name, :slug, 'USD')"
            ),
            {
                "id": venue_id.hex,
                "org": org_id.hex,
                "name": "Count Cellar",
                "slug": f"counts-{venue_id.hex[:10]}",
            },
        )
        session.commit()
    return org_id, venue_id


def _sku(venue_id, barcode: str, *, par_level: int = 6, cost: int = 2500) -> str:
    from madira.domain.catalog.service import ensure_sku

    with session_scope() as session:
        stock = ensure_sku(
            session,
            venue_id,
            category="spirit",
            name=barcode,
            barcode=barcode,
            par=par_level,
            cost=cost,
        )
        session.commit()
        return stock.barcode


def _location(venue_id, name: str = "Main Cellar", kind: str = "cellar") -> uuid.UUID:
    with session_scope() as session:
        place = ledger.ensure_location(session, venue_id, name, kind)
        session.commit()
        return place.id


def _open(venue_id, location_id, sku: str, quantity: str, *, days_ago: int = 40):
    with session_scope() as session:
        ledger.post_movement(
            session,
            venue_id,
            sku=sku,
            location_id=location_id,
            quantity=Decimal(quantity),
            movement_type="opening_balance",
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        )
        session.commit()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_sync_is_idempotent_conflict_blocks_approval_until_resolved():
    _org, venue_id = _venue()
    actor = _actor()
    counted = _sku(venue_id, f"CNT-{uuid.uuid4().hex[:6].upper()}", par_level=6, cost=2500)
    steady = _sku(venue_id, f"STD-{uuid.uuid4().hex[:6].upper()}", par_level=4, cost=1000)
    place = _location(venue_id)
    _open(venue_id, place, counted, "10")
    _open(venue_id, place, steady, "5")
    started = counts.start_count_session(venue_id, place, actor, notes="night")
    assert started["status"] == "in_progress"
    session_id = started["id"]
    moment = datetime.now(timezone.utc) - timedelta(minutes=5)
    first = counts.sync_count_lines(
        venue_id,
        session_id,
        [
            {
                "client_mutation_id": "m1",
                "device_id": "phone-a",
                "sku": counted,
                "counted_quantity": "1.4",
                "counted_at": moment.isoformat(),
            }
        ],
        actor,
    )
    replay = counts.sync_count_lines(
        venue_id,
        session_id,
        [
            {
                "client_mutation_id": "m1",
                "device_id": "phone-a",
                "sku": counted,
                "counted_quantity": "9",
                "counted_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        actor,
    )
    assert replay["lines"][0]["id"] == first["lines"][0]["id"]
    assert replay["lines"][0]["counted_quantity"] == 1.4
    with session_scope() as session:
        stored = session.scalar(
            sa.select(sa.func.count()).select_from(CountLine).where(CountLine.session_id == uuid.UUID(session_id))
        )
        assert stored == 1
    counts.sync_count_lines(
        venue_id,
        session_id,
        [
            {
                "client_mutation_id": "m2",
                "device_id": "phone-b",
                "sku": counted,
                "counted_quantity": "2.0",
                "counted_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "client_mutation_id": "m3",
                "device_id": "phone-a",
                "sku": steady,
                "counted_quantity": "5",
                "counted_at": datetime.now(timezone.utc).isoformat(),
            },
        ],
        actor,
    )
    submitted = counts.submit_count_session(venue_id, session_id, actor)
    conflict = next(row for row in submitted["conflicts"] if row["sku"] == counted)
    assert conflict["resolved"] is False
    assert {reading["device_id"] for reading in conflict["readings"]} == {"phone-a", "phone-b"}
    assert {reading["counted_quantity"] for reading in conflict["readings"]} == {1.4, 2}
    try:
        counts.approve_count_session(venue_id, session_id, actor)
    except Rejected as exc:
        assert exc.status == 409
        assert "conflict" in exc.message.lower()
    else:
        raise AssertionError("approval should wait for the conflict")
    resolved = counts.resolve_count_conflict(venue_id, session_id, counted, Decimal("1.4"), actor, notes="phone-a")
    assert next(row for row in resolved["conflicts"] if row["sku"] == counted)["resolved"] is True
    approved = counts.approve_count_session(venue_id, session_id, actor)
    assert approved["session"]["status"] == "approved"
    posted = {row["sku"]: Decimal(str(row["quantity"])) for row in approved["movements"]}
    assert posted == {counted: Decimal("-8.60")}
    variance = next(row for row in approved["variance_lines"] if row["sku"] == counted)
    assert variance["expected_quantity"] == 10
    assert variance["counted_quantity"] == 1.4
    assert variance["variance"] == -8.6
    assert variance["variance_value_cents"] == -21500
    with session_scope() as session:
        rows = session.scalars(
            sa.select(StockMovement).where(
                StockMovement.venue_id == venue_id,
                StockMovement.source_type == "count_session",
                StockMovement.source_id == session_id,
            )
        ).all()
        assert [(row.movement_type, as_qty(row.quantity)) for row in rows] == [("count_adjustment", Decimal("-8.60"))]
        counted_id = session.scalar(sa.select(Sku.id).where(Sku.venue_id == venue_id, Sku.barcode == counted))
        steady_id = session.scalar(sa.select(Sku.id).where(Sku.venue_id == venue_id, Sku.barcode == steady))
        assert _on_hand(session, venue_id, counted_id) == Decimal("1.40")
        assert _on_hand(session, venue_id, steady_id) == Decimal("5.00")
        actions = set(
            session.scalars(sa.select(AuditEvent.action).where(AuditEvent.venue_id == venue_id)).all()
        )
        assert "count_session.started" in actions
        assert "count_session.approved" in actions
        chain = verify_audit_chain(session, venue_id)
        assert chain["valid"] is True
        assert chain["checked_count"] > 0
    try:
        counts.sync_count_lines(
            venue_id,
            session_id,
            [{"client_mutation_id": "late", "device_id": "phone-a", "sku": counted, "counted_quantity": "1"}],
            actor,
        )
    except Rejected as exc:
        assert exc.status == 409
    else:
        raise AssertionError("a closed session should reject sync")


def _on_hand(session, venue_id, sku_id) -> Decimal:
    return as_qty(
        session.scalar(
            sa.select(InventoryItem.on_hand).where(
                InventoryItem.venue_id == venue_id,
                InventoryItem.sku_id == sku_id,
            )
        )
    )


def test_bin_qr_resolves_during_sync():
    _org, venue_id = _venue()
    other_org, other_venue = _venue()
    actor = _actor()
    barcode = _sku(venue_id, f"BIN-{uuid.uuid4().hex[:6].upper()}")
    place = _location(venue_id)
    foreign = _location(other_venue, "Other Cellar")
    with session_scope() as session:
        spot = ledger.ensure_bin(session, venue_id, place, "A1", "Bay A1")
        other = ledger.ensure_bin(session, other_venue, foreign, "B9", "Other")
        session.commit()
        payload = spot.qr_payload
        other_payload = other.qr_payload
        spot_id = str(spot.id)
    started = counts.start_count_session(venue_id, place, actor)
    synced = counts.sync_count_lines(
        venue_id,
        started["id"],
        [
            {
                "client_mutation_id": "bin-1",
                "device_id": "scanner",
                "barcode": barcode,
                "bin_qr": payload,
                "counted_quantity": "1.4",
            }
        ],
        actor,
    )
    assert synced["lines"][0]["bin_id"] == spot_id
    assert synced["lines"][0]["bin_code"] == "A1"
    assert synced["lines"][0]["counted_quantity"] == 1.4
    try:
        counts.sync_count_lines(
            venue_id,
            started["id"],
            [
                {
                    "client_mutation_id": "bin-2",
                    "sku": barcode,
                    "bin_qr": other_payload,
                    "counted_quantity": "1",
                }
            ],
            actor,
        )
    except Exception as exc:
        assert getattr(exc, "message", "") 
        from madira.domain.errors import NotFound

        assert isinstance(exc, NotFound)
    else:
        raise AssertionError("a bin from another venue should be hidden")
    assert other_org is not None


def test_par_math_accepts_and_rejects_with_an_audit_event():
    _org, venue_id = _venue()
    actor = _actor("buyer@example.com")
    place = _location(venue_id)
    moving = _sku(venue_id, f"PAR-{uuid.uuid4().hex[:6].upper()}", par_level=12, cost=1800)
    small = _sku(venue_id, f"MIN-{uuid.uuid4().hex[:6].upper()}", par_level=6, cost=900)
    quiet = _sku(venue_id, f"QUI-{uuid.uuid4().hex[:6].upper()}", par_level=4, cost=500)
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        ledger.post_movement(
            session,
            venue_id,
            sku=moving,
            location_id=place,
            quantity=Decimal("30"),
            movement_type="opening_balance",
            created_at=now - timedelta(days=40),
        )
        ledger.post_movement(
            session,
            venue_id,
            sku=moving,
            location_id=place,
            quantity=Decimal("-18"),
            movement_type="sale",
            created_at=now - timedelta(days=2),
        )
        ledger.post_movement(
            session,
            venue_id,
            sku=small,
            location_id=place,
            quantity=Decimal("8"),
            movement_type="opening_balance",
            created_at=now - timedelta(days=40),
        )
        ledger.post_movement(
            session,
            venue_id,
            sku=small,
            location_id=place,
            quantity=Decimal("-1"),
            movement_type="sale",
            created_at=now - timedelta(days=1),
        )
        ledger.post_movement(
            session,
            venue_id,
            sku=quiet,
            location_id=place,
            quantity=Decimal("4"),
            movement_type="opening_balance",
            created_at=now - timedelta(days=40),
        )
        session.commit()
    assert _formula("18") == 7
    assert _formula("1") == 1
    first = par.propose_par_changes(venue_id)
    by_sku = {row["sku"]: row for row in first["proposals"]}
    assert set(by_sku) == {moving, small}
    assert by_sku[moving]["current_par"] == 12
    assert by_sku[moving]["proposed_par"] == 7
    assert by_sku[moving]["depletion_30d"] == 18
    assert by_sku[moving]["lead_time_days"] == 7
    assert by_sku[moving]["safety_days"] == 4
    assert "proposes par 7" in by_sku[moving]["rationale"]
    assert by_sku[small]["proposed_par"] == 1
    assert by_sku[small]["proposed_by"] == "cellar-manager"
    assert quiet not in by_sku
    second = par.propose_par_changes(venue_id)
    assert {row["sku"] for row in second["proposals"]} == {moving, small}
    with session_scope() as session:
        pending = session.scalars(
            sa.select(ParProposal).where(ParProposal.venue_id == venue_id, ParProposal.status == "pending")
        ).all()
        assert len(pending) == 2
        rejected = session.scalars(
            sa.select(ParProposal).where(ParProposal.venue_id == venue_id, ParProposal.status == "rejected")
        ).all()
        assert len(rejected) == 2
        assert all("Superseded" in row.rationale for row in rejected)
    assert "not pending" in _reject_message(venue_id, by_sku[moving]["id"], actor)
    fresh = next(row for row in second["proposals"] if row["sku"] == moving)
    accepted = par.decide_par_proposal(venue_id, fresh["id"], "accept", actor)
    assert accepted["status"] == "accepted"
    assert accepted["proposed_par"] == 7
    declined = par.decide_par_proposal(venue_id, next(row["id"] for row in second["proposals"] if row["sku"] == small), "reject", actor)
    assert declined["status"] == "rejected"
    with session_scope() as session:
        assert session.scalar(sa.select(Sku.par).where(Sku.barcode == moving)) == 7
        assert session.scalar(sa.select(Sku.par).where(Sku.barcode == small)) == 6
        assert session.scalar(sa.select(Sku.par).where(Sku.barcode == quiet)) == 4
        actions = set(session.scalars(sa.select(AuditEvent.action).where(AuditEvent.venue_id == venue_id)).all())
        assert "par.updated" in actions
        assert "par.rejected" in actions
        assert verify_audit_chain(session, venue_id)["valid"] is True
    from madira.domain.inventory.service import snapshot

    shown = next(row for row in snapshot(venue_id)["items"] if row["sku"] == moving)
    assert shown["par"] == 7


def _reject_message(venue_id, proposal_id, actor) -> str:
    try:
        par.decide_par_proposal(venue_id, proposal_id, "accept", actor)
    except Rejected as exc:
        assert exc.status == 409
        return exc.message
    raise AssertionError("a decided proposal should not be accepted again")


def test_cellar_manager_tools_return_count_surfaces():
    org_id, venue_id = _venue()
    actor = _actor()
    barcode = _sku(venue_id, f"TOOL-{uuid.uuid4().hex[:6].upper()}", par_level=3, cost=2800)
    place = _location(venue_id)
    _open(venue_id, place, barcode, "4")
    with session_scope() as session:
        ledger.post_movement(
            session,
            venue_id,
            sku=barcode,
            location_id=place,
            quantity=Decimal("-2"),
            movement_type="sale",
            created_at=datetime.now(timezone.utc) - timedelta(days=3),
        )
        session.commit()
    started = counts.start_count_session(venue_id, place, actor)
    counts.sync_count_lines(
        venue_id,
        started["id"],
        [{"client_mutation_id": "tool-1", "device_id": "web", "sku": barcode, "counted_quantity": "1.4"}],
        actor,
    )
    submitted = counts.submit_count_session(venue_id, started["id"], actor)
    ctx = RequestContext(
        user_id=uuid.uuid4(),
        email="cellar@example.com",
        name="Cellar",
        venue_id=venue_id,
        organization_id=org_id,
        role=OWNER,
    )
    token = bind(ctx)
    try:
        body = json.loads(get_count_variance(submitted["session"]["id"]))
        proposals = json.loads(propose_par_changes())
    finally:
        reset(token)
    blob = json.dumps(body["a2ui_operations"])
    assert "CountSheet" in blob
    assert "VarianceReport" in blob
    surfaces = [op.get("createSurface", {}).get("surfaceId") for op in body["a2ui_operations"] if "createSurface" in op]
    assert "count-sheet" in surfaces
    assert "variance-report" in surfaces
    assert any(row["sku"] == barcode for row in proposals["proposals"])
    assert proposals["proposals"][0]["proposed_by"] == "cellar-manager"


def _cookie(client, monkeypatch, role: str) -> None:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    demo = ensure_demo_tenant()
    sub = f"count-{role.lower()}-{uuid.uuid4().hex[:8]}"
    now = utcnow()
    with session_scope() as session:
        user = User(google_sub=sub, email=f"{sub}@example.com", name=role, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, venue_id=demo.venue_id, role=role))
        session.commit()
    client.cookies.set("madira_session", issue_session(sub))


def test_roles_and_cross_venue_counts(client, monkeypatch):
    _org, other = _venue()
    place = _location(other, "Foreign")
    hidden = counts.start_count_session(other, place, _actor())
    assert client.get(f"/inventory/counts/{hidden['id']}").status_code == 404
    missing = client.post(f"/inventory/par-proposals/{uuid.uuid4()}/accept")
    assert missing.status_code == 404

    _cookie(client, monkeypatch, AUDITOR)
    assert client.get("/inventory/counts").status_code == 200
    assert client.get("/inventory/par-proposals").status_code == 200
    denied = client.post("/inventory/counts", json={"location_id": str(uuid.uuid4())})
    assert denied.status_code == 403
    assert client.post("/inventory/par-proposals/generate", json={}).status_code == 403
    assert client.post(f"/inventory/counts/{uuid.uuid4()}/approve").status_code == 403

    _cookie(client, monkeypatch, STAFF)
    assert client.post("/inventory/counts", json={"location_id": str(uuid.uuid4())}).status_code == 403
    assert client.post(f"/inventory/counts/{uuid.uuid4()}/approve").status_code == 403
    assert client.post(f"/inventory/par-proposals/{uuid.uuid4()}/accept").status_code == 403
    assert client.post(f"/inventory/par-proposals/{uuid.uuid4()}/reject").status_code == 403

    _cookie(client, monkeypatch, MANAGER)
    demo = ensure_demo_tenant()
    with session_scope() as session:
        cellar = ledger.ensure_location(session, demo.venue_id, "Main Cellar", "cellar")
        session.commit()
        cellar_id = str(cellar.id)
    started = client.post("/inventory/counts", json={"location_id": cellar_id, "notes": "manager"})
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"
    assert client.get(f"/inventory/counts/{hidden['id']}").status_code == 404


def test_migration_0011_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0011_counts_and_par.py").read_text()
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert source.count('_enable_rls("') == 4
    db = tmp_path / "counts.db"
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
    assert version == "0011_counts_and_par"
    tables = set(sa.inspect(conn).get_table_names())
    assert {"count_sessions", "count_lines", "count_conflict_resolutions", "par_proposals"} <= tables
    line_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(count_lines)"))}
    assert {"sku_id", "counted_quantity", "expected_quantity", "device_id", "client_mutation_id", "bin_id"} <= line_cols
    par_cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(par_proposals)"))}
    assert {"current_par", "proposed_par", "depletion_30d", "lead_time_days", "safety_days", "proposed_by", "status"} <= par_cols
command.downgrade(cfg, "0010_stock_ledger")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0010_stock_ledger"
    tables = set(sa.inspect(conn).get_table_names())
    assert "count_sessions" not in tables
    assert "par_proposals" not in tables
    assert "stock_movements" in tables
command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0011_counts_and_par"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
