"""Queue claim, retry, venue scope, and the inline job kinds."""

from __future__ import annotations

import logging
import signal
import threading
import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.jobs.handlers import HANDLERS, REQUEST_ATTEMPTS
from madira.jobs.queue import (
    POSTGRES_CLAIM,
    SQLITE_CLAIM,
    claim_next,
    claim_sql,
    current_time,
    enqueue,
    load_job,
    mark_succeeded,
    next_poll_delay,
    public_error,
)
from madira.jobs.runner import perform, run_existing
from madira.jobs.schedule import enqueue_briefings, enqueue_pos, schedule_due
from madira.main import app
from madira.models import Job, Membership, ReminderRule, User, Venue
from madira.seed import seed
from madira.tenancy import OWNER, RequestContext, bind, ensure_demo_tenant, reset
from madira.worker import install_stop_signals, request_stop, reset_stop, serve, stop_requested


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def _other_venue(demo: RequestContext) -> Venue:
    session = SessionLocal()
    try:
        venue = Venue(
            organization_id=demo.organization_id,
            name="Other Queue",
            slug=f"other-queue-{uuid.uuid4().hex[:8]}",
            jurisdiction="US-CA",
        )
        session.add(venue)
        session.flush()
        user = User(
            google_sub=f"queue-{uuid.uuid4().hex[:8]}",
            email=f"queue-{uuid.uuid4().hex[:6]}@example.com",
            name="Other Owner",
            picture="",
            created_at=current_time(),
            last_login_at=current_time(),
        )
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, venue_id=venue.id, role=OWNER))
        session.commit()
        session.refresh(venue)
        return venue
    finally:
        session.close()


def test_skip_locked_sql_is_postgres_only():
    assert "FOR UPDATE SKIP LOCKED" in POSTGRES_CLAIM
    assert "FOR UPDATE" not in SQLITE_CLAIM
    assert claim_sql("postgresql") == POSTGRES_CLAIM
    assert claim_sql("sqlite") == SQLITE_CLAIM
    assert "RETURNING id" in SQLITE_CLAIM


def test_poll_delay_backs_off_until_a_job_is_found():
    assert next_poll_delay(0.25, found=False) == 0.5
    assert next_poll_delay(4, found=False) == 5
    assert next_poll_delay(4, found=True) == 0.25


def test_sqlite_claim_is_exclusive(monkeypatch):
    monkeypatch.setenv("MADIRA_JOBS_INLINE", "0")
    demo = _demo()
    kind = f"tests.claim.{uuid.uuid4().hex[:8]}"
    first = enqueue(kind=kind, venue_id=demo.venue_id, organization_id=demo.organization_id, max_attempts=3)
    second = enqueue(kind=kind, venue_id=demo.venue_id, organization_id=demo.organization_id, max_attempts=3)
    found: list[uuid.UUID | None] = []
    barrier = threading.Barrier(2)

    def take():
        barrier.wait(timeout=5)
        found.append(claim_next(f"worker-{threading.get_ident()}", kind=kind))

    threads = [threading.Thread(target=take), threading.Thread(target=take)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    ids = {item for item in found if item is not None}
    assert ids == {first, second}
    assert claim_next("nobody", kind=kind) is None


def test_retry_then_dead_letter_keeps_the_prompt_out_of_the_log(monkeypatch, caplog):
    monkeypatch.setenv("MADIRA_JOBS_INLINE", "0")
    demo = _demo()
    kind = f"tests.flaky.{uuid.uuid4().hex[:8]}"
    calls = {"n": 0}

    def flaky(_args):
        calls["n"] += 1
        raise RuntimeError("PROMPT-SECRET sk-should-not-log")

    HANDLERS[kind] = flaky
    try:
        job_id = enqueue(
            kind=kind,
            venue_id=demo.venue_id,
            organization_id=demo.organization_id,
            args={"body_b64": "c2VjcmV0"},
            max_attempts=2,
        )
        with caplog.at_level(logging.WARNING, logger="madira.jobs"):
            assert run_existing(job_id, "try-1") == "failed"
            job = load_job(job_id)
            assert job is not None
            assert job.attempts == 1
            assert job.run_at > job.updated_at
            assert "PROMPT-SECRET" not in job.last_error
            assert "sk-should-not-log" not in job.last_error
            assert "c2VjcmV0" not in job.last_error
            monkeypatch.setattr("madira.jobs.queue.current_time", lambda: job.run_at + timedelta(seconds=1))
            assert run_existing(job_id, "try-2") == "dead"
        text = caplog.text
        assert "PROMPT-SECRET" not in text
        assert "sk-should-not-log" not in text
        assert "c2VjcmV0" not in text
        dead = load_job(job_id)
        assert dead is not None and dead.status == "dead"
        assert dead.attempts == 2
        assert calls["n"] == 2
    finally:
        HANDLERS.pop(kind, None)


def test_second_attempt_succeeds(monkeypatch):
    monkeypatch.setenv("MADIRA_JOBS_INLINE", "0")
    demo = _demo()
    kind = f"tests.once.{uuid.uuid4().hex[:8]}"
    calls = {"n": 0}

    def once(_args):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("not yet")
        return {"ok": True}

    HANDLERS[kind] = once
    try:
        job_id = enqueue(
            kind=kind,
            venue_id=demo.venue_id,
            organization_id=demo.organization_id,
            max_attempts=3,
        )
        assert run_existing(job_id, "a") == "failed"
        job = load_job(job_id)
        assert job is not None
        monkeypatch.setattr("madira.jobs.queue.current_time", lambda: job.run_at + timedelta(seconds=1))
        assert run_existing(job_id, "b") == "succeeded"
        done = load_job(job_id)
        assert done is not None and done.result == {"ok": True}
        assert calls["n"] == 2
    finally:
        HANDLERS.pop(kind, None)


def test_expired_lock_is_reclaimed_and_the_old_worker_cannot_finish(monkeypatch):
    monkeypatch.setenv("MADIRA_JOBS_INLINE", "0")
    demo = _demo()
    kind = f"tests.lock.{uuid.uuid4().hex[:8]}"
    job_id = enqueue(kind=kind, venue_id=demo.venue_id, organization_id=demo.organization_id, max_attempts=3)
    claimed = claim_next("first", kind=kind, lease=60)
    assert claimed == job_id
    session = SessionLocal()
    try:
        row = session.get(Job, job_id)
        assert row is not None
        row.locked_until = current_time() - timedelta(seconds=5)
        session.commit()
    finally:
        session.close()
    again = claim_next("second", kind=kind)
    assert again == job_id
    assert mark_succeeded(job_id, "first", {"stolen": True}) is False
    held = load_job(job_id)
    assert held is not None
    assert held.locked_by == "second"
    assert held.status == "running"
    assert held.attempts == 2
    HANDLERS[kind] = lambda _args: {"ok": True}
    try:
        perform(job_id, "second")
    finally:
        HANDLERS.pop(kind, None)
    done = load_job(job_id)
    assert done is not None and done.status == "succeeded"
    assert done.result == {"ok": True}


def test_expired_lock_past_the_attempt_cap_is_dead(monkeypatch):
    monkeypatch.setenv("MADIRA_JOBS_INLINE", "0")
    demo = _demo()
    kind = f"tests.deadlock.{uuid.uuid4().hex[:8]}"
    job_id = enqueue(kind=kind, venue_id=demo.venue_id, organization_id=demo.organization_id, max_attempts=1)
    assert claim_next("holder", kind=kind, lease=60) == job_id
    session = SessionLocal()
    try:
        row = session.get(Job, job_id)
        assert row is not None
        row.locked_until = current_time() - timedelta(seconds=5)
        session.commit()
    finally:
        session.close()
    assert claim_next("other", kind=kind) is None
    dead = load_job(job_id)
    assert dead is not None
    assert dead.status == "dead"
    assert dead.last_error == "The lock expired."


def _park_claimable() -> None:
    session = SessionLocal()
    try:
        rows = session.scalars(select(Job).where(Job.status.in_(("queued", "failed", "running")))).all()
        now = current_time()
        for row in rows:
            row.status = "dead"
            row.locked_by = None
            row.locked_until = None
            row.finished_at = now
        session.commit()
    finally:
        session.close()


def test_sigterm_finishes_the_current_job_and_leaves_the_next():
    demo = _demo()
    _park_claimable()
    kind = f"tests.stop.{uuid.uuid4().hex[:8]}"

    def stop_after(_args):
        request_stop()
        return {"ok": True}

    HANDLERS[kind] = stop_after
    try:
        first = enqueue(kind=kind, venue_id=demo.venue_id, organization_id=demo.organization_id, max_attempts=1)
        second = enqueue(kind=kind, venue_id=demo.venue_id, organization_id=demo.organization_id, max_attempts=1)
        reset_stop()
        box: dict[str, int] = {}

        def run():
            box["code"] = serve(schedule=False, poll_floor=0.05)

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(8)
        assert not thread.is_alive()
        assert box["code"] == 0
        finished = load_job(first)
        waiting = load_job(second)
        assert finished is not None and finished.status == "succeeded"
        assert waiting is not None and waiting.status == "queued"
    finally:
        HANDLERS.pop(kind, None)
        reset_stop()


def test_sigterm_handler_requests_stop():
    previous = signal.getsignal(signal.SIGTERM)
    reset_stop()
    try:
        install_stop_signals()
        signal.raise_signal(signal.SIGTERM)
        assert stop_requested()
    finally:
        signal.signal(signal.SIGTERM, previous)
        reset_stop()


def test_job_runs_with_that_venues_scope(monkeypatch):
    monkeypatch.setenv("MADIRA_JOBS_INLINE", "0")
    demo = _demo()
    other = _other_venue(demo)
    kind = f"tests.scope.{uuid.uuid4().hex[:8]}"

    def remember(_args):
        from madira.tenancy import current_request

        ctx = current_request()
        assert ctx is not None
        return {"venue_id": str(ctx.venue_id)}

    HANDLERS[kind] = remember
    try:
        own = enqueue(kind=kind, venue_id=demo.venue_id, organization_id=demo.organization_id, max_attempts=1)
        theirs = enqueue(kind=kind, venue_id=other.id, organization_id=other.organization_id, max_attempts=1)
        assert run_existing(own, "scope-a") == "succeeded"
        assert run_existing(theirs, "scope-b") == "succeeded"
        assert load_job(own).result["venue_id"] == str(demo.venue_id)
        assert load_job(theirs).result["venue_id"] == str(other.id)
    finally:
        HANDLERS.pop(kind, None)


def test_reminders_refresh_does_not_write_another_venue(monkeypatch):
    monkeypatch.setenv("MADIRA_JOBS_INLINE", "0")
    demo = _demo()
    other = _other_venue(demo)
    session = SessionLocal()
    try:
        session.query(ReminderRule).filter(ReminderRule.venue_id == demo.venue_id).delete()
        session.commit()
    finally:
        session.close()
    ids = schedule_due()
    for job_id in ids:
        job = load_job(job_id)
        if job is None or job.kind != "reminders.refresh" or job.venue_id != demo.venue_id:
            continue
        assert run_existing(job_id, "reminders") == "succeeded"
    session = SessionLocal()
    try:
        own = session.scalars(select(ReminderRule).where(ReminderRule.venue_id == demo.venue_id)).all()
        foreign = session.scalars(select(ReminderRule).where(ReminderRule.venue_id == other.id)).all()
        assert own
        assert foreign == []
    finally:
        session.close()


def test_get_job_is_scoped_to_the_venue_and_the_role():
    demo = _demo()
    other = _other_venue(demo)
    with TestClient(app) as client:
        ingested = client.post("/menus/ingest", data={"text": "OCTOPUS\nGrilled, olive oil\n28"})
        assert ingested.status_code == 200, ingested.text
        body = ingested.json()
        assert body["menu_id"]
        job_id = body["job_id"]
        own = client.get(f"/jobs/{job_id}")
        assert own.status_code == 200, own.text
        assert own.json()["status"] == "succeeded"
        assert own.json()["kind"] == "menu.ingest"
        assert "body_b64" not in own.text
        client.cookies.set("madira_demo_persona", "ana")
        denied = client.get(f"/jobs/{job_id}")
        assert denied.status_code == 403
        client.cookies.delete("madira_demo_persona")
        hidden = enqueue(
            kind="menu.ingest",
            venue_id=other.id,
            organization_id=other.organization_id,
            max_attempts=REQUEST_ATTEMPTS,
        )
        missing = client.get(f"/jobs/{hidden}")
        assert missing.status_code == 404


def test_each_kind_runs_inline(monkeypatch):
    demo = _demo()
    with TestClient(app) as client:
        menu = client.post("/menus/ingest", data={"text": "OCTOPUS\nGrilled, olive oil\n28"})
        assert menu.status_code == 200, menu.text
        assert menu.json()["job_id"]
        _succeeded(menu.json()["job_id"], "menu.ingest")

        imported = client.post(
            "/lists/import",
            files={"file": ("list.csv", b"section,name,producer,category\nWhite,Test Wine,House,wine\n", "text/csv")},
            data={"confirm": "false"},
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["mode"] == "preview"
        _succeeded(imported.json()["job_id"], "list.import")

        supplier = client.post("/procurement/suppliers", json={"name": f"Queue Sheets {uuid.uuid4().hex[:6]}"})
        assert supplier.status_code == 200, supplier.text
        sheet = client.post(
            "/procurement/price-sheets",
            data={"supplier_id": supplier.json()["supplier"]["id"]},
            files={"file": ("sheet.csv", b"name,sku,price\nQueue Bottle,,12.00\n", "text/csv")},
        )
        assert sheet.status_code == 200, sheet.text
        _succeeded(sheet.json()["job_id"], "price_sheet.ingest")

    from madira.domain.pos.service import connect_demo

    token = bind(demo)
    try:
        connect_demo(demo.venue_id)
    finally:
        reset(token)
    monkeypatch.setenv("MADIRA_JOBS_INLINE", "0")
    briefing_ids = enqueue_briefings()
    assert any(run_existing(job_id, "briefing") == "succeeded" for job_id in briefing_ids)
    pos_ids = [
        job_id
        for job_id in enqueue_pos()
        if (load_job(job_id) or Job()).venue_id == demo.venue_id
    ]
    assert pos_ids
    assert run_existing(pos_ids[0], "pos") == "succeeded"
    assert load_job(pos_ids[0]).kind == "pos.sync"


def _succeeded(job_id: str, kind: str) -> None:
    job = load_job(uuid.UUID(job_id))
    assert job is not None
    assert job.status == "succeeded"
    assert job.kind == kind
    assert job.venue_id is not None


def test_sensor_and_invoice_jobs_run_inline():
    from madira.domain.catalog.service import ensure_sku
    from madira.domain.session import session_scope

    demo = _demo()
    suffix = uuid.uuid4().hex[:6]
    with TestClient(app) as client:
        zones = client.get("/inventory/storage-zones")
        assert zones.status_code == 200, zones.text
        zone_id = zones.json()["zones"][0]["id"]
        external = f"job-{suffix}"
        created = client.post(
            "/sensors",
            json={"name": "Job probe", "zone_id": zone_id, "metric": "temperature_c", "external_id": external},
        )
        assert created.status_code == 200, created.text
        preview = client.post(
            "/sensors/imports",
            files={"file": ("readings.csv", f"sensor,timestamp,metric,value\n{external},2020-01-15T00:00:00+00:00,temperature_c,12\n".encode(), "text/csv")},
            data={"filename": "readings.csv"},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["status"] == "pending_review"
        _succeeded(preview.json()["job_id"], "sensor.csv")

        with session_scope() as session:
            ensure_sku(
                session,
                demo.venue_id,
                category="wine",
                name=f"Job Bottle {suffix}",
                barcode=f"JOB-{suffix}",
                cost=1000,
                vintage="2020",
                par=0,
            )
            session.commit()
        supplier = client.post("/procurement/suppliers", json={"name": f"Job Receiving {suffix}", "default_case_size": 1})
        assert supplier.status_code == 200, supplier.text
        drafted = client.post(
            "/procurement/orders",
            json={
                "supplier_id": supplier.json()["supplier"]["id"],
                "lines": [{"sku": f"JOB-{suffix}", "product_name": "Bottle", "bottles": 1, "case_size": 1, "unit_cost_cents": 1000}],
            },
        )
        assert drafted.status_code == 200, drafted.text
        po_id = drafted.json()["id"]
        assert client.post(f"/procurement/orders/{po_id}/approve", json={"comment": "ok"}).status_code == 200
        assert client.post(f"/procurement/orders/{po_id}/send").status_code == 200
        invoice = client.post(
            f"/procurement/orders/{po_id}/invoices",
            files={"file": ("delivery.jpg", b"\xff\xd8\xff\x00job-photo", "image/jpeg")},
            data={"invoice_number": f"JOB-{suffix}", "invoice_date": "2026-11-24"},
        )
        assert invoice.status_code == 200, invoice.text
        assert invoice.json()["status"] == "uploaded"
        _succeeded(invoice.json()["job_id"], "invoice.extract")


def test_public_error_drops_a_secret_in_a_domain_message():
    class Boom(Exception):
        def __init__(self) -> None:
            super().__init__("nope")
            self.message = "provider said sk-live-secret"

    assert public_error(Boom()) == "The job failed."
    assert "RuntimeError" in public_error(RuntimeError("PROMPT sk-abc"))
