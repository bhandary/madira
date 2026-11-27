"""POS sync posts each sale once, keeps the watermark, and hides the token."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from madira.auth import SESSION_COOKIE, issue_session
from madira.db import SessionLocal, init_db
from madira.domain.inventory.ledger import movement_sum
from madira.domain.pos.adapter import CatalogVariation, PosError, PosLocation, SaleLine
from madira.domain.pos.service import connect_demo, run_sync, save_mapping, sync
from madira.main import app
from madira.models import (
    AuditEvent,
    Membership,
    PosConnection,
    PosCredential,
    PosItemMapping,
    PosSale,
    PosSyncRun,
    StockMovement,
    User,
    Venue,
)
from madira.pos.__main__ import main as pos_main
from madira.seed import seed
from madira.tenancy import AUDITOR, DEMO_USER_SUB, OWNER, RequestContext, bind, ensure_demo_tenant, reset

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "pos-sync-test-secret"
TOKEN = "sq0atp-sync-secret-token-7788"


class FixedRegister:
    def __init__(self, lines: list[SaleLine]) -> None:
        self.lines = lines

    def list_locations(self) -> list[PosLocation]:
        return [PosLocation("bar-1", "Main Bar")]

    def list_variations(self) -> list[CatalogVariation]:
        return [
            CatalogVariation("item-1", "var-muscadet", "Muscadet", "Bottle", "W-MUS-01"),
            CatalogVariation("item-2", "var-unknown", "Unlisted pour", "Glass", ""),
        ]

    def search_sales(self, location_id: str, start_at: str, end_at: str) -> list[SaleLine]:
        del location_id, start_at, end_at
        return list(self.lines)


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _bind(demo):
    return bind(
        RequestContext(
            user_id=demo.user_id,
            email="owner@maison-madira.demo",
            name="Owner",
            venue_id=demo.venue_id,
            organization_id=demo.organization_id,
            role=OWNER,
        )
    )


def _clear_pos(venue_id) -> None:
    session = SessionLocal()
    try:
        session.execute(delete(PosSale).where(PosSale.venue_id == venue_id))
        session.execute(delete(PosItemMapping).where(PosItemMapping.venue_id == venue_id))
        session.execute(delete(PosSyncRun).where(PosSyncRun.venue_id == venue_id))
        session.execute(delete(PosConnection).where(PosConnection.venue_id == venue_id))
        session.execute(delete(PosCredential).where(PosCredential.venue_id == venue_id))
        session.commit()
    finally:
        session.close()


def test_sync_maps_posts_once_and_keeps_unmapped_items():
    demo = _demo()
    token = _bind(demo)
    closed = datetime.now(timezone.utc) - timedelta(hours=2)
    later = closed + timedelta(minutes=30)
    lines = [
        SaleLine("order-1", "line-1", "item-1", "var-muscadet", "Muscadet", "2", closed.isoformat()),
        SaleLine("order-2", "line-2", "item-2", "var-unknown", "Unlisted pour", "1", later.isoformat()),
    ]
    driver = FixedRegister(lines)
    try:
        _clear_pos(demo.venue_id)
        connect_demo(demo.venue_id)
        save_mapping(
            demo.venue_id,
            variation_id="var-muscadet",
            item_id="item-1",
            sku="W-MUS-01",
            pour_ml=750,
            units_per_sale="1",
        )
        session = SessionLocal()
        try:
            sku_id = _sku_id(session, demo.venue_id)
            before = movement_sum(session, demo.venue_id, sku_id)
            first = run_sync(session, demo.venue_id, driver)
            session.commit()
            after = movement_sum(session, demo.venue_id, sku_id)
            assert first["posted"] == 1
            assert first["skipped"] == 0
            assert first["unmapped"][0]["variation_id"] == "var-unknown"
            assert after == before - 2
            sales = session.scalars(select(PosSale).where(PosSale.venue_id == demo.venue_id)).all()
            assert len(sales) == 1
            movement = session.get(StockMovement, sales[0].movement_id)
            assert movement is not None
            assert movement.movement_type == "sale"
            assert movement.reason == "pos_sale"
            assert movement.source_type == "pos_sale"
            connection = session.scalar(select(PosConnection).where(PosConnection.venue_id == demo.venue_id))
            assert connection is not None
            assert connection.watermark
            assert connection.last_synced_at is not None
            second = run_sync(session, demo.venue_id, driver)
            session.commit()
            assert second["posted"] == 0
            assert second["skipped"] == 1
            assert second["unmapped"][0]["name"] == "Unlisted pour"
            assert movement_sum(session, demo.venue_id, sku_id) == after
            assert session.scalar(
                select(func.count()).select_from(PosSale).where(PosSale.venue_id == demo.venue_id)
            ) == 1
            event = session.scalar(
                select(AuditEvent).where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "pos.synced")
            )
            assert event is not None
        finally:
            session.close()
    finally:
        reset(token)
        _clear_pos(demo.venue_id)


def _sku_id(session, venue_id):
    from madira.models import Sku

    return session.scalar(select(Sku.id).where(Sku.venue_id == venue_id, Sku.barcode == "W-MUS-01"))


def test_sync_failure_is_recorded_and_does_not_post(monkeypatch):
    demo = _demo()
    token = _bind(demo)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-pos")

    def ok(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"locations": [{"id": "LOC1", "name": "Bar", "status": "ACTIVE"}]})

    def bad(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"errors": [{"code": "SERVICE_UNAVAILABLE", "detail": TOKEN}]})

    try:
        _clear_pos(demo.venue_id)
        from madira.domain.pos.service import connect_square

        connect_square(demo.venue_id, TOKEN, "LOC1", client=httpx.Client(transport=httpx.MockTransport(ok)))
        session = SessionLocal()
        try:
            sku_id = _sku_id(session, demo.venue_id)
            before = movement_sum(session, demo.venue_id, sku_id)
        finally:
            session.close()
        with pytest.raises(PosError) as caught:
            sync(demo.venue_id, client=httpx.Client(transport=httpx.MockTransport(bad)))
        assert TOKEN not in caught.value.message
        session = SessionLocal()
        try:
            failed = session.scalar(
                select(PosSyncRun).where(PosSyncRun.venue_id == demo.venue_id, PosSyncRun.status == "failed")
            )
            assert failed is not None
            assert "503" in failed.error
            assert TOKEN not in failed.error
            assert movement_sum(session, demo.venue_id, sku_id) == before
            assert session.scalar(select(func.count()).select_from(PosSale).where(PosSale.venue_id == demo.venue_id)) == 0
        finally:
            session.close()
    finally:
        reset(token)
        _clear_pos(demo.venue_id)


def test_square_token_is_not_in_the_response_or_the_log(monkeypatch, caplog):
    demo = _demo()
    token = _bind(demo)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-pos")
    monkeypatch.setenv("MADIRA_SQUARE_ENV", "sandbox")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Square-Version"]
        return httpx.Response(
            200,
            json={"locations": [{"id": "LOC1", "name": "Bar", "status": "ACTIVE"}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        from madira.domain.pos.service import connect_square
        from madira.llm_runtime import resolve_runtime

        assert resolve_runtime().demo_mode is False
        with caplog.at_level(logging.DEBUG):
            try:
                connect_demo(demo.venue_id)
            except PosError as exc:
                assert exc.status == 422
                assert "demo" in exc.message.lower()
            else:
                raise AssertionError("live mode must not connect the demo register")
            try:
                connect_square(demo.venue_id, "", client=client)
            except PosError as exc:
                assert "access token" in exc.message
            else:
                raise AssertionError("a missing token must fail")
            body = connect_square(demo.venue_id, TOKEN, "LOC1", client=client)
        encoded = json.dumps(body)
        assert TOKEN not in encoded
        assert "ciphertext" not in encoded
        assert body["key_last4"] == TOKEN[-4:]
        assert body["masked"] == f"····{TOKEN[-4:]}"
        assert TOKEN not in caplog.text
        session = SessionLocal()
        try:
            stored = session.scalar(select(PosCredential).where(PosCredential.venue_id == demo.venue_id))
            assert stored is not None
            assert TOKEN not in stored.ciphertext
            assert stored.key_last4 == TOKEN[-4:]
        finally:
            session.close()
    finally:
        client.close()
        reset(token)
        _clear_pos(demo.venue_id)


def test_rbac_and_tenancy(monkeypatch):
    demo = _demo()
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    other_id = uuid.uuid4()
    session = SessionLocal()
    try:
        venue = session.get(Venue, demo.venue_id)
        other = Venue(
            id=other_id,
            organization_id=venue.organization_id,
            name="Other room",
            slug=f"other-{other_id.hex[:8]}",
            timezone="America/Los_Angeles",
            invite_delivery="draft_only",
        )
        session.add(other)
        session.flush()
        user = session.scalar(select(User).where(User.google_sub == "pos-auditor"))
        if user is None:
            user = User(
                google_sub="pos-auditor",
                email="pos-auditor@example.com",
                name="POS Auditor",
                picture="",
                created_at=datetime.now(timezone.utc),
                last_login_at=datetime.now(timezone.utc),
            )
            session.add(user)
            session.flush()
        member = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == demo.venue_id))
        if member is None:
            session.add(Membership(user_id=user.id, venue_id=demo.venue_id, role=AUDITOR))
        else:
            member.role = AUDITOR
        outsider = session.scalar(select(User).where(User.google_sub == "pos-outsider"))
        if outsider is None:
            outsider = User(
                google_sub="pos-outsider",
                email="pos-outsider@example.com",
                name="Outsider",
                picture="",
                created_at=datetime.now(timezone.utc),
                last_login_at=datetime.now(timezone.utc),
            )
            session.add(outsider)
            session.flush()
        if session.scalar(select(Membership).where(Membership.user_id == outsider.id, Membership.venue_id == other_id)) is None:
            session.add(Membership(user_id=outsider.id, venue_id=other_id, role=OWNER))
        session.commit()
    finally:
        session.close()

    token = _bind(demo)
    try:
        _clear_pos(demo.venue_id)
        connect_demo(demo.venue_id)
    finally:
        reset(token)

    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "ana")
        assert client.get("/pos/status").status_code == 403
        assert client.post("/pos/connect/demo").status_code == 403
        client.cookies.set("madira_demo_persona", "lea")
        assert client.get("/pos/status").status_code == 200
        assert client.post("/pos/sync").status_code == 403
        client.cookies.set("madira_demo_persona", "mia")
        assert client.get("/pos/gaps").status_code == 200
        client.cookies.set("madira_demo_persona", "owner")
        owner = client.get("/pos/status")
        assert owner.status_code == 200
        assert owner.json()["provider"] == "demo"
        assert TOKEN not in owner.text
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, issue_session("pos-auditor"))
        assert client.get("/pos/status").status_code == 200
        assert client.post("/pos/connect/demo").status_code == 403
        client.cookies.set(SESSION_COOKIE, issue_session("pos-outsider"))
        outsider_status = client.get("/pos/status")
        assert outsider_status.status_code == 200
        assert outsider_status.json()["connected"] is False
    _clear_pos(demo.venue_id)


def test_cli_syncs_an_active_register():
    demo = _demo()
    token = _bind(demo)
    try:
        _clear_pos(demo.venue_id)
        connect_demo(demo.venue_id)
        save_mapping(
            demo.venue_id,
            variation_id="demo-var-muscadet",
            item_id="demo-item-muscadet",
            sku="W-MUS-01",
            pour_ml=None,
            units_per_sale="1",
        )
    finally:
        reset(token)
    assert pos_main(["sync"]) == 0
    session = SessionLocal()
    try:
        sale = session.scalar(select(PosSale).where(PosSale.venue_id == demo.venue_id, PosSale.provider == "demo"))
        assert sale is not None
        assert sale.external_line_id == "demo-order-1:line"
    finally:
        session.close()
        _clear_pos(demo.venue_id)
    env = os.environ.copy()
    env["PYTHONPATH"] = "backend"
    env["MADIRA_DEMO_MODE"] = "true"
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "MADIRA_API_KEY", "DATABASE_URL"):
        env.pop(key, None)
    proc = subprocess.run(
        [sys.executable, "-m", "madira.pos", "sync"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "sq0atp" not in proc.stdout + proc.stderr


def test_migration_0024_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0024_pos.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0023_tasting_invites"' in source
    assert source.count('_enable_rls("') == 5
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "venue_isolation" in source
    assert "if not _is_postgres():" in source
    db = tmp_path / "pos.db"
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
    assert version == "0029_tablet_pin"
    tables = set(sa.inspect(conn).get_table_names())
    assert "pos_credentials" in tables
    assert "pos_connections" in tables
    assert "pos_item_mappings" in tables
    assert "pos_sales" in tables
    assert "pos_sync_runs" in tables

command.downgrade(cfg, "0023_tasting_invites")
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "pos_connections" not in tables
    assert "pos_credentials" not in tables
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0023_tasting_invites"

command.upgrade(cfg, "head")
with engine.connect() as conn:
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0029_tablet_pin"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
