"""Tiny in-memory sliding-window rate limiter (single-process deployment)."""
import threading
import time
from collections import defaultdict, deque

from app.core.errors import AppError

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def check(key: str, limit: int, window_seconds: float) -> None:
    """Record a hit for ``key``; raise 429 when more than ``limit`` hits fall in the window."""
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            raise AppError(429, "rate_limited", "Too many attempts. Please try again later.")
        q.append(now)


def reset(key: str | None = None) -> None:
    """Clear one key (or everything) - used by tests."""
    with _lock:
        if key is None:
            _hits.clear()
        else:
            _hits.pop(key, None)
