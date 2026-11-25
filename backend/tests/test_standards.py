"""House standards ship with the venue. An edit bumps the version and is audited."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from madira.db import SessionLocal, init_db
from madira.domain.training.standards import DEFAULT_STANDARDS, list_standards, reset_standard, update_standard
from madira.main import app
from madira.models import AuditEvent, Standard
from madira.seed import seed
from madira.tenancy import ensure_demo_tenant

ROOT = Path(__file__).resolve().parents[2]


def test_defaults_seed_for_the_venue_and_an_edit_is_audited():
    init_db()
    seed()
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        session.execute(delete(Standard).where(Standard.venue_id == demo.venue_id))
        session.commit()
    finally:
        session.close()
    payload = list_standards(demo.venue_id)
    slugs = [row["slug"] for row in payload["standards"]]
    assert slugs == [row["slug"] for row in DEFAULT_STANDARDS]
    assert all(row["is_default"] and row["version"] == 1 for row in payload["standards"])
    again = list_standards(demo.venue_id)
    assert [row["id"] for row in again["standards"]] == [row["id"] for row in payload["standards"]]

    edited = update_standard(
        demo.venue_id,
        "opening-still",
        title="Opening a still bottle",
        body="Present the bottle, then wait for the host before anyone else is poured.",
    )
    assert edited["version"] == 2
    assert edited["is_default"] is False
    same = update_standard(
        demo.venue_id,
        "opening-still",
        title=edited["title"],
        body=edited["body"],
    )
    assert same["version"] == 2

    session = SessionLocal()
    try:
        event = session.scalar(
            select(AuditEvent)
            .where(AuditEvent.venue_id == demo.venue_id, AuditEvent.action == "training.standard.edit")
            .order_by(AuditEvent.seq.desc())
        )
        assert event is not None
        assert event.before_json["body"] != event.after_json["body"]
        assert event.before_json["version"] == 1
        assert event.after_json["version"] == 2
    finally:
        session.close()

    restored = reset_standard(demo.venue_id, "opening-still")
    assert restored["is_default"] is True
    assert restored["version"] == 3
    assert restored["body"] == next(row["body"] for row in DEFAULT_STANDARDS if row["slug"] == "opening-still")


def test_standards_routes_follow_the_author_role(monkeypatch):
    init_db()
    seed()
    monkeypatch.setenv("MADIRA_AUTH_SECRET", "standards-test-secret")
    from madira.auth import SESSION_COOKIE, issue_session
    from madira.tenancy import DEMO_USER_SUB

    with TestClient(app) as client:
        listed = client.get("/training/standards")
        assert listed.status_code == 200
        assert len(listed.json()["standards"]) == len(DEFAULT_STANDARDS)
        client.cookies.set("madira_demo_persona", "ana")
        denied = client.put(
            "/training/standards",
            json={"slug": "pour-sizes", "title": "Pour sizes", "body": "A taste, then a third of the glass."},
        )
        assert denied.status_code == 403
        client.cookies.set(SESSION_COOKIE, issue_session(DEMO_USER_SUB))
        before = next(row["version"] for row in client.get("/training/standards").json()["standards"] if row["slug"] == "pour-sizes")
        saved = client.put(
            "/training/standards",
            json={"slug": "pour-sizes", "title": "Pour sizes", "body": "A taste, then a third of the glass."},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["version"] == before + 1
        reset = client.post("/training/standards/pour-sizes/reset")
        assert reset.status_code == 200
        assert reset.json()["is_default"] is True


def test_migration_0016_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0016_training_content.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0015_list_pricing_coverage"' in source
    assert source.count('_enable_rls("') == 2
    assert "if not _is_postgres():" in source
    db = tmp_path / "training.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["PYTHONPATH"] = "backend"
    script = r'''
import os
import uuid
import sqlalchemy as sa
from alembic import command
from madira.db import _alembic_config

cfg = _alembic_config()
command.upgrade(cfg, "0015_list_pricing_coverage")
engine = sa.create_engine(os.environ["DATABASE_URL"])
org = uuid.uuid4().hex
venue = uuid.uuid4().hex
user = uuid.uuid4().hex
lesson = uuid.uuid4().hex
quiz = uuid.uuid4().hex
attempt = uuid.uuid4().hex

def insert(conn, table, values):
    cols = sa.inspect(conn).get_columns(table)
    payload = dict(values)
    for col in cols:
        name = col["name"]
        if name in payload or col.get("nullable") or col.get("default") is not None or col.get("primary_key"):
            continue
        kind = str(col["type"]).upper()
        payload[name] = 0 if any(token in kind for token in ("INT", "NUM", "REAL", "FLOA")) else ""
    names = ", ".join(payload)
    marks = ", ".join(f":{key}" for key in payload)
    conn.execute(sa.text(f"INSERT INTO {table} ({names}) VALUES ({marks})"), payload)

with engine.begin() as conn:
    insert(conn, "organizations", {"id": org, "name": "House", "slug": "house-training"})
    insert(conn, "venues", {"id": venue, "organization_id": org, "name": "House", "slug": "house-training", "currency": "USD"})
    insert(conn, "users", {"id": user, "google_sub": "training-user", "email": "t@example.com", "name": "T"})
    insert(conn, "lessons", {"id": lesson, "venue_id": venue, "slug": "wine-service", "title": "Wine", "role": "waitstaff", "category": "service", "body": "Present it."})
    insert(conn, "quizzes", {"id": quiz, "venue_id": venue, "lesson_id": lesson, "title": "Quiz", "questions": "[]"})
    insert(conn, "quiz_attempts", {"id": attempt, "venue_id": venue, "quiz_id": quiz, "staff_name": "Floor", "answers": "[]", "score": 100})

command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0019_list_versions"
    tables = set(sa.inspect(conn).get_table_names())
    assert {"standards", "quiz_reviews"} <= tables
    lesson_row = conn.execute(sa.text("SELECT position, status FROM lessons")).one()
    assert lesson_row.position == "server"
    assert lesson_row.status == "approved"
    attempt_row = conn.execute(sa.text("SELECT score_bp, user_id FROM quiz_attempts")).one()
    assert attempt_row.score_bp == 10000
    assert attempt_row.user_id is None
    memberships = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(memberships)"))}
    assert "position" in memberships

command.downgrade(cfg, "0015_list_pricing_coverage")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0015_list_pricing_coverage"
    tables = set(sa.inspect(conn).get_table_names())
    assert "standards" not in tables
    assert "quiz_reviews" not in tables
    lessons = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(lessons)"))}
    assert "position" not in lessons
    attempts = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(quiz_attempts)"))}
    assert "score_bp" not in attempts

command.upgrade(cfg, "head")
with engine.connect() as conn:
    version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0019_list_versions"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
    _ = Standard
