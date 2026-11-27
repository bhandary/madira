"""Build each venue's briefing for the local service date.

Run: python -m madira.workers.briefings

Inline mode (demo, and tests) runs the jobs before returning. Otherwise the
rows stay queued for ``python -m madira.worker``.
"""

from __future__ import annotations

from madira.db import init_db
from madira.jobs.runner import inline_enabled
from madira.jobs.schedule import enqueue_briefings, run_ids
from madira.seed import seed
from madira.tenancy import demo_posture


def main() -> int:
    init_db()
    if demo_posture():
        seed()
    ids = enqueue_briefings()
    if inline_enabled():
        failed = run_ids(ids)
        return 1 if failed else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
