"""Live embedding calls through the provider already configured for chat.

OpenAI and Google are called with httpx, which is already installed. The API
key is sent as a header and is not written into the error text.
"""

from __future__ import annotations

import uuid

import httpx

from madira.domain.embeddings.identity import identity, local_mode
from madira.domain.usage.service import UsageError, charge_embedding
from madira.llm_runtime import resolve_runtime


class EmbeddingError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def embed_query(venue_id: uuid.UUID, text: str) -> list[float]:
    current = identity()
    if current is None or local_mode():
        raise EmbeddingError("Live embeddings are not available for this provider.")
    model, dimension = current
    runtime = resolve_runtime()
    estimated = max(1, len(text or "") // 4)
    charge_embedding(venue_id, model=model, tokens_in=estimated, latency_ms=0)
    try:
        if runtime.provider == "openai":
            vector = _openai(runtime.api_key, model, dimension, text)
        elif runtime.provider == "google_genai":
            vector = _google(runtime.api_key, model, dimension, text)
        else:
            raise EmbeddingError("Live embeddings are not available for this provider.")
    except EmbeddingError:
        raise
    except UsageError:
        raise
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"The embedding provider did not answer ({type(exc).__name__}).") from exc
    if len(vector) != dimension:
        raise EmbeddingError(f"The embedding provider returned {len(vector)} dimensions, expected {dimension}.")
    return vector


def _openai(api_key: str, model: str, dimension: int, text: str) -> list[float]:
    response = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "input": text or " ", "dimensions": dimension},
        timeout=30,
    )
    if response.status_code >= 400:
        raise EmbeddingError(f"The embedding provider returned HTTP {response.status_code}.")
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None
    if not data or not isinstance(data, list):
        raise EmbeddingError("The embedding provider returned an empty response.")
    vector = data[0].get("embedding") if isinstance(data[0], dict) else None
    if not isinstance(vector, list):
        raise EmbeddingError("The embedding provider returned an empty response.")
    return [float(value) for value in vector]


def _google(api_key: str, model: str, dimension: int, text: str) -> list[float]:
    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent",
        headers={"x-goog-api-key": api_key},
        json={
            "content": {"parts": [{"text": text or " "}]},
            "outputDimensionality": dimension,
        },
        timeout=30,
    )
    if response.status_code >= 400:
        raise EmbeddingError(f"The embedding provider returned HTTP {response.status_code}.")
    body = response.json()
    embedding = body.get("embedding") if isinstance(body, dict) else None
    values = embedding.get("values") if isinstance(embedding, dict) else None
    if not isinstance(values, list):
        raise EmbeddingError("The embedding provider returned an empty response.")
    return [float(value) for value in values]
