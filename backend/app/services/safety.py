"""Food safety window estimator (rule-based, transparent).

These are conservative heuristics for rescue prioritisation, NOT medical advice.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.errors import bad_request
from app.db.models import FoodSafetyRule

STORAGE_CONDITIONS = ("room", "hot_holding", "refrigerated", "sealed_packaged")
CATEGORIES = ("cooked_meal", "dairy_paneer", "nonveg_cooked", "bakery_dry", "fruits_veg", "sealed_packaged")

# (category, storage) -> (safe_hours, note)
DEFAULT_RULES: dict[tuple[str, str], tuple[float, str]] = {
    ("cooked_meal", "room"): (3.0, "Cooked rice/curry/dal at room temperature."),
    ("cooked_meal", "hot_holding"): (5.0, "Held above 60C."),
    ("cooked_meal", "refrigerated"): (24.0, "Cooled promptly and refrigerated."),
    ("dairy_paneer", "room"): (2.0, "Dairy / paneer dishes at room temperature."),
    ("dairy_paneer", "hot_holding"): (3.0, "Held above 60C."),
    ("dairy_paneer", "refrigerated"): (24.0, "Refrigerated."),
    ("nonveg_cooked", "room"): (2.0, "Cooked non-veg at room temperature."),
    ("nonveg_cooked", "hot_holding"): (3.0, "Held above 60C."),
    ("nonveg_cooked", "refrigerated"): (24.0, "Refrigerated."),
    ("bakery_dry", "room"): (24.0, "Bread, bakery items, dry snacks."),
    ("bakery_dry", "refrigerated"): (48.0, "Refrigerated bakery."),
    ("fruits_veg", "room"): (12.0, "Fruits and raw vegetables."),
    ("fruits_veg", "refrigerated"): (48.0, "Refrigerated produce."),
}
DISCLAIMER = "Conservative heuristic for rescue prioritisation; not medical advice."


def effective_safe_hours(rule_hours: float, hot_day: bool = False, buffer: float | None = None) -> float:
    """Apply the safety buffer (default 15%) and the hot-day reduction to a rule's hours."""
    buf = settings.SAFETY_BUFFER if buffer is None else buffer
    hours = rule_hours * (1.0 - buf)
    if hot_day:
        hours *= settings.HOT_DAY_FACTOR
    return hours


def lookup_rule_hours(db: Session | None, category: str, storage: str) -> float | None:
    """Hours for (category, storage): DB rule first (admin editable), then built-in default."""
    if db is not None:
        rule = db.scalar(
            select(FoodSafetyRule).where(
                FoodSafetyRule.food_category == category, FoodSafetyRule.storage_condition == storage
            )
        )
        if rule is not None:
            return rule.safe_hours
    default = DEFAULT_RULES.get((category, storage))
    return default[0] if default else None


def compute_safe_until(
    db: Session | None,
    category: str,
    storage: str,
    cooked_at: datetime,
    hot_day: bool = False,
    expiry_at: datetime | None = None,
) -> datetime:
    """Return the instant until which the food is considered safe to hand over."""
    if category == "sealed_packaged" or storage == "sealed_packaged":
        if category != "sealed_packaged" or storage != "sealed_packaged":
            raise bad_request("invalid_storage", "Sealed packaged food must use category and storage 'sealed_packaged'.")
        if expiry_at is None:
            raise bad_request("expiry_required", "Printed expiry date/time is required for sealed packaged food.")
        return expiry_at
    hours = lookup_rule_hours(db, category, storage)
    if hours is None:
        raise bad_request("unsupported_combination", f"No safety rule for '{category}' stored '{storage}'.")
    return cooked_at + timedelta(hours=effective_safe_hours(hours, hot_day))


def check_rescuable(safe_until: datetime, now: datetime | None = None) -> float:
    """Return minutes of safe time left; raise if below the minimum rescue window."""
    now = now or clock.now()
    left = clock.minutes_between(now, safe_until)
    if left < settings.MIN_SAFE_MINUTES:
        raise bad_request(
            "too_close_to_expiry",
            f"Only {max(0, round(left))} minutes of safe time left; at least {round(settings.MIN_SAFE_MINUTES)} "
            "minutes are needed to rescue this food in time.",
        )
    return left
