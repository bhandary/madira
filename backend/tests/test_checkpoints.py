"""A checkpointed thread survives a new process, and only for its own venue."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _python(database_url: str, script: str) -> dict:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(ROOT / "backend")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    lines = [line for line in completed.stdout.splitlines() if line.startswith("MADIRA_CKPT ")]
    assert lines, completed.stdout + completed.stderr
    return json.loads(lines[-1].split(" ", 1)[1])


def _write_script(thread_id: str, marker: str) -> str:
    return f"""
import json
from madira.db import init_db
from madira.seed import seed
from madira.agents.orchestrator import invoke_head_sommelier
init_db()
seed()
result = invoke_head_sommelier({marker!r}, thread_id={thread_id!r})
print("MADIRA_CKPT " + json.dumps({{"reply": result["reply"]}}))
"""


def _read_script(thread_id: str) -> str:
    return f"""
import json
import uuid
from madira.tenancy import ensure_demo_tenant
from madira.agents.checkpointer import thread_message_texts
demo = str(ensure_demo_tenant().venue_id)
other = str(uuid.uuid4())
print("MADIRA_CKPT " + json.dumps({{
    "own": thread_message_texts({thread_id!r}, demo),
    "other": thread_message_texts({thread_id!r}, other),
}}))
"""


def _assert_restart(database_url: str) -> None:
    thread_id = str(uuid.uuid4())
    marker = f"checkpoint-marker-{uuid.uuid4()}"
    written = _python(database_url, _write_script(thread_id, marker))
    assert written["reply"]
    read = _python(database_url, _read_script(thread_id))
    assert any(marker in text for text in read["own"]), read
    assert read["other"] == []


def test_thread_survives_a_sqlite_restart_and_stays_in_its_venue():
    with tempfile.TemporaryDirectory() as tmp:
        _assert_restart(f"sqlite:///{Path(tmp) / 'madira.db'}")


def test_thread_survives_a_postgres_restart_and_stays_in_its_venue():
    admin_url = os.environ.get("MADIRA_TEST_POSTGRES", "postgresql://madira:madira@127.0.0.1:5432/postgres")
    psycopg = pytest.importorskip("psycopg")
    try:
        admin = psycopg.connect(admin_url, autocommit=True, connect_timeout=3)
    except Exception as exc:
        pytest.skip(f"Postgres is not running locally: {exc}")
    name = "madira_ckpt_" + uuid.uuid4().hex[:12]
    admin.execute(f'CREATE DATABASE "{name}"')
    try:
        _assert_restart(f"postgresql+psycopg://madira:madira@127.0.0.1:5432/{name}")
    finally:
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (name,),
        )
        admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        admin.close()
