"""WebSocket connection manager and post-commit push of notifications.

Notifications are queued on ``db.info['push']`` and only sent after the transaction commits,
so clients never receive events for data that was rolled back.
"""
import asyncio
import logging
from collections import defaultdict

from fastapi import WebSocket
from sqlalchemy import event
from sqlalchemy.orm import Session

log = logging.getLogger("foodbridge.realtime")


class ConnectionManager:
    def __init__(self) -> None:
        self._conns: dict[int, set[WebSocket]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._loop = asyncio.get_running_loop()
        self._conns[user_id].add(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        self._conns[user_id].discard(ws)
        if not self._conns[user_id]:
            self._conns.pop(user_id, None)

    def online_users(self) -> int:
        return len(self._conns)

    async def _send(self, user_id: int, payload: dict) -> None:
        for ws in list(self._conns.get(user_id, ())):
            try:
                await ws.send_json(payload)
            except Exception:  # connection died; drop it
                self.disconnect(user_id, ws)

    def push(self, user_id: int, payload: dict) -> None:
        """Thread-safe push from synchronous code. No-op if the user is offline."""
        if self._loop is None or user_id not in self._conns:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._send(user_id, payload), self._loop)
        except RuntimeError:  # loop closed
            log.debug("push skipped: event loop closed")


manager = ConnectionManager()


def queue_push(db: Session, user_id: int, payload: dict) -> None:
    db.info.setdefault("push", []).append((user_id, payload))


@event.listens_for(Session, "after_commit")
def _flush_pushes(session: Session) -> None:
    for user_id, payload in session.info.pop("push", []):
        manager.push(user_id, payload)


@event.listens_for(Session, "after_rollback")
def _drop_pushes(session: Session) -> None:
    session.info.pop("push", None)
