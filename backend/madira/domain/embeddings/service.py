"""Build, store, and search catalog embeddings.

The structured pairing score is unchanged. This module only adds a similarity
sentence and a catalog search ranking.
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.embeddings.documents import dish_document, note_document, sku_document
from madira.domain.embeddings.identity import identity, local_mode
from madira.domain.embeddings.local import cosine, embed as local_embed
from madira.domain.embeddings.provider import EmbeddingError, embed_query
from madira.domain.embeddings.vectors import (
    content_hash,
    current_rows,
    delete_row,
    get_row,
    rank_python,
    rank_sql,
    save_row,
)
from madira.domain.errors import DraftFailed
from madira.domain.session import session_scope
from madira.domain.usage.service import UsageError
from madira.models import CatalogEmbedding, Product, ProductVariant, Sku, TastingNote, Venue

_SEMANTIC_FLOOR = 0.2
_LIMIT = 8
_live_vectors: dict[tuple[str, str, str], tuple[float, ...]] = {}


def similarity_words(score: float) -> str:
    if score >= 0.45:
        return "The taste lines up closely with this dish."
    if score >= 0.3:
        return "The taste is somewhat close to this dish."
    return "The taste is only loosely related to this dish."


def _embed(venue_id: uuid.UUID, body: str) -> list[float]:
    if local_mode():
        return local_embed(body)
    try:
        return embed_query(venue_id, body)
    except UsageError as exc:
        raise DraftFailed(exc.message, exc.status) from exc
    except EmbeddingError as exc:
        raise DraftFailed(exc.message, 502) from exc


@lru_cache(maxsize=256)
def _cached_local(body: str) -> tuple[float, ...]:
    return tuple(local_embed(body))


def _query_vector(venue_id: uuid.UUID, body: str, model: str, dimension: int) -> list[float]:
    if local_mode():
        return list(_cached_local(body))
    key = (str(venue_id), model, body)
    held = _live_vectors.get(key)
    if held is not None:
        return list(held)
    vector = _embed(venue_id, body)
    if len(vector) != dimension:
        raise DraftFailed(f"The embedding provider returned {len(vector)} dimensions, expected {dimension}.", 502)
    _live_vectors[key] = tuple(vector)
    if len(_live_vectors) > 256:
        _live_vectors.pop(next(iter(_live_vectors)))
    return vector


def _approved_notes(session: Session, venue_id: uuid.UUID, product_id: uuid.UUID) -> list[TastingNote]:
    return list(
        session.scalars(
            select(TastingNote)
            .where(
                TastingNote.venue_id == venue_id,
                TastingNote.product_id == product_id,
                TastingNote.status == "approved",
            )
            .order_by(TastingNote.approved_at, TastingNote.id)
        ).all()
    )


def _skus_for_product(session: Session, venue_id: uuid.UUID, product_id: uuid.UUID) -> list[Sku]:
    return list(
        session.scalars(
            select(Sku)
            .join(ProductVariant, Sku.product_variant_id == ProductVariant.id)
            .where(Sku.venue_id == venue_id, ProductVariant.product_id == product_id)
        ).all()
    )


def embed_subject(venue_id: uuid.UUID, subject_type: str, subject_id: uuid.UUID) -> dict:
    current = identity()
    if current is None:
        raise DraftFailed("Live embeddings are not available for this provider.", 502)
    model, dimension = current
    with session_scope() as session:
        venue = session.get(Venue, venue_id)
        if venue is None:
            raise DraftFailed("venue not found", 404)
        if subject_type == "sku":
            sku = session.get(Sku, subject_id)
            if sku is None or sku.venue_id != venue_id:
                delete_row(session, venue_id, "sku", subject_id)
                session.commit()
                return {"subject_type": "sku", "subject_id": str(subject_id), "updated": False}
            notes = _approved_notes(session, venue_id, sku.variant.product_id)
            body = sku_document(sku, notes)
        elif subject_type == "note":
            note = session.get(TastingNote, subject_id)
            if note is None or note.venue_id != venue_id or note.status != "approved":
                delete_row(session, venue_id, "note", subject_id)
                session.commit()
                return {"subject_type": "note", "subject_id": str(subject_id), "updated": False}
            product = session.get(Product, note.product_id)
            if product is None:
                delete_row(session, venue_id, "note", subject_id)
                session.commit()
                return {"subject_type": "note", "subject_id": str(subject_id), "updated": False}
            body = note_document(product, note)
        else:
            raise DraftFailed("Unknown embedding subject.", 422)
        digest = content_hash(model, body)
        existing = get_row(session, venue_id, subject_type, subject_id)
        if (
            existing is not None
            and existing.model_name == model
            and existing.dimension == dimension
            and existing.content_hash == digest
        ):
            return {"subject_type": subject_type, "subject_id": str(subject_id), "model": model, "updated": False}
        vector = _embed(venue_id, body)
        if len(vector) != dimension:
            raise DraftFailed(f"The embedding provider returned {len(vector)} dimensions, expected {dimension}.", 502)
        save_row(
            session,
            organization_id=venue.organization_id,
            venue_id=venue_id,
            subject_type=subject_type,
            subject_id=subject_id,
            model_name=model,
            vector=vector,
            body=body,
        )
        session.commit()
    return {"subject_type": subject_type, "subject_id": str(subject_id), "model": model, "dimension": dimension, "updated": True}


def backfill_venue(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        sku_ids = list(session.scalars(select(Sku.id).where(Sku.venue_id == venue_id)).all())
        note_ids = list(
            session.scalars(
                select(TastingNote.id).where(TastingNote.venue_id == venue_id, TastingNote.status == "approved")
            ).all()
        )
    updated = 0
    for sku_id in sku_ids:
        if embed_subject(venue_id, "sku", sku_id).get("updated"):
            updated += 1
    for note_id in note_ids:
        if embed_subject(venue_id, "note", note_id).get("updated"):
            updated += 1
    return {"skus": len(sku_ids), "notes": len(note_ids), "updated": updated}


def _missing(session: Session, venue_id: uuid.UUID, model: str, dimension: int) -> bool:
    sku_ids = list(session.scalars(select(Sku.id).where(Sku.venue_id == venue_id)).all())
    if not sku_ids:
        return False
    ready = set(
        session.scalars(
            select(CatalogEmbedding.subject_id).where(
                CatalogEmbedding.venue_id == venue_id,
                CatalogEmbedding.subject_type == "sku",
                CatalogEmbedding.model_name == model,
                CatalogEmbedding.dimension == dimension,
            )
        ).all()
    )
    return any(sku_id not in ready for sku_id in sku_ids)


def _ensure_indexed(venue_id: uuid.UUID) -> None:
    current = identity()
    if current is None:
        return
    model, dimension = current
    with session_scope() as session:
        missing = _missing(session, venue_id, model, dimension)
    if not missing:
        return
    from madira.jobs.runner import JobError, accept

    try:
        accept("catalog.embed_backfill", {}, max_attempts=1)
    except JobError as exc:
        raise DraftFailed(exc.message or "The catalog embedding failed.", 502) from exc


def _hit(sku: Sku, score: float | None, why: str) -> dict:
    product = sku.variant.product
    return {
        "sku_id": str(sku.id),
        "product_id": str(product.id),
        "name": product.name,
        "producer": product.producer,
        "region": product.region,
        "style": product.style,
        "category": product.category,
        "vintage": sku.variant.vintage or "",
        "similarity": None if score is None else round(float(score), 4),
        "why": why,
    }


def _keyword(session: Session, venue_id: uuid.UUID, query: str) -> list[dict]:
    needle = query.casefold().strip()
    if not needle:
        return []
    ranked = []
    for sku in session.scalars(select(Sku).where(Sku.venue_id == venue_id)).all():
        product = sku.variant.product
        notes = _approved_notes(session, venue_id, product.id)
        fields = {
            "name": product.name or "",
            "producer": product.producer or "",
            "region": product.region or "",
            "style": product.style or "",
            "grape": product.grape or "",
            "category": product.category or "",
            "vintage": sku.variant.vintage or "",
            "barcode": sku.barcode or "",
            "notes": " ".join(note.guest_description or "" for note in notes),
        }
        haystacks = [value.casefold() for value in fields.values()]
        if not any(needle in value for value in haystacks):
            continue
        name = fields["name"].casefold()
        if name == needle:
            rank = 0
        elif name.startswith(needle):
            rank = 1
        elif needle in name:
            rank = 2
        else:
            rank = 3
        ranked.append((rank, product.name.casefold(), str(sku.id), sku))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [_hit(sku, None, "Matched the catalog words.") for _rank, _name, _sku_id, sku in ranked[:_LIMIT]]


def _resolve_skus(session: Session, venue_id: uuid.UUID, subject_type: str, subject_id: uuid.UUID) -> list[Sku]:
    if subject_type == "sku":
        sku = session.get(Sku, subject_id)
        if sku is None or sku.venue_id != venue_id:
            return []
        return [sku]
    note = session.get(TastingNote, subject_id)
    if note is None or note.venue_id != venue_id or note.status != "approved":
        return []
    return _skus_for_product(session, venue_id, note.product_id)


def search_catalog(venue_id: uuid.UUID, query: str) -> dict:
    text = (query or "").strip()[:200]
    if not text:
        return {"query": "", "mode": "keyword", "results": []}
    current = identity()
    if current is not None:
        _ensure_indexed(venue_id)
    with session_scope() as session:
        semantic = []
        if current is not None:
            model, dimension = current
            query_vector = _query_vector(venue_id, text, model, dimension)
            ranked = rank_sql(session, venue_id, model, dimension, query_vector, 24)
            if ranked is None:
                ranked = rank_python(current_rows(session, venue_id, model, dimension), query_vector, 24)
            best: dict[uuid.UUID, tuple[float, Sku]] = {}
            for subject_type, subject_id, score in ranked:
                for sku in _resolve_skus(session, venue_id, subject_type, subject_id):
                    held = best.get(sku.id)
                    if held is None or score > held[0]:
                        best[sku.id] = (score, sku)
            ordered = sorted(best.values(), key=lambda item: (-item[0], item[1].variant.product.name.casefold(), str(item[1].id)))
            if ordered and ordered[0][0] >= _SEMANTIC_FLOOR:
                semantic = [_hit(sku, score, similarity_words(score)) for score, sku in ordered[:_LIMIT]]
        if semantic:
            return {"query": text, "mode": "semantic", "results": semantic}
        return {"query": text, "mode": "keyword", "results": _keyword(session, venue_id, text)}


def similarity_line(session: Session, dish, sku_id: uuid.UUID) -> str:
    """A plain-language similarity signal. It does not change which bottle was chosen."""

    current = identity()
    if current is None or sku_id is None:
        return ""
    model, dimension = current
    sku = session.get(Sku, sku_id)
    if sku is None or sku.venue_id != dish.venue_id:
        return ""
    dish_text = dish_document(dish)
    if local_mode():
        notes = _approved_notes(session, dish.venue_id, sku.variant.product_id)
        left = _cached_local(dish_text)
        right = _cached_local(sku_document(sku, notes))
        if len(left) != len(right):
            return ""
        return similarity_words(cosine(list(left), list(right)))
    row = get_row(session, dish.venue_id, "sku", sku_id)
    if row is None or row.model_name != model or row.dimension != dimension:
        return ""
    if not isinstance(row.values, list):
        return ""
    stored = [float(value) for value in row.values]
    query = _query_vector(dish.venue_id, dish_text, model, dimension)
    return similarity_words(cosine(query, stored))
