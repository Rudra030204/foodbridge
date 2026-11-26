"""Notification service: in-app rows + mock SMS/WhatsApp adapters + realtime push."""
import logging

from sqlalchemy.orm import Session

from app.db.models import Notification, User
from app.services.realtime import queue_push

log = logging.getLogger("foodbridge.notifier")


class MockSmsAdapter:
    """Pretends to send an SMS: logs to console, the DB row is written by notify()."""

    prefix = "[MOCK SMS]"
    channel = "sms_mock"

    def send(self, phone: str | None, text: str) -> None:
        log.info("%s to=%s text=%s", self.prefix, phone or "n/a", text)


class MockWhatsAppAdapter(MockSmsAdapter):
    prefix = "[MOCK WHATSAPP]"
    channel = "whatsapp_mock"


_sms = MockSmsAdapter()
_wa = MockWhatsAppAdapter()


def notify(
    db: Session, user_id: int, type_: str, title: str, body: str, data: dict | None = None,
    sms: bool = False, whatsapp: bool = False,
) -> Notification:
    """Create an in-app notification (and optional mock SMS/WhatsApp copies); push over WebSocket after commit."""
    note = Notification(user_id=user_id, type=type_, title=title, body=body, channel="in_app", data=data)
    db.add(note)
    db.flush()
    if sms or whatsapp:
        user = db.get(User, user_id)
        phone = user.phone if user else None
        for adapter, wanted in ((_sms, sms), (_wa, whatsapp)):
            if wanted:
                adapter.send(phone, f"{title}: {body}")
                db.add(Notification(user_id=user_id, type=type_, title=title, body=body, channel=adapter.channel, data=data))
    queue_push(db, user_id, {
        "event": type_, "notification_id": note.id, "title": title, "body": body, "data": data or {},
    })
    return note
