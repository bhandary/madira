"""Migration 0027 adds the pairing cache and drops it on the way down."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_migration_0027_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0027_pairing_cache.py").read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "0026_usage_metering"' in source
    assert source.count('_enable_rls("') == 1
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "if not _is_postgres():" in source
    assert "venue_isolation" in source
    db = tmp_path / "pairing-cache.db"
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
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0027_pairing_cache"
    tables = set(sa.inspect(conn).get_table_names())
    assert "pairing_cache" in tables
    columns = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(pairing_cache)"))}
    assert {"venue_id", "dish_id", "menu_version_id", "list_version_id", "cache_key", "result"} <= columns

command.downgrade(cfg, "0026_usage_metering")
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "pairing_cache" not in tables
    assert "agent_usage" in tables
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0026_usage_metering"

command.upgrade(cfg, "head")
with engine.connect() as conn:
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0027_pairing_cache"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
