"""Read and write embedding rows. Ranking uses pgvector when the column exists."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from madira.domain.embeddings.local import cosine
from madira.models import CatalogEmbedding

_vector_ready: bool | None = None


def content_hash(model: str, body: str) -> str:
    return hashlib.sha256(f"{model}\n{body}".encode("utf-8")).hexdigest()


def vector_column_ready(session: Session) -> bool:
    global _vector_ready
    if _vector_ready is not None:
        return _vector_ready
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        _vector_ready = False
        return False
    found = session.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'catalog_embeddings' AND column_name = 'embedding'"
        )
    ).scalar()
    _vector_ready = bool(found)
    return _vector_ready


def reset_vector_cache() -> None:
    global _vector_ready
    _vector_ready = None


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def get_row(session: Session, venue_id: uuid.UUID, subject_type: str, subject_id: uuid.UUID) -> CatalogEmbedding | None:
    return session.scalar(
        select(CatalogEmbedding).where(
            CatalogEmbedding.venue_id == venue_id,
            CatalogEmbedding.subject_type == subject_type,
            CatalogEmbedding.subject_id == subject_id,
        )
    )


def delete_row(session: Session, venue_id: uuid.UUID, subject_type: str, subject_id: uuid.UUID) -> None:
    row = get_row(session, venue_id, subject_type, subject_id)
    if row is not None:
        session.delete(row)


def save_row(
    session: Session,
    *,
    organization_id: uuid.UUID,
    venue_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    model_name: str,
    vector: list[float],
    body: str,
) -> CatalogEmbedding:
    digest = content_hash(model_name, body)
    row = get_row(session, venue_id, subject_type, subject_id)
    if row is None:
        row = CatalogEmbedding(
            organization_id=organization_id,
            venue_id=venue_id,
            subject_type=subject_type,
            subject_id=subject_id,
            model_name=model_name,
            dimension=len(vector),
            values=vector,
            content_hash=digest,
        )
        session.add(row)
        session.flush()
    else:
        row.organization_id = organization_id
        row.model_name = model_name
        row.dimension = len(vector)
        row.values = vector
        row.content_hash = digest
        session.flush()
    if vector_column_ready(session):
        session.execute(
            text("UPDATE catalog_embeddings SET embedding = CAST(:literal AS vector) WHERE id = :id"),
            {"literal": vector_literal(vector), "id": row.id},
        )
    return row


def current_rows(session: Session, venue_id: uuid.UUID, model_name: str, dimension: int) -> list[CatalogEmbedding]:
    return list(
        session.scalars(
            select(CatalogEmbedding).where(
                CatalogEmbedding.venue_id == venue_id,
                CatalogEmbedding.model_name == model_name,
                CatalogEmbedding.dimension == dimension,
            )
        ).all()
    )


def rank_sql(
    session: Session,
    venue_id: uuid.UUID,
    model_name: str,
    dimension: int,
    query: list[float],
    limit: int,
) -> list[tuple[str, uuid.UUID, float]] | None:
    """Nearest rows via pgvector, or ``None`` when the column is absent."""

    if not vector_column_ready(session):
        return None
    rows = session.execute(
        text(
            """
            SELECT subject_type, subject_id,
                   1 - (embedding <=> CAST(:literal AS vector)) AS score
            FROM catalog_embeddings
            WHERE venue_id = :venue_id
              AND model_name = :model_name
              AND dimension = :dimension
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:literal AS vector)
            LIMIT :limit
            """
        ),
        {
            "literal": vector_literal(query),
            "venue_id": venue_id,
            "model_name": model_name,
            "dimension": dimension,
            "limit": limit,
        },
    ).all()
    found = []
    for subject_type, subject_id, score in rows:
        if score is None:
            continue
        found.append((str(subject_type), subject_id, float(score)))
    return found


def rank_python(rows: list[CatalogEmbedding], query: list[float], limit: int) -> list[tuple[str, uuid.UUID, float]]:
    scored = []
    for row in rows:
        values = row.values if isinstance(row.values, list) else []
        vector = [float(value) for value in values]
        scored.append((row.subject_type, row.subject_id, cosine(query, vector)))
    scored.sort(key=lambda item: (-item[2], item[0], str(item[1])))
    return scored[:limit]
