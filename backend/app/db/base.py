"""Declarative base and shared column helpers."""
from datetime import datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def utcnow() -> datetime:
    """Default factory for created_at columns (goes through the app clock)."""
    from app.core import clock

    return clock.now()
