from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MADIRA_DATA_DIR", ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Default LLM: OpenAI gpt-4.1-mini. Override with MADIRA_LLM_PROVIDER / MADIRA_LLM_MODEL.
LLM_PROVIDER = os.environ.get("MADIRA_LLM_PROVIDER", "openai")
LLM_MODEL = os.environ.get("MADIRA_LLM_MODEL", "gpt-4.1-mini")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
MADIRA_API_KEY = os.environ.get("MADIRA_API_KEY", "")


def _has_provider_key() -> bool:
    provider = LLM_PROVIDER.lower()
    if provider in {"openai", "azure"}:
        return bool(OPENAI_API_KEY or MADIRA_API_KEY)
    if provider in {"anthropic"}:
        return bool(ANTHROPIC_API_KEY or MADIRA_API_KEY)
    if provider in {"google", "google_genai", "gemini"}:
        return bool(GOOGLE_API_KEY or MADIRA_API_KEY)
    return bool(MADIRA_API_KEY or OPENAI_API_KEY or ANTHROPIC_API_KEY)


_demo_flag = os.environ.get("MADIRA_DEMO_MODE", "").strip().lower()
if _demo_flag in {"0", "false", "no", "off"}:
    DEMO_MODE = False
elif _demo_flag in {"1", "true", "yes", "on"}:
    DEMO_MODE = True
else:
    DEMO_MODE = not _has_provider_key()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{(DATA_DIR / 'madira.db').as_posix()}",
)

FRONTEND_ORIGIN = os.environ.get("MADIRA_FRONTEND_ORIGIN", "http://localhost:3000")
HOST = os.environ.get("MADIRA_HOST", "0.0.0.0")
PORT = int(os.environ.get("MADIRA_PORT", "8123"))

CATALOG_ID = "madira://beverage-catalog"


def status_payload() -> dict:
    return {
        "app": "madira",
        "demo_mode": DEMO_MODE,
        "llm_provider": LLM_PROVIDER,
        "llm_model": "madira-demo-fixtures" if DEMO_MODE else LLM_MODEL,
        "database": "postgres" if DATABASE_URL.startswith("postgres") else "sqlite",
        "label": "DEMO MODE — deterministic fixtures, no API key"
        if DEMO_MODE
        else f"LIVE — {LLM_PROVIDER}:{LLM_MODEL}",
    }
