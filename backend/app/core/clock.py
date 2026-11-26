"""Single source of time for the whole app.

Every module must call ``clock.now()`` instead of ``datetime.now()``.
Supports TIME_SCALE (accelerated simulated time) and test-time freezing/advancing.
All values are naive UTC datetimes.
"""
import time
from datetime import datetime, timedelta, timezone

from app.core.config import settings

_start_real = time.time()
_start_sim = datetime.now(timezone.utc).replace(tzinfo=None)
_frozen: datetime | None = None
_offset = timedelta(0)


def now() -> datetime:
    """Current (possibly scaled / frozen) naive-UTC time."""
    if _frozen is not None:
        return _frozen + _offset
    elapsed = (time.time() - _start_real) * settings.TIME_SCALE
    return _start_sim + timedelta(seconds=elapsed) + _offset


def real_now() -> datetime:
    """Real wall-clock naive-UTC time, never scaled. Used for JWT expiry and rate limits."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def freeze(at: datetime | None = None) -> None:
    """Freeze the clock (tests). Defaults to the current time."""
    global _frozen, _offset
    _frozen = at if at is not None else now()
    _offset = timedelta(0)


def advance(**kwargs) -> None:
    """Move the frozen clock (or shift the live clock) forward, e.g. advance(minutes=15)."""
    global _offset
    _offset += timedelta(**kwargs)


def unfreeze() -> None:
    """Return to live time and drop any advance offset."""
    global _frozen, _offset
    _frozen = None
    _offset = timedelta(0)


def minutes_between(a: datetime, b: datetime) -> float:
    """(b - a) in minutes."""
    return (b - a).total_seconds() / 60.0
