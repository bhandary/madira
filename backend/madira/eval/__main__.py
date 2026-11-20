"""Run the extraction and pairing evals.

Demo mode is the default and does not call a provider. ``--live`` uses the
configured model when ``OPENAI_API_KEY`` is set, and skips with a message
when it is not. Live mode never substitutes fixture dishes or fixture copy.
"""

from __future__ import annotations

import os
import sys
import tempfile


_PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "MADIRA_API_KEY",
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    live = "--live" in args
    if live:
        flag = os.environ.get("MADIRA_DEMO_MODE", "").strip().lower()
        if flag in {"1", "true", "yes", "on"}:
            print("Live eval refused: MADIRA_DEMO_MODE is on, so extraction would use fixtures.")
            return 1
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            print("Live eval skipped: OPENAI_API_KEY is not set.")
            return 0
        os.environ.pop("MADIRA_DEMO_MODE", None)
    else:
        for name in _PROVIDER_KEYS:
            os.environ.pop(name, None)
        os.environ["MADIRA_DEMO_MODE"] = "true"

    tmp = tempfile.mkdtemp(prefix="madira-eval-")
    os.environ["MADIRA_DATA_DIR"] = tmp
    os.environ["MADIRA_STORAGE_DIR"] = os.path.join(tmp, "storage")
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "madira.db")

    from madira.eval.runner import run

    return run(live=live)


if __name__ == "__main__":
    sys.exit(main())
