"""Model tier for each specialist.

Every specialist is `fast` or `standard`. A tier's model id comes from
`MADIRA_LLM_MODEL_FAST` or `MADIRA_LLM_MODEL_STANDARD` when that variable is
set. Otherwise the tier uses the model `resolve_runtime` already chose, which
is the venue's saved model when Settings holds a key (P4-4) and the env model
otherwise. Unset tiers therefore match today's single model.

The provider and the API key always come from that runtime. A tier never
swaps in a different key.
"""

from __future__ import annotations

import os
from typing import Any

from madira.llm_runtime import LlmRuntime, resolve_runtime

TIERS = ("fast", "standard")

TIER_BY_SPECIALIST = {
    "head-sommelier": "standard",
    "menu-analyst": "standard",
    "pairing-sommelier": "standard",
    "list-curator": "fast",
    "inventory-purchasing": "fast",
    "staff-trainer": "fast",
    "supplier-scheduler": "fast",
    "buyer": "fast",
    "compliance-auditor": "fast",
}

_TIER_ENV = {
    "fast": "MADIRA_LLM_MODEL_FAST",
    "standard": "MADIRA_LLM_MODEL_STANDARD",
}


def tier_for(name: str) -> str:
    return TIER_BY_SPECIALIST.get(name, "standard")


def configured_model(tier: str, fallback: str) -> str:
    env_name = _TIER_ENV.get(tier, "")
    chosen = os.environ.get(env_name, "").strip() if env_name else ""
    return chosen or fallback


def model_for_specialist(name: str, runtime: LlmRuntime | None = None) -> str:
    """The model id a specialist run should meter and call."""

    runtime = runtime or resolve_runtime()
    if runtime.demo_mode:
        return "madira-demo-fixtures"
    return configured_model(tier_for(name), runtime.model)


def bind_chat_model(specialist: str) -> Any:
    """Live chat model for one specialist. The venue key stays on the runtime."""

    from langchain.chat_models import init_chat_model

    runtime = resolve_runtime()
    model_id = configured_model(tier_for(specialist), runtime.model)
    kwargs: dict[str, Any] = {}
    if runtime.api_key:
        kwargs["api_key"] = runtime.api_key
    return init_chat_model(f"{runtime.provider}:{model_id}", **kwargs)
