"""Audit log helper."""
from sqlalchemy.orm import Session

from app.db.models import AuditLog


def log_action(db: Session, actor_id: int | None, action: str, entity: str, entity_id: int | None = None) -> None:
    """Append an audit row (caller commits)."""
    db.add(AuditLog(actor_id=actor_id, action=action, entity=entity, entity_id=entity_id))
