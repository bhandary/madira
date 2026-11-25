"""Pull POS sales for every venue with an active register.

Run: python -m madira.pos sync
"""

from __future__ import annotations

import sys

from madira.db import init_db
from madira.domain.pos.service import sync_all
from madira.seed import seed
from madira.tenancy import demo_posture


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["sync"]:
        print("usage: python -m madira.pos sync", file=sys.stderr)
        return 2
    init_db()
    if demo_posture():
        seed()
    failures = sync_all()
    if failures:
        print(f"POS sync failed for {failures} venue(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
