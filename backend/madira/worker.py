"""Poll the job table.

Run: python -m madira.worker
One tick, enqueue only: python -m madira.worker schedule

The process polls with backoff, reclaims expired locks, and stops on SIGTERM
after the job it is already running. Demo mode does not need this process:
request handlers and the existing CLIs run due jobs inline.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
from datetime import timedelta

from madira.db import init_db
from madira.jobs.queue import claim_next, current_time, next_poll_delay
from madira.jobs.runner import perform
from madira.jobs.schedule import schedule_due
from madira.seed import seed
from madira.tenancy import demo_posture

_stop = threading.Event()


def request_stop() -> None:
    _stop.set()


def reset_stop() -> None:
    _stop.clear()


def stop_requested() -> bool:
    return _stop.is_set()


def install_stop_signals() -> None:
    signal.signal(signal.SIGTERM, lambda *_args: request_stop())


def worker_name() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"[:120]


def schedule_interval() -> int:
    raw = os.environ.get("MADIRA_JOB_SCHEDULE_SECONDS", "").strip()
    if not raw:
        return 3600
    try:
        value = int(raw)
    except ValueError:
        return 3600
    if value < 1:
        return 1
    return value


def serve(*, schedule: bool = True, poll_floor: float = 0.25) -> int:
    """Claim until SIGTERM. Finish the current job, then return."""

    reset_stop()
    init_db()
    if demo_posture():
        seed()
    name = worker_name()
    delay = poll_floor
    nxt = current_time()
    interval = schedule_interval()
    while not stop_requested():
        if schedule and current_time() >= nxt:
            schedule_due()
            nxt = current_time() + timedelta(seconds=interval)
        job_id = claim_next(name)
        if job_id is None:
            delay = next_poll_delay(delay, found=False, floor=poll_floor)
            if _stop.wait(delay):
                break
            continue
        delay = next_poll_delay(delay, found=True, floor=poll_floor)
        try:
            perform(job_id, name)
        except Exception:
            # perform already recorded the scrubbed error.
            continue
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["schedule"]):
        print("usage: python -m madira.worker [schedule]", file=sys.stderr)
        return 2
    init_db()
    if demo_posture():
        seed()
    if args == ["schedule"]:
        schedule_due()
        return 0
    install_stop_signals()
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
