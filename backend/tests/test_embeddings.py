"""Catalog embeddings: local hasher, venue isolation, model changes, and the pgvector fallback."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from madira.db import SessionLocal, init_db
from madira.domain.catalog.service import ensure_sku
from madira.domain.embeddings.identity import LOCAL_MODEL
from madira.domain.embeddings.local import LOCAL_DIM, cosine, embed
from madira.domain.embeddings.provider import embed_query
from madira.domain.embeddings.schema import vector_extension_available
from madira.domain.embeddings.service import search_catalog
from madira.domain.usage.service import UsageError, update_limits
from madira.models import CatalogEmbedding, Membership, User, Venue
from madira.seed import seed
from madira.tenancy import OWNER, RequestContext, bind, ensure_demo_tenant, reset

ROOT = Path(__file__).resolve().parents[2]
SECRET = "Hidden Quince Cider"


def _demo():
    init_db()
    seed()
    return ensure_demo_tenant()


def test_local_embedder_is_deterministic_and_ranks_the_name():
    first = embed("Barolo G.D. Vajra 2019 wine")
    assert first == embed("Barolo G.D. Vajra 2019 wine")
    assert len(first) == LOCAL_DIM
    assert abs(sum(value * value for value in first) - 1) < 1e-6
    assert embed("Barolo") != embed("Chablis")
    barolo = cosine(embed("Barolo"), embed("Barolo G.D. Vajra 2019 Barolo Barolo Barolo wine"))
    chablis = cosine(embed("Barolo"), embed("Chablis 1er Vaillons Droin Chablis Chablis Chablis wine"))
    assert barolo > chablis
    assert barolo >= 0.2


def test_postgres_without_the_vector_extension_stays_on_json():
    class Nested:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class Conn:
        dialect = SimpleNamespace(name="postgresql")

        def begin_nested(self):
            return Nested()

        def execute(self, statement, *args, **kwargs):
            if "CREATE EXTENSION" in str(statement):
                raise RuntimeError('extension "vector" is not available')
            raise AssertionError(str(statement))

    assert vector_extension_available(Conn()) is False
    sqlite = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    assert vector_extension_available(sqlite) is False


def test_search_does_not_cross_venues():
    demo = _demo()
    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "embed-other"))
        if venue is None:
            venue = Venue(organization_id=demo.organization_id, name="Embed Other", slug="embed-other")
            session.add(venue)
            session.flush()
        user = session.scalar(select(User).where(User.google_sub == "embed-other-owner"))
        if user is None:
            from madira.auth import utcnow

            now = utcnow()
            user = User(google_sub="embed-other-owner", email="embed-other@example.com", name="Embed Other", picture="", created_at=now, last_login_at=now)
            session.add(user)
            session.flush()
        membership = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue.id))
        if membership is None:
            session.add(Membership(user_id=user.id, venue_id=venue.id, role=OWNER))
        ensure_sku(session, venue.id, category="cider", name=SECRET, producer="Hidden Orchard")
        other = RequestContext(
            user_id=user.id,
            email=user.email,
            name=user.name,
            venue_id=venue.id,
            organization_id=venue.organization_id,
            role=OWNER,
        )
        session.commit()
    finally:
        session.close()

    token = bind(demo)
    try:
        home = search_catalog(demo.venue_id, SECRET)
        barolo = search_catalog(demo.venue_id, "Barolo")
    finally:
        reset(token)
    assert all(hit["name"] != SECRET for hit in home["results"])
    assert barolo["mode"] == "semantic"
    assert any(hit["name"] == "Barolo G.D. Vajra 2019" for hit in barolo["results"])

    token = bind(other)
    try:
        found = search_catalog(other.venue_id, SECRET)
    finally:
        reset(token)
    assert found["mode"] == "semantic"
    assert [hit["name"] for hit in found["results"] if hit["name"] == SECRET] == [SECRET]


def test_a_model_change_reembeds_instead_of_mixing(monkeypatch):
    demo = _demo()
    token = bind(demo)
    try:
        search_catalog(demo.venue_id, "Barolo")
        session = SessionLocal()
        try:
            row = session.scalar(
                select(CatalogEmbedding).where(
                    CatalogEmbedding.venue_id == demo.venue_id,
                    CatalogEmbedding.model_name == LOCAL_MODEL,
                )
            )
            assert row is not None
            assert row.dimension == LOCAL_DIM
        finally:
            session.close()
        monkeypatch.setattr("madira.domain.embeddings.identity.LOCAL_MODEL", "madira-local-embed-v2")
        stale = search_catalog(demo.venue_id, "Barolo")
        session = SessionLocal()
        try:
            fresh = session.scalar(
                select(CatalogEmbedding).where(
                    CatalogEmbedding.venue_id == demo.venue_id,
                    CatalogEmbedding.subject_type == "sku",
                    CatalogEmbedding.model_name == "madira-local-embed-v2",
                )
            )
            assert fresh is not None
            assert fresh.dimension == LOCAL_DIM
        finally:
            session.close()
        assert stale["mode"] == "semantic"
        assert any(hit["name"] == "Barolo G.D. Vajra 2019" for hit in stale["results"])
    finally:
        reset(token)


def test_live_embedding_stops_at_the_cap_before_the_network(monkeypatch):
    demo = _demo()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-embed-test")
    called = {"n": 0}

    def boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("network")

    monkeypatch.setattr("madira.domain.embeddings.provider.httpx.post", boom)
    try:
        update_limits(demo.venue_id, monthly_spend_cap_cents=0, requests_per_minute=None)
        with pytest.raises(UsageError) as caught:
            embed_query(demo.venue_id, "Barolo")
        assert "cap" in caught.value.message
        assert called["n"] == 0
    finally:
        update_limits(demo.venue_id, monthly_spend_cap_cents=None, requests_per_minute=None)


def test_migration_0030_upgrades_and_downgrades(tmp_path):
    source = (ROOT / "backend/madira/migrations/versions/0030_catalog_embeddings.py").read_text()
    assert 'revision: str = "0030_catalog_embeddings"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "0029_tablet_pin"' in source
    assert source.count('_enable_rls("') == 1
    assert "CREATE EXTENSION IF NOT EXISTS vector" in (ROOT / "backend/madira/domain/embeddings/schema.py").read_text()
    assert "if not _is_postgres():" in source
    db = tmp_path / "embed.db"
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
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0030_catalog_embeddings"
    columns = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(catalog_embeddings)"))}
    assert {"venue_id", "organization_id", "subject_type", "subject_id", "model_name", "dimension", "values"} <= columns
    assert "embedding" not in columns
command.downgrade(cfg, "0029_tablet_pin")
with engine.connect() as conn:
    tables = set(sa.inspect(conn).get_table_names())
    assert "catalog_embeddings" not in tables
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0029_tablet_pin"
command.upgrade(cfg, "head")
with engine.connect() as conn:
    assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0030_catalog_embeddings"
print("migration-ok")
'''
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "migration-ok" in proc.stdout
