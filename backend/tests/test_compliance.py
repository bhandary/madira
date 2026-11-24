"""Hash-chained audit ledger, document vault, retention, and role checks."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from madira.auth import issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.compliance.service import (
    DEMO_LICENSE_FILENAME,
    GENESIS,
    Rejected,
    event_digest,
    get_retention_policy,
    list_audit_events,
    record_audit_event,
    update_retention_policy,
    verify_audit_chain,
)
from madira.domain.errors import NotFound
from madira.main import app
from madira.models import AuditEvent, BeverageList, Document, InventoryItem, Membership, Menu, Organization, User, Venue
from madira.seed import seed
from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, bind, ensure_demo_tenant, reset

AUTH_SECRET = "compliance-test-secret"


@pytest.fixture(autouse=True)
def restore_demo_retention():
    yield
    demo = ensure_demo_tenant()
    token = bind(demo)
    session = SessionLocal()
    try:
        if get_retention_policy(session, demo.organization_id) != 7:
            update_retention_policy(session, demo.organization_id, 7, venue_id=demo.venue_id)
            session.commit()
    finally:
        session.close()
        reset(token)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _session_cookie(monkeypatch, google_sub: str) -> str:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    return issue_session(google_sub)


def _as(client: TestClient, monkeypatch, google_sub: str) -> None:
    client.cookies.set("madira_session", _session_cookie(monkeypatch, google_sub))


def _user(session, google_sub: str, email: str, venue_id, role: str) -> User:
    user = session.scalar(select(User).where(User.google_sub == google_sub))
    now = utcnow()
    if user is None:
        user = User(google_sub=google_sub, email=email, name=email, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
    else:
        user.email = email
    membership = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id))
    if membership is None:
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=role))
    else:
        membership.role = role
    session.commit()
    return user


def _lab(session, organization_id) -> uuid.UUID:
    venue = session.scalar(select(Venue).where(Venue.slug == "audit-lab"))
    if venue is None:
        venue = Venue(organization_id=organization_id, name="Audit Lab", slug="audit-lab")
        session.add(venue)
        session.flush()
    session.execute(delete(AuditEvent).where(AuditEvent.venue_id == venue.id))
    session.commit()
    return venue.id


def _append(session, org_id, venue_id, action: str, after: dict) -> AuditEvent:
    return record_audit_event(
        session,
        org_id=org_id,
        venue_id=venue_id,
        action=action,
        entity_type="organization",
        entity_id=org_id,
        after=after,
        actor_email="lab@example.com",
    )


def test_demo_seed_adds_a_valid_chain_without_changing_catalog_counts():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        def counts():
            stock = session.scalar(
                select(func.count()).select_from(InventoryItem).where(InventoryItem.venue_id == demo.venue_id)
            )
            menus = session.scalar(select(func.count()).select_from(Menu).where(Menu.venue_id == demo.venue_id))
            lists = session.scalar(
                select(func.count()).select_from(BeverageList).where(BeverageList.venue_id == demo.venue_id)
            )
            licenses = session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.venue_id == demo.venue_id, Document.filename == DEMO_LICENSE_FILENAME)
            )
            return stock, menus, lists, licenses

        before = counts()
        session.close()
        seed()
        session = SessionLocal()
        after = counts()
        assert after[0] == before[0]
        assert after[1] == before[1]
        assert after[2] == before[2]
        assert after[3] == 1
        chain = verify_audit_chain(session, demo.venue_id)
        assert chain["valid"] is True
        assert chain["checked_count"] >= 2
        assert chain["head_hash"]
        assert chain["broken_event_id"] is None
        first = session.scalar(
            select(AuditEvent).where(AuditEvent.venue_id == demo.venue_id).order_by(AuditEvent.seq.asc()).limit(1)
        )
        assert first.seq == 1
        assert first.prev_hash == GENESIS
        assert first.event_hash == event_digest(first)
    finally:
        session.close()


def test_chain_links_hashes_and_catches_tampering():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        venue_id = _lab(session, demo.organization_id)
        first = _append(session, demo.organization_id, venue_id, "lab.open", {"n": 1})
        second = _append(session, demo.organization_id, venue_id, "lab.next", {"n": 2})
        third = _append(session, demo.organization_id, venue_id, "lab.last", {"n": 3})
        session.commit()
        session.expire_all()
        chain = verify_audit_chain(session, venue_id)
        assert chain == {
            "valid": True,
            "checked_count": 3,
            "head_hash": third.event_hash,
            "broken_event_id": None,
            "reason": None,
        }
        assert first.seq == 1 and first.prev_hash == GENESIS
        assert second.seq == 2 and second.prev_hash == first.event_hash
        assert third.prev_hash == second.event_hash

        second.after_json = {"n": 99}
        session.commit()
        session.expire_all()
        broken = verify_audit_chain(session, venue_id)
        assert broken["valid"] is False
        assert broken["broken_event_id"] == str(second.id)
        assert broken["reason"] == "hash mismatch"
        assert broken["head_hash"] is None
        assert broken["checked_count"] == 2
    finally:
        session.close()


def test_chain_catches_a_gap_and_a_relinked_prev_hash():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        venue_id = _lab(session, demo.organization_id)
        _append(session, demo.organization_id, venue_id, "lab.open", {"n": 1})
        middle = _append(session, demo.organization_id, venue_id, "lab.next", {"n": 2})
        last = _append(session, demo.organization_id, venue_id, "lab.last", {"n": 3})
        session.delete(middle)
        session.commit()
        gap = verify_audit_chain(session, venue_id)
        assert gap["valid"] is False
        assert gap["reason"] == "sequence gap"
        assert gap["broken_event_id"] == str(last.id)

        session.execute(delete(AuditEvent).where(AuditEvent.venue_id == venue_id))
        session.commit()
        _append(session, demo.organization_id, venue_id, "lab.open", {"n": 1})
        moved = _append(session, demo.organization_id, venue_id, "lab.next", {"n": 2})
        moved.prev_hash = "0" * 64
        session.commit()
        relinked = verify_audit_chain(session, venue_id)
        assert relinked["valid"] is False
        assert relinked["broken_event_id"] == str(moved.id)
        assert relinked["reason"] == "prev_hash does not match the previous event"

        session.execute(delete(AuditEvent).where(AuditEvent.venue_id == venue_id))
        session.commit()
        opening = _append(session, demo.organization_id, venue_id, "lab.open", {"n": 1})
        session.delete(opening)
        _append(session, demo.organization_id, venue_id, "lab.next", {"n": 2})
        session.commit()
        # The surviving row was inserted as seq 2 before the delete, so the chain no longer starts at 1.
        started = verify_audit_chain(session, venue_id)
        assert started["valid"] is False
        assert started["reason"] == "sequence does not start at 1"
    finally:
        session.close()


def test_filters_limit_the_ledger_to_one_venue():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        venue_id = _lab(session, demo.organization_id)
        _append(session, demo.organization_id, venue_id, "lab.open", {"n": 1})
        _append(session, demo.organization_id, venue_id, "lab.next", {"n": 2})
        session.commit()
        listed = list_audit_events(session, venue_id, action="lab.next", limit=10)
        assert [row["action"] for row in listed] == ["lab.next"]
        assert list_audit_events(session, venue_id, limit=1)[0]["seq"] == 2
        future = datetime.now(timezone.utc) + timedelta(days=1)
        assert list_audit_events(session, venue_id, since=future) == []
        demo_actions = {row["action"] for row in list_audit_events(session, demo.venue_id, limit=500)}
        assert "lab.open" not in demo_actions
    finally:
        session.close()


def test_new_organization_defaults_retention_to_seven_years():
    init_db()
    session = SessionLocal()
    try:
        org = Organization(name="Retention Defaults", slug=f"retention-{uuid.uuid4().hex[:8]}")
        session.add(org)
        session.flush()
        venue = Venue(organization_id=org.id, name="Retention Cellar", slug=f"cellar-{uuid.uuid4().hex[:8]}")
        session.add(venue)
        session.commit()
        assert org.document_retention_years == 7
        assert get_retention_policy(session, org.id) == 7
        with pytest.raises(Rejected):
            update_retention_policy(session, org.id, 0, venue_id=venue.id)
        with pytest.raises(Rejected):
            update_retention_policy(session, org.id, 26, venue_id=venue.id)
        with pytest.raises(Rejected):
            update_retention_policy(session, org.id, True, venue_id=venue.id)  # type: ignore[arg-type]
        assert update_retention_policy(session, org.id, 25, venue_id=venue.id) == 25
        session.commit()
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.venue_id == venue.id, AuditEvent.action == "retention.update")
        )
        assert event.before_json == {"document_retention_years": 7}
        assert event.after_json == {"document_retention_years": 25}
        assert verify_audit_chain(session, venue.id)["valid"] is True
    finally:
        session.close()


def test_vault_upload_download_and_content_rules(client: TestClient, monkeypatch, tmp_path):
    monkeypatch.setenv("MADIRA_STORAGE_DIR", str(tmp_path))
    note = b"Received 6 cases of Muscadet.\n"
    uploaded = client.post(
        "/compliance/documents",
        files={"file": ("cellar-delivery.txt", note, "text/plain")},
        data={"doc_type": "delivery_note"},
    )
    assert uploaded.status_code == 200, uploaded.text
    document = uploaded.json()["document"]
    assert document["sha256"] == hashlib.sha256(note).hexdigest()
    assert document["size_bytes"] == len(note)
    assert document["doc_type"] == "delivery_note"
    downloaded = client.get(f"/compliance/documents/{document['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == note
    assert "cellar-delivery.txt" in downloaded.headers["content-disposition"]

    listed = client.get("/compliance/documents")
    assert listed.status_code == 200
    assert document["id"] in {row["id"] for row in listed.json()["documents"]}
    assert DEMO_LICENSE_FILENAME in listed.text

    rejected = client.post(
        "/compliance/documents",
        files={"file": ("picture.gif", b"GIF89a", "image/gif")},
        data={"doc_type": "other"},
    )
    assert rejected.status_code == 415

    empty = client.post(
        "/compliance/documents",
        files={"file": ("empty.txt", b"", "text/plain")},
        data={"doc_type": "other"},
    )
    assert empty.status_code == 400

    binary_text = client.post(
        "/compliance/documents",
        files={"file": ("notes.txt", b"ok\x00no", "text/plain")},
        data={"doc_type": "other"},
    )
    assert binary_text.status_code == 415

    bad_type = client.post(
        "/compliance/documents",
        files={"file": ("notes.txt", b"ok", "text/plain")},
        data={"doc_type": "passport"},
    )
    assert bad_type.status_code == 422

    bad_link = client.post(
        "/compliance/documents",
        files={"file": ("notes.txt", b"ok", "text/plain")},
        data={"doc_type": "other", "linked_entity_id": "not-a-uuid"},
    )
    assert bad_link.status_code == 400

    guessed = client.post(
        "/compliance/documents",
        files={"file": ("sheet.csv", b"sku,qty\nW-1,1\n", "application/octet-stream")},
        data={"doc_type": "other"},
    )
    assert guessed.status_code == 200
    assert guessed.json()["document"]["content_type"] == "text/csv"

    monkeypatch.setenv("MADIRA_UPLOAD_MAX_BYTES", "16")
    oversized = client.post(
        "/compliance/documents",
        files={"file": ("big.txt", b"x" * 32, "text/plain")},
        data={"doc_type": "other"},
    )
    assert oversized.status_code == 413


def test_accepted_vault_types(client: TestClient, monkeypatch, tmp_path):
    monkeypatch.setenv("MADIRA_STORAGE_DIR", str(tmp_path))
    samples = (
        ("a.pdf", b"%PDF-1.4\n", "application/pdf", "invoice"),
        ("a.png", b"\x89PNG\r\n", "image/png", "other"),
        ("a.jpg", b"\xff\xd8\xff", "image/jpeg", "other"),
        ("a.webp", b"RIFF", "image/webp", "other"),
        ("a.csv", b"sku,qty\n", "text/csv", "other"),
    )
    for name, body, media, doc_type in samples:
        uploaded = client.post(
            "/compliance/documents",
            files={"file": (name, body, media)},
            data={"doc_type": doc_type},
        )
        assert uploaded.status_code == 200, (name, uploaded.text)
        assert uploaded.json()["document"]["content_type"] == media


def test_stock_adjustment_is_written_to_the_ledger(client: TestClient):
    current = client.get("/inventory")
    assert current.status_code == 200
    item = next(row for row in current.json()["items"] if row["sku"] == "W-MUS-01")
    target = 2 if item["on_hand"] == 1 else 1
    patched = client.patch("/inventory/W-MUS-01", json={"on_hand": target})
    assert patched.status_code == 200
    events = client.get("/compliance/audit-events", params={"action": "inventory.adjust", "entity_type": "inventory_item"})
    assert events.status_code == 200
    body = events.json()
    assert "AuditTable" in str(body["a2ui_operations"])
    match = next(row for row in body["events"] if row["after_json"]["on_hand"] == target and row["after_json"]["sku"] == "W-MUS-01")
    assert match["before_json"]["on_hand"] == item["on_hand"]
    assert "on_hand" in match["summary"]
    chain = client.get("/compliance/audit-events/verify")
    assert chain.status_code == 200
    assert chain.json()["valid"] is True


def test_retention_is_owner_only_and_defaults_to_seven(client: TestClient, monkeypatch):
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        roles = {
            "compliance-owner": (OWNER, "owner-compliance@example.com"),
            "compliance-sommelier": (SOMMELIER, "sommelier-compliance@example.com"),
            "compliance-manager": (MANAGER, "manager-compliance@example.com"),
            "compliance-staff": (STAFF, "staff-compliance@example.com"),
            "compliance-auditor": (AUDITOR, "auditor-compliance@example.com"),
        }
        for sub, (role, email) in roles.items():
            _user(session, sub, email, demo.venue_id, role)
    finally:
        session.close()

    client.cookies.clear()
    current = client.get("/compliance/retention")
    assert current.status_code == 200
    assert current.json() == {"document_retention_years": 7, "can_edit": True}

    _as(client, monkeypatch, "compliance-sommelier")
    assert client.patch("/compliance/retention", json={"document_retention_years": 8}).status_code == 403
    assert client.get("/compliance/retention").json()["document_retention_years"] == 7

    _as(client, monkeypatch, "compliance-manager")
    assert client.get("/compliance/audit-events").status_code == 200
    assert client.get("/compliance/audit-events/verify").status_code == 200
    assert client.get("/compliance/documents").status_code == 200
    assert client.post(
        "/compliance/documents",
        files={"file": ("nope.txt", b"no", "text/plain")},
        data={"doc_type": "other"},
    ).status_code == 403
    assert client.patch("/compliance/retention", json={"document_retention_years": 8}).status_code == 403

    _as(client, monkeypatch, "compliance-auditor")
    assert client.get("/compliance/audit-events/verify").status_code == 200
    license_id = next(row["id"] for row in client.get("/compliance/documents").json()["documents"] if row["filename"] == DEMO_LICENSE_FILENAME)
    downloaded = client.get(f"/compliance/documents/{license_id}/download")
    assert downloaded.status_code == 200
    assert b"Maison Madira" in downloaded.content
    assert client.post(
        "/compliance/documents",
        files={"file": ("nope.txt", b"no", "text/plain")},
        data={"doc_type": "other"},
    ).status_code == 403
    assert client.patch("/compliance/retention", json={"document_retention_years": 8}).status_code == 403
    assert client.get("/compliance/retention").status_code == 200

    _as(client, monkeypatch, "compliance-staff")
    for path in (
        "/compliance/audit-events",
        "/compliance/audit-events/verify",
        "/compliance/documents",
        "/compliance/retention",
    ):
        assert client.get(path).status_code == 403
    assert client.post(
        "/compliance/documents",
        files={"file": ("nope.txt", b"no", "text/plain")},
        data={"doc_type": "other"},
    ).status_code == 403
    assert client.patch("/compliance/retention", json={"document_retention_years": 8}).status_code == 403

    _as(client, monkeypatch, "compliance-owner")
    changed = client.patch("/compliance/retention", json={"document_retention_years": 12})
    assert changed.status_code == 200
    assert changed.json()["document_retention_years"] == 12
    events = client.get("/compliance/audit-events", params={"action": "retention.update"})
    assert events.json()["events"][0]["after_json"]["document_retention_years"] == 12
    assert client.patch("/compliance/retention", json={"document_retention_years": 0}).status_code == 422
    assert client.patch("/compliance/retention", json={"document_retention_years": 26}).status_code == 422


def test_documents_and_events_stay_inside_the_venue(client: TestClient, monkeypatch, tmp_path):
    monkeypatch.setenv("MADIRA_STORAGE_DIR", str(tmp_path))
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "vault-other"))
        if venue is None:
            venue = Venue(organization_id=demo.organization_id, name="Vault Other", slug="vault-other")
            session.add(venue)
            session.flush()
        _user(session, "vault-other-owner", "vault-other@example.com", venue.id, OWNER)
        other_id = venue.id
    finally:
        session.close()

    client.cookies.clear()
    uploaded = client.post(
        "/compliance/documents",
        files={"file": ("demo-only.txt", b"demo vault", "text/plain")},
        data={"doc_type": "certificate"},
    )
    assert uploaded.status_code == 200
    demo_doc = uploaded.json()["document"]["id"]
    demo_events = {row["id"] for row in client.get("/compliance/audit-events").json()["events"]}

    _as(client, monkeypatch, "vault-other-owner")
    other_list = client.get("/compliance/documents")
    assert other_list.status_code == 200
    assert demo_doc not in {row["id"] for row in other_list.json()["documents"]}
    assert client.get(f"/compliance/documents/{demo_doc}/download").status_code == 404
    other_events = client.get("/compliance/audit-events").json()["events"]
    assert demo_events.isdisjoint({row["id"] for row in other_events})

    other_upload = client.post(
        "/compliance/documents",
        files={"file": ("other-only.txt", b"other vault", "text/plain")},
        data={"doc_type": "certificate"},
    )
    assert other_upload.status_code == 200
    other_doc = other_upload.json()["document"]["id"]

    client.cookies.clear()
    assert client.get(f"/compliance/documents/{other_doc}/download").status_code == 404
    demo_names = {row["filename"] for row in client.get("/compliance/documents").json()["documents"]}
    assert "other-only.txt" not in demo_names
    assert "demo-only.txt" in demo_names
    missing = client.get(f"/compliance/documents/{uuid.uuid4()}/download")
    assert missing.status_code == 404


def test_unknown_document_is_not_found(client: TestClient):
    missing = client.get(f"/compliance/documents/{uuid.uuid4()}/download")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "document not found"
    with pytest.raises(NotFound):
        from madira.domain.session import session_scope
        from madira.domain.compliance.service import get_document

        demo = ensure_demo_tenant()
        with session_scope() as session:
            get_document(session, demo.venue_id, uuid.uuid4())
