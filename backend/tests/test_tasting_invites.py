"""Tasting invites stay drafts until an Owner or a Manager approves them."""

from __future__ import annotations

import os
import socket
import smtplib
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from langchain_core.messages import HumanMessage

from madira.agents.demo.model import DemoChatModel, classify_intent
from madira.agents.tools import propose_tasting_invite
from madira.api.settings import SettingsSaveBody
from madira.db import SessionLocal, init_db
from madira.domain.errors import DraftFailed
from madira.domain.sourcing.service import build_brief
from madira.domain.tastings.invite_delivery import DraftOnlyDelivery, set_invite_delivery
from madira.domain.tastings.invites import approve, desk, propose, reject, set_agenda_completer
from madira.domain.tastings.service import TastingError, add_sample, create_session
from madira.main import app
from madira.models import AuditEvent, Product, Supplier, Venue
from madira.seed import seed
from madira.tenancy import bind, ensure_demo_tenant, reset

ROOT = Path(__file__).resolve().parents[2]


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _session(demo, title, **extra):
    created = create_session(
        demo.venue_id,
        supplier_name="Kermit Lynch Wine Merchant",
        title=title,
        starts_at="2026-12-01T15:00",
        ends_at="2026-12-01T16:30",
        **extra,
    )
    raw = created["draft"]["id"]
    return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))


def _slots():
    return [
        {"starts_at": "2026-12-01T15:00", "ends_at": "2026-12-01T16:30", "source": "entered"},
        {"starts_at": "2026-12-02T11:00", "ends_at": "2026-12-02T12:30", "source": "entered"},
    ]


def _product(name):
    session = SessionLocal()
    try:
        product = session.scalar(select(Product).where(Product.name == name))
        assert product is not None
        return product.id
    finally:
        session.close()


def test_proposal_uses_gaps_or_the_want_list_and_strips_model_digits():
    demo = _demo()
    brief = build_brief(demo.venue_id)
    assert brief["brief"]["items"]
    quantity = brief["brief"]["items"][0]["quantity_hint"]
    style = brief["brief"]["items"][0]["style"]
    tasting_id = _session(demo, "Invite from the want list")
    product_id = _product("Muscadet Domaine de l'Ecu")
    add_sample(demo.venue_id, tasting_id, product_id=product_id)
    set_agenda_completer(lambda _prompt: '{"agenda":"Bring 99999 bottles of the open style."}')
    try:
        payload = propose(demo.venue_id, tasting_id, slots=_slots(), staff_user_ids=[str(demo.user_id)])
    finally:
        set_agenda_completer(None)
    invite = payload["invite"]
    assert invite["status"] == "proposed"
    assert invite["sent"] is False
    assert invite["email_body"] == ""
    assert invite["ics_ready"] is False
    assert invite["agenda_facts"]["source"] == "want_list"
    assert "99999" not in invite["agenda_note"]
    assert not any(char.isdigit() for char in invite["agenda_note"])
    matched = [row for row in invite["agenda_facts"]["gaps"] if row["style"] == style]
    assert matched
    assert matched[0]["quantity_hint"] == quantity
    assert any(row["name"] == "Muscadet Domaine de l'Ecu" for row in invite["agenda_facts"]["samples"])
    assert any(row["kind"] == "rep" and row["email"] == "claire.vasseur@kermitlynch.example" for row in invite["attendees"])
    assert any(row["kind"] == "staff" and row["user_id"] == str(demo.user_id) for row in invite["attendees"])
    suggestions = desk(demo.venue_id, tasting_id)["suggestions"]
    assert len(suggestions) == 3
    assert suggestions[0]["source"] == "service"


def test_delivery_runs_only_after_approval_and_the_ics_uses_the_chosen_slot(monkeypatch):
    demo = _demo()
    tasting_id = _session(demo, "Invite chosen slot")
    calls = {"n": 0}
    real = DraftOnlyDelivery.deliver

    def wrapped(self, package):
        calls["n"] += 1
        return real(self, package)

    monkeypatch.setattr(DraftOnlyDelivery, "deliver", wrapped)
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(smtplib, "SMTP", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("smtp")))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("http")))

    proposed = propose(demo.venue_id, tasting_id, slots=_slots(), staff_user_ids=[])
    assert calls["n"] == 0
    assert proposed["invite"]["email_subject"] == ""
    with TestClient(app) as client:
        early = client.get(f"/tastings/{tasting_id}/invite.ics")
        assert early.status_code == 409
    ready = approve(demo.venue_id, tasting_id, slot_index=1, comment="Thursday")
    assert calls["n"] == 1
    invite = ready["invite"]
    assert invite["status"] == "ready"
    assert invite["sent"] is False
    assert invite["driver"] == "draft_only"
    assert invite["chosen_starts_at"] == "2026-12-02T11:00"
    assert "Madira did not send it" in invite["email_body"]
    assert invite["email_subject"].startswith("Tasting invite:")
    assert invite["email_mailto"].startswith("mailto:claire.vasseur@kermitlynch.example")
    assert any(row["quantity_hint"] for row in invite["agenda_facts"]["gaps"]) or invite["agenda_facts"]["gaps"] == []
    again = approve(demo.venue_id, tasting_id, slot_index=0)
    assert calls["n"] == 1
    assert again["invite"]["chosen_starts_at"] == "2026-12-02T11:00"
    with TestClient(app) as client:
        downloaded = client.get(f"/tastings/{tasting_id}/invite.ics")
        assert downloaded.status_code == 200
        body = downloaded.text.replace("\r\n ", "").replace("\n ", "")
        assert "METHOD:REQUEST" in body
        assert "METHOD:PUBLISH" not in body
        assert "ATTENDEE" in body
        assert "claire.vasseur@kermitlynch.example" in body
        assert "DTSTART:20261202T110000Z" in body
        assert "DTSTART:20261201T150000Z" not in body
        session_ics = client.get(f"/tastings/{tasting_id}.ics")
        assert session_ics.status_code == 200
        assert "METHOD:PUBLISH" in session_ics.text
        assert "ATTENDEE" not in session_ics.text
    session = SessionLocal()
    try:
        actions = set(
            session.scalars(
                select(AuditEvent.action).where(AuditEvent.venue_id == demo.venue_id, AuditEvent.entity_type == "tasting_invite")
            ).all()
        )
    finally:
        session.close()
    assert "tasting_invite.proposed" in actions
    assert "tasting_invite.approved" in actions
    assert "tasting_invite.ready" in actions


def test_reject_does_not_deliver(monkeypatch):
    demo = _demo()
    tasting_id = _session(demo, "Invite rejected")
    propose(demo.venue_id, tasting_id, slots=_slots(), staff_user_ids=[])

    def blocked(self, package):
        raise AssertionError("delivery ran")

    monkeypatch.setattr(DraftOnlyDelivery, "deliver", blocked)
    payload = reject(demo.venue_id, tasting_id, comment="Not this week")
    assert payload["invite"]["status"] == "rejected"
    assert payload["invite"]["sent"] is False
    assert payload["invite"]["ics_ready"] is False
    session = SessionLocal()
    try:
        actions = set(
            session.scalars(
                select(AuditEvent.action).where(AuditEvent.entity_id == uuid.UUID(payload["invite"]["id"]))
            ).all()
        )
    finally:
        session.close()
    assert "tasting_invite.rejected" in actions
    assert "tasting_invite.ready" not in actions


def test_only_draft_only_is_allowed_and_settings_does_not_expose_it():
    demo = _demo()
    with pytest.raises(TastingError):
        set_invite_delivery(demo.venue_id, "google")
    assert set_invite_delivery(demo.venue_id, "draft_only") == "draft_only"
    assert "invite_delivery" not in SettingsSaveBody.model_fields
    page = (ROOT / "frontend/src/app/settings/page.tsx").read_text()
    assert "invite_delivery" not in page
    session = SessionLocal()
    try:
        venue = session.get(Venue, demo.venue_id)
        assert venue.invite_delivery == "draft_only"
    finally:
        session.close()


def test_live_agenda_fails_loudly(monkeypatch):
    demo = _demo()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-invite-test")
    from madira.llm_runtime import resolve_runtime

    assert resolve_runtime().demo_mode is False

    def boom(_prompt, *, kind):
        raise RuntimeError(f"{kind} down")

    def demo_agenda(_prompt):
        raise AssertionError("demo agenda")

    monkeypatch.setattr("madira.domain.sourcing.service.live_complete", boom)
    monkeypatch.setattr("madira.domain.tastings.invites.demo_agenda", demo_agenda)
    tasting_id = _session(demo, "Invite live failure")
    with pytest.raises(DraftFailed) as caught:
        propose(demo.venue_id, tasting_id, slots=_slots(), staff_user_ids=[])
    message = str(caught.value)
    assert "RuntimeError" in message
    assert "AssertionError" not in message


def test_roles_tenancy_and_tonight():
    demo = _demo()
    session = SessionLocal()
    try:
        other = Venue(
            organization_id=demo.organization_id,
            name="Other Invites",
            slug=f"other-invites-{uuid.uuid4().hex[:8]}",
        )
        session.add(other)
        session.flush()
        session.add(Supplier(venue_id=other.id, name="Other House Wines", kind="distributor"))
        session.commit()
        other_id = other.id
    finally:
        session.close()
    hidden = create_session(
        other_id,
        supplier_name="Other House Wines",
        title="Hidden invite tasting",
        starts_at="2026-12-03T15:00",
        ends_at="2026-12-03T16:00",
    )
    hidden_id = hidden["draft"]["id"]
    tasting_id = _session(demo, "Invite for the floor")
    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "ana")
        assert client.get(f"/tastings/{tasting_id}/invite").status_code == 403
        client.cookies.set("madira_demo_persona", "lea")
        proposed = client.post(
            f"/tastings/{tasting_id}/invite",
            json={"slots": _slots(), "staff_user_ids": []},
        )
        assert proposed.status_code == 200
        assert proposed.json()["invite"]["status"] == "proposed"
        assert client.post(f"/tastings/{tasting_id}/invite/approve", json={"slot_index": 1, "comment": ""}).status_code == 403
        hidden_from_sommelier = client.get("/tonight")
        assert hidden_from_sommelier.status_code == 200
        assert all(row["kind"] != "tasting_invite" for row in hidden_from_sommelier.json()["approvals"])
        client.cookies.set("madira_demo_persona", "mia")
        tonight = client.get("/tonight")
        assert tonight.status_code == 200
        assert any(row["title"] == "Tasting invite awaiting approval" and row["href"] == "/tastings" for row in tonight.json()["approvals"])
        approved = client.post(f"/tastings/{tasting_id}/invite/approve", json={"slot_index": 1, "comment": "Go"})
        assert approved.status_code == 200
        assert approved.json()["invite"]["status"] == "ready"
        assert approved.json()["invite"]["sent"] is False
        client.cookies.set("madira_demo_persona", "owner")
        foreign = client.get(f"/tastings/{hidden_id}/invite")
        assert foreign.status_code == 404
        client.cookies.set("madira_demo_persona", "lea")
        assert client.get("/tonight").status_code == 200
        assert all(row["kind"] != "tasting_invite" or row["status"] != "pending" for row in client.get("/tonight").json()["approvals"])


def test_tool_proposes_and_the_demo_model_routes_it():
    demo = _demo()
    tasting_id = _session(demo, "Tool invite tasting")
    assert classify_intent("Propose a tasting invite for the Loire") == "supplier"
    model = DemoChatModel(role="supplier-scheduler")
    routed = model.invoke([HumanMessage(content=f"Propose a tasting invite {tasting_id}")])
    assert routed.tool_calls[0]["name"] == "propose_tasting_invite"
    assert routed.tool_calls[0]["args"]["session_id"] == str(tasting_id)
    token = bind(demo)
    try:
        import json

        payload = json.loads(propose_tasting_invite(str(tasting_id)))
    finally:
        reset(token)
    assert payload["invite"]["status"] == "proposed"
    assert payload["invite"]["sent"] is False
    assert payload["invite"]["email_body"] == ""
    assert "ApprovalCard" in json.dumps(payload["a2ui_operations"])


def test_migration_0023_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0023_tasting_invites.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0022_sourcing"' in source
    assert source.count('_enable_rls("') == 3
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "venue_isolation" in source
    assert "if not _is_postgres():" in source
    db = tmp_path / "invites.db"
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
    assert version == "0023_tasting_invites"
    tables = set(sa.inspect(conn).get_table_names())
    assert "tasting_invites" in tables
    assert "tasting_invite_slots" in tables
    assert "tasting_invite_attendees" in tables
    columns = {col["name"] for col in sa.inspect(conn).get_columns("venues")}
    assert "invite_delivery" in columns

command.downgrade(cfg, "0022_sourcing")
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "tasting_invites" not in tables
    columns = {col["name"] for col in sa.inspect(conn).get_columns("venues")}
    assert "invite_delivery" not in columns
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0022_sourcing"

command.upgrade(cfg, "head")
with engine.connect() as conn:
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0023_tasting_invites"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
