"""4-digit handover OTPs: salted hash for verification, lock-out after repeated failures."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from app.core import clock
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Pickup


def generate_code() -> str:
    return f"{secrets.randbelow(10000):04d}"


def hash_code(code: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()
    return f"{salt}${digest}"


def check_code(code: str, stored: str | None) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_code(code, salt), stored)


def is_locked(pickup: Pickup, now: datetime | None = None) -> bool:
    now = now or clock.now()
    return pickup.otp_locked_until is not None and pickup.otp_locked_until > now


def verify(pickup: Pickup, code: str, stored_hash: str | None, now: datetime | None = None) -> bool:
    """Check a code, tracking failures. Raises 423 when locked. Caller must commit on both outcomes."""
    now = now or clock.now()
    if is_locked(pickup, now):
        mins = max(1, round((pickup.otp_locked_until - now).total_seconds() / 60))
        raise AppError(423, "otp_locked", f"Too many wrong codes. Try again in about {mins} minute(s).")
    if check_code(code, stored_hash):
        pickup.otp_failed_attempts = 0
        pickup.otp_locked_until = None
        return True
    pickup.otp_failed_attempts += 1
    if pickup.otp_failed_attempts >= settings.OTP_MAX_ATTEMPTS:
        pickup.otp_locked_until = now + timedelta(minutes=settings.OTP_LOCK_MINUTES)
        pickup.otp_failed_attempts = 0
    return False
