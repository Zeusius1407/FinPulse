"""Optional background refresh.

When FINPULSE_ENABLE_SCHEDULER=1, the API spins up an APScheduler job that
re-ingests market data every FINPULSE_REFRESH_HOURS hours, so a long-running
host keeps its data fresh without an external cron. Off by default (ingestion
is usually driven by a separate cron / manual run instead).
"""
from __future__ import annotations

import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler

_scheduler: BackgroundScheduler | None = None


def _refresh_job() -> None:
    # Imported lazily so the API can start even if ingestion deps hiccup.
    from backend.ingest import run

    try:
        run()
    except Exception as exc:  # noqa: BLE001
        print(f"[scheduler] refresh failed: {exc}")


def maybe_start() -> None:
    global _scheduler
    if os.getenv("FINPULSE_ENABLE_SCHEDULER", "0") != "1":
        return
    if _scheduler is not None:
        return

    hours = float(os.getenv("FINPULSE_REFRESH_HOURS", "6"))
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_refresh_job, "interval", hours=hours, id="refresh")
    _scheduler.start()
    print(f"[scheduler] background refresh every {hours}h enabled")

    # Kick one refresh shortly after boot in a worker thread (non-blocking).
    threading.Timer(5.0, _refresh_job).start()


def shutdown() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
