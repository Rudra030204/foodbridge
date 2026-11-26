"""Password hashing and JWT helpers."""
from datetime import datetime, timedelta, timezone

import secrets

import bcrypt
from jose import JWTError, jwt

from app.core import clock
from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def _epoch(dt: datetime) -> int:
    """Naive-UTC datetime -> unix epoch seconds."""
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def _make_token(sub: int, role: str, kind: str, expires: timedelta) -> str:
    payload = {"sub": str(sub), "role": role, "type": kind, "jti": secrets.token_hex(8), "exp": _epoch(clock.real_now() + expires)}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: int, role: str) -> str:
    return _make_token(user_id, role, "access", timedelta(minutes=settings.ACCESS_TOKEN_MINUTES))


def create_refresh_token(user_id: int, role: str) -> str:
    return _make_token(user_id, role, "refresh", timedelta(days=settings.REFRESH_TOKEN_DAYS))


def decode_token(token: str, expected_type: str = "access") -> dict | None:
    """Return the payload if valid, unexpired and of the expected type, else None.

    Expiry uses real wall-clock time (not the scaled simulation clock).
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
    except JWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    if payload.get("exp", 0) < _epoch(clock.real_now()):
        return None
    return payload
