"""APScheduler job that drives escalation, expiry, warnings and re-assignment."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.db.session import SessionLocal
from app.services import escalation

log = logging.getLogger("foodbridge.scheduler")


def tick() -> dict | None:
    """Run one cycle in its own transaction; never let an exception kill the scheduler."""
    try:
        with SessionLocal() as db:
            result = escalation.run_cycle(db)
            db.commit()
            return result
    except Exception:  # noqa: BLE001 - keep the scheduler alive
        log.exception("Scheduler tick failed")
        return None


def interval_seconds() -> float:
    """Real-time interval. With TIME_SCALE=60 a 30 s simulated cadence becomes 0.5 s of real time."""
    return max(0.5, settings.SCHEDULER_INTERVAL_SECONDS / max(1.0, settings.TIME_SCALE))


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(tick, "interval", seconds=interval_seconds(), id="foodbridge-cycle",
                  max_instances=1, coalesce=True, replace_existing=True)
    sched.start()
    log.info("Scheduler started (every %.1f real seconds, TIME_SCALE=%s)", interval_seconds(), settings.TIME_SCALE)
    return sched
