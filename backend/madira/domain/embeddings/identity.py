"""Which embedding model this process writes and reads.

Demo, tests, and CI stay on the local hasher. Live mode uses the venue's
configured provider. Anthropic has no embedding endpoint, so live Anthropic
keeps keyword search until the provider is OpenAI or Google.
"""

from __future__ import annotations

import os

from madira.llm_runtime import resolve_runtime

from madira.domain.embeddings.local import LOCAL_DIM, LOCAL_MODEL

_PROVIDER_MODELS = {
    "openai": ("text-embedding-3-small", 1536),
    "google_genai": ("gemini-embedding-001", 768),
}


def local_mode() -> bool:
    runtime = resolve_runtime()
    return bool(runtime.demo_mode) or not runtime.api_key


def identity() -> tuple[str, int] | None:
    """``(model name, dimension)`` or ``None`` when live embeddings are unavailable."""

    if local_mode():
        return LOCAL_MODEL, LOCAL_DIM
    runtime = resolve_runtime()
    chosen = _PROVIDER_MODELS.get(runtime.provider)
    if chosen is None:
        return None
    model, dimension = chosen
    override = os.environ.get("MADIRA_EMBEDDING_MODEL", "").strip()
    if override:
        model = override
    raw_dim = os.environ.get("MADIRA_EMBEDDING_DIMENSION", "").strip()
    if raw_dim:
        try:
            dimension = int(raw_dim)
        except ValueError:
            dimension = chosen[1]
    if dimension < 1 or dimension > 4096:
        dimension = chosen[1]
    return model, dimension
