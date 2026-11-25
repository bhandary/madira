"""List versions: numbered snapshots, Owner approval, the vault PDF, and the guest page."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from madira.agents.demo.model import DemoChatModel
from madira.agents.tools import submit_list_for_publish
from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.catalog.service import ensure_sku
from madira.domain.errors import NotFound
from madira.domain.lists import versions as list_versions
from madira.domain.lists.service import add_item, curate, remove_item, update_item
from madira.domain.lists.versions import ListVersionError
from madira.domain.session import session_scope
from madira.main import app
from madira.models import (
    AuditEvent,
    BeverageList,
    Document,
    ListEntry,
    ListItem,
    ListSection,
    ListVersion,
    Membership,
    PublicListSnapshot,
    User,
    Venue,
)
from madira.seed import seed
from madira.tenancy import MANAGER, OWNER, SOMMELIER, bind, ensure_demo_tenant, persona_context, reset

ROOT = Path(__file__).resolve().parents[2]
AUTH_SECRET = "list-version-test-secret"


def _ready():
    init_db()
    seed()
    return ensure_demo_tenant()


def _persona(slug: str):
    session = SessionLocal()
    try:
        ctx = persona_context(session, slug)
    finally:
        session.close()
    assert ctx is not None
    return ctx


def _member(venue_id, role: str) -> User:
    session = SessionLocal()
    try:
        token = uuid.uuid4().hex
        user = User(
            google_sub=f"list-version-{token}",
            email=f"list.version.{token}@example.com",
            name=f"List {role}",
            picture="",
            created_at=utcnow(),
            last_login_at=utcnow(),
        )
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=role, position=None))
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def _other_venue(organization_id) -> uuid.UUID:
    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "list-version-other"))
        if venue is None:
            venue = Venue(organization_id=organization_id, name="List Version Other", slug="list-version-other")
            session.add(venue)
            session.commit()
        return venue.id
    finally:
        session.close()


def _uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _keys(value, found: set[str] | None = None) -> set[str]:
    found = found or set()
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(str(key).lower())
            _keys(child, found)
    elif isinstance(value, list):
        for child in value:
            _keys(child, found)
    return found


def _word(text: str, word: str) -> bool:
    return re.search(rf"\b{word}\b", text, re.IGNORECASE) is not None


def test_snapshots_are_numbered_and_do_not_change():
    demo = _ready()
    created = curate(demo.venue_id, budget=12000, target_margin=3.2, name="Numbered house list")
    list_id = _uuid(created["list_id"])
    first = list_versions.snapshot_draft(demo.venue_id, list_id, demo)
    assert first["number"] == 1
    assert first["status"] == "draft"
    assert first["public_token"] is None
    assert first["entries"]
    assert len(first["diff"]["added"]) == len(first["entries"])
    assert first["diff"]["removed"] == []
    held = first["entries"][0]
    update_item(
        demo.venue_id,
        list_id,
        _uuid(created["items"][0]["id"]),
        {"bottle_price": int(held["bottle_price_cents"]) + 500},
    )
    session = SessionLocal()
    try:
        stored = session.get(ListEntry, uuid.UUID(held["id"]))
        assert stored is not None
        assert int(stored.bottle_price_cents) == int(held["bottle_price_cents"])
        stored.display_name = "Changed after the snapshot"
        with pytest.raises(ValueError, match="cannot change"):
            session.commit()
        session.rollback()
        stored = session.get(ListEntry, uuid.UUID(held["id"]))
        session.delete(stored)
        with pytest.raises(ValueError, match="cannot be deleted"):
            session.commit()
        session.rollback()
    finally:
        session.close()
    second = list_versions.snapshot_draft(demo.venue_id, list_id, demo)
    assert second["number"] == 2
    assert second["id"] != first["id"]
    kept = next(row for row in second["entries"] if row["sku_id"] == held["sku_id"])
    assert kept["bottle_price_cents"] == int(held["bottle_price_cents"]) + 500
    with session_scope() as session:
        count = session.scalar(select(ListVersion.number).where(ListVersion.id == uuid.UUID(first["id"])))
        assert count == 1


def test_diff_reports_added_removed_repriced_and_moved():
    demo = _ready()
    created = curate(demo.venue_id, budget=12000, target_margin=3.2, name="Diff house list")
    assert len(created["items"]) >= 3
    list_id = _uuid(created["list_id"])
    first = list_versions.submit_list(demo.venue_id, list_id, demo)
    published = list_versions.approve(demo.venue_id, _uuid(first["id"]), demo)
    assert published["status"] == "published"
    priced, moved, gone = created["items"][:3]
    update_item(demo.venue_id, list_id, _uuid(priced["id"]), {"bottle_price": int(priced["bottle_price"]) + 700})
    update_item(demo.venue_id, list_id, _uuid(moved["id"]), {"section": "By the glass", "position": 9})
    remove_item(demo.venue_id, list_id, _uuid(gone["id"]))
    with session_scope() as session:
        sku = ensure_sku(
            session,
            demo.venue_id,
            name="Diff Arrival",
            producer="House Press",
            category="wine",
            region="Sonoma",
            style="red",
            cost=2200,
        )
        session.commit()
        sku_id = sku.id
    add_item(demo.venue_id, list_id, sku_id, "By the glass")
    draft = list_versions.snapshot_draft(demo.venue_id, list_id, demo)
    diff = draft["diff"]
    assert str(sku_id) in {row["sku_id"] for row in diff["added"]}
    assert str(gone["sku_id"]) in {row["sku_id"] for row in diff["removed"]}
    assert str(priced["sku_id"]) in {row["sku_id"] for row in diff["repriced"]}
    assert str(moved["sku_id"]) in {row["sku_id"] for row in diff["moved"]}
    live = list_versions.diff_live(demo.venue_id, list_id)
    assert str(priced["sku_id"]) in {row["sku_id"] for row in live["repriced"]}
    with TestClient(app) as client:
        routed = client.get(f"/lists/versions/{draft['id']}/diff")
    assert routed.status_code == 200
    assert {row["sku_id"] for row in routed.json()["added"]} == {str(sku_id)}


def test_only_the_owner_can_approve_and_the_ledger_records_it(monkeypatch, tmp_path):
    monkeypatch.setenv("MADIRA_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    demo = _ready()
    lea = _persona("lea")
    mia = _persona("mia")
    created = curate(demo.venue_id, budget=12000, target_margin=3.2, name="Approval house list")
    list_id = _uuid(created["list_id"])
    with pytest.raises(ListVersionError) as blocked:
        list_versions.submit_list(demo.venue_id, list_id, mia)
    assert blocked.value.status == 403
    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "lea")
        drafted = client.post(f"/lists/{list_id}/versions")
        assert drafted.status_code == 200, drafted.text
        version_id = drafted.json()["id"]
        submitted = client.post(f"/lists/versions/{version_id}/submit")
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "pending_approval"
        assert submitted.json()["public_token"] is None
        client.cookies.set("madira_demo_persona", "mia")
        assert client.post(f"/lists/versions/{version_id}/approve").status_code == 403
        assert client.post(f"/lists/versions/{version_id}/submit").status_code == 403
        client.cookies.set("madira_demo_persona", "lea")
        assert client.post(f"/lists/versions/{version_id}/approve").status_code == 403
        client.cookies.set("madira_demo_persona", "owner")
        board = client.get("/tonight")
        assert board.status_code == 200
        assert any(row["title"].startswith("List publish awaiting") for row in board.json()["approvals"])
        approved = client.post(f"/lists/versions/{version_id}/approve", json={"comment": "Print it"})
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "published"
        assert body["public_path"].startswith("/l/")
        assert len(body["public_token"]) >= 40
        assert body["public_token"] != version_id
        pdf = client.get(f"/lists/versions/{version_id}/pdf")
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF-")
        pdf_text = pdf.content.decode("latin-1", errors="ignore")
        assert not _word(pdf_text, "margin")
        assert not _word(pdf_text, "cost")
        qr = client.get(f"/lists/versions/{version_id}/qr.png")
        assert qr.status_code == 200
        assert qr.content.startswith(b"\x89PNG")
        guest = client.get(f"/public/lists/{body['public_token']}")
        assert guest.status_code == 200
        guest_body = guest.json()
        keys = _keys(guest_body)
        assert "cost" not in keys
        assert "margin" not in keys
        assert "margin_pct" not in keys
        assert "beverage_cost_pct" not in keys
        rendered = json.dumps(guest_body)
        assert not _word(rendered, "margin")
        assert not _word(rendered, "cost")
        assert "Isolation" not in rendered
        draft_token = client.get(f"/public/lists/{version_id}")
        assert draft_token.status_code == 404
        assert client.get("/public/lists/short-token").status_code == 404
        revoked = client.post(f"/lists/versions/{version_id}/revoke-public")
        assert revoked.status_code == 200
        assert client.get(f"/public/lists/{body['public_token']}").status_code == 404
        assert client.get(f"/lists/versions/{version_id}/qr.png").status_code == 404
    session = SessionLocal()
    try:
        version = session.get(ListVersion, uuid.UUID(version_id))
        document = session.get(Document, version.document_id)
        assert document is not None
        assert document.doc_type == "other"
        assert document.storage_key.startswith(f"{demo.venue_id}/vault/")
        assert (tmp_path / document.storage_key).is_file()
        actions = {
            row.action: row
            for row in session.scalars(
                select(AuditEvent).where(AuditEvent.venue_id == demo.venue_id, AuditEvent.entity_id == version.id)
            )
        }
        for action in ("list.submitted", "list.approved", "list.published", "list.public_revoked"):
            assert action in actions
            assert actions[action].before_json is not None
            assert actions[action].after_json is not None
        assert actions["list.submitted"].before_json["status"] == "draft"
        assert actions["list.submitted"].after_json["status"] == "pending_approval"
        assert actions["list.approved"].after_json["decision"] == "approved"
        assert actions["list.published"].after_json["public_token"] == body["public_token"]
        assert actions["list.published"].actor_email == demo.email
        assert actions["list.submitted"].actor_email == lea.email
    finally:
        session.close()


def test_reject_does_not_publish():
    demo = _ready()
    created = curate(demo.venue_id, budget=12000, target_margin=3.2, name="Rejected house list")
    list_id = _uuid(created["list_id"])
    pending = list_versions.submit_list(demo.venue_id, list_id, demo)
    rejected = list_versions.reject(demo.venue_id, _uuid(pending["id"]), demo, comment="Hold the print")
    assert rejected["status"] == "rejected"
    assert rejected["public_token"] is None
    with pytest.raises(NotFound):
        list_versions.public_list(str(uuid.uuid4()))
    session = SessionLocal()
    try:
        version = session.get(ListVersion, _uuid(pending["id"]))
        assert version.public_token is None
        assert version.document_id is None
        snapshot = session.scalar(select(PublicListSnapshot).where(PublicListSnapshot.token == str(version.id)))
        assert snapshot is None
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.entity_id == version.id, AuditEvent.action == "list.rejected")
        )
        assert event is not None
        assert event.before_json["status"] == "pending_approval"
        assert event.after_json["status"] == "rejected"
        assert event.after_json["comment"] == "Hold the print"
    finally:
        session.close()


def test_tokens_differ_and_another_venue_cannot_read_the_version(monkeypatch):
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    demo = _ready()
    first_list = curate(demo.venue_id, budget=12000, target_margin=3.2, name="Token one")
    second_list = curate(demo.venue_id, budget=12000, target_margin=3.2, name="Token two")
    first = list_versions.approve(
        demo.venue_id,
        _uuid(list_versions.submit_list(demo.venue_id, _uuid(first_list["list_id"]), demo)["id"]),
        demo,
    )
    second = list_versions.approve(
        demo.venue_id,
        _uuid(list_versions.submit_list(demo.venue_id, _uuid(second_list["list_id"]), demo)["id"]),
        demo,
    )
    assert first["public_token"] != second["public_token"]
    assert len(first["public_token"]) >= 40
    assert len(second["public_token"]) >= 40
    other_id = _other_venue(demo.organization_id)
    sommelier = _member(other_id, SOMMELIER)
    manager = _member(other_id, MANAGER)
    with session_scope() as session:
        sku = ensure_sku(
            session,
            other_id,
            name="Isolation Nebbiolo",
            producer="Other Ridge",
            category="wine",
            region="Piedmont",
            style="red",
            cost=2400,
        )
        beverage = BeverageList(
            venue_id=other_id,
            name="Other floor list",
            budget=100000,
            currency="USD",
            target_margin=3,
        )
        session.add(beverage)
        session.flush()
        section = ListSection(venue_id=other_id, list_id=beverage.id, name="Red", position=1)
        session.add(section)
        session.flush()
        session.add(
            ListItem(
                venue_id=other_id,
                list_id=beverage.id,
                sku_id=sku.id,
                section="Red",
                section_id=section.id,
                position=1,
                cost=2400,
                pour_price=1600,
                bottle_price=7800,
                currency="USD",
                margin_pct=0,
            )
        )
        session.commit()
        foreign_list = beverage.id
    foreign_actor = _context_for(_member(other_id, OWNER))
    pending = list_versions.submit_list(other_id, foreign_list, foreign_actor)
    published = list_versions.approve(other_id, _uuid(pending["id"]), foreign_actor)
    assert "Isolation Nebbiolo" in json.dumps(list_versions.public_list(published["public_token"]))
    with TestClient(app) as client:
        hidden = client.get(f"/lists/versions/{published['id']}")
        assert hidden.status_code == 404
        hidden_list = client.get(f"/lists/{foreign_list}/versions")
        assert hidden_list.status_code == 404
        guest = client.get(f"/public/lists/{published['public_token']}")
        assert guest.status_code == 200
        assert "Isolation Nebbiolo" in guest.text
        demo_guest = client.get(f"/public/lists/{first['public_token']}")
        assert "Isolation Nebbiolo" not in demo_guest.text
        client.cookies.set(SESSION_COOKIE, issue_session(sommelier.google_sub))
        assert client.post(f"/lists/versions/{published['id']}/approve").status_code == 403
        client.cookies.set(SESSION_COOKIE, issue_session(manager.google_sub))
        assert client.post(f"/lists/versions/{pending['id']}/approve").status_code == 403
        assert client.post(f"/lists/{foreign_list}/versions").status_code == 403


def _context_for(user: User):
    session = SessionLocal()
    try:
        membership = session.scalar(select(Membership).where(Membership.user_id == user.id))
        venue = session.get(Venue, membership.venue_id)
        from madira.tenancy import RequestContext

        return RequestContext(
            user_id=user.id,
            email=user.email,
            name=user.name,
            venue_id=venue.id,
            organization_id=venue.organization_id,
            role=membership.role,
        )
    finally:
        session.close()


def test_submit_tool_opens_an_approval_and_does_not_publish():
    demo = _ready()
    created = curate(demo.venue_id, budget=12000, target_margin=3.2, name="Tool house list")
    token = bind(demo)
    try:
        raw = submit_list_for_publish(str(created["list_id"]))
    finally:
        reset(token)
    body = json.loads(raw)
    assert "error" not in body
    encoded = json.dumps(body["a2ui_operations"])
    assert "ApprovalCard" in encoded
    assert "listVersion" in encoded
    version = body["version"]
    assert version["status"] == "pending_approval"
    assert version["public_token"] is None
    session = SessionLocal()
    try:
        stored = session.get(ListVersion, _uuid(version["id"]))
        assert stored.status == "pending_approval"
        assert stored.public_token is None
        assert session.get(PublicListSnapshot, str(stored.id)) is None
    finally:
        session.close()
    again = bind(demo)
    try:
        repeat = json.loads(submit_list_for_publish(str(created["list_id"])))
    finally:
        reset(again)
    assert repeat["version"]["id"] == version["id"]


def test_demo_model_routes_submit_and_diff_before_curate():
    model = DemoChatModel(role="list-curator")
    submitted = model.invoke([HumanMessage(content="Submit this list for publish")])
    assert submitted.tool_calls[0]["name"] == "submit_list_for_publish"
    diffed = model.invoke([HumanMessage(content="Diff the list against the published list")])
    assert diffed.tool_calls[0]["name"] == "diff_list"
    curated = model.invoke([HumanMessage(content="Curate a balanced beverage list. Budget $12000.")])
    assert curated.tool_calls[0]["name"] == "curate_beverage_list"


def test_migration_0019_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0019_list_versions.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0018_team_roleplay_certificates"' in source
    assert source.count('_enable_rls("') == 2
    assert "public_list_snapshots" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "if not _is_postgres():" in source
    db = tmp_path / "list-versions.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "0018_team_roleplay_certificates")
engine = sa.create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "list_versions" not in tables
    assert "list_entries" not in tables
    assert "public_list_snapshots" not in tables

command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0022_sourcing"
    tables = set(sa.inspect(conn).get_table_names())
    assert {"list_versions", "list_entries", "public_list_snapshots"} <= tables
    versions = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(list_versions)"))}
    assert {
        "venue_id",
        "list_id",
        "number",
        "status",
        "approval_id",
        "submitted_by_user_id",
        "published_by_user_id",
        "published_at",
        "document_id",
        "public_token",
        "public_revoked_at",
        "created_at",
    } <= versions
    entries = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(list_entries)"))}
    assert {
        "venue_id",
        "version_id",
        "section_name",
        "position",
        "sku_id",
        "bottle_price_cents",
        "glass_price_cents",
        "currency",
        "display_name",
        "display_detail",
    } <= entries
    public = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(public_list_snapshots)"))}
    assert "venue_id" not in public
    assert {"token", "venue_name", "rendered", "published_at", "revoked_at"} <= public

command.downgrade(cfg, "0018_team_roleplay_certificates")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0018_team_roleplay_certificates"
    tables = set(sa.inspect(conn).get_table_names())
    assert "list_versions" not in tables
    assert "list_entries" not in tables
    assert "public_list_snapshots" not in tables

command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0022_sourcing"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
