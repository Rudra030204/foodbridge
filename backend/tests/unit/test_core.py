"""Unit tests: clock, geo, security, safety estimator."""
from datetime import datetime, timedelta

import pytest

from app.core import clock
from app.core.errors import AppError
from app.core.geo import area_cell, haversine_km, travel_minutes
from app.core.security import create_access_token, decode_token, hash_password, verify_password
from app.services import safety


def test_haversine_known_distance():
    # Delhi (28.6139, 77.2090) to Greater Noida (28.4744, 77.5040) is about 31-32 km
    d = haversine_km(28.6139, 77.2090, 28.4744, 77.5040)
    assert 30.0 < d < 34.0
    assert haversine_km(10, 10, 10, 10) == 0.0
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.3)


def test_haversine_symmetric():
    assert haversine_km(28.1, 77.1, 28.9, 77.9) == pytest.approx(haversine_km(28.9, 77.9, 28.1, 77.1))


def test_travel_minutes_and_cell():
    assert travel_minutes(25, 25) == pytest.approx(60)
    assert travel_minutes(5, 0) == float("inf")
    assert area_cell(28.47, 77.50) == area_cell(28.471, 77.501)
    assert area_cell(28.47, 77.50) != area_cell(28.60, 77.50)


def test_clock_freeze_and_advance():
    clock.freeze(datetime(2026, 1, 1, 12, 0))
    assert clock.now() == datetime(2026, 1, 1, 12, 0)
    clock.advance(minutes=15)
    assert clock.now() == datetime(2026, 1, 1, 12, 15)
    assert clock.minutes_between(datetime(2026, 1, 1, 12, 0), clock.now()) == 15
    clock.unfreeze()
    assert clock.now().year >= 2026


def test_clock_time_scale(monkeypatch):
    from app.core.config import settings

    clock.unfreeze()
    t0 = clock.now()
    monkeypatch.setattr(settings, "TIME_SCALE", 60.0)
    import time

    time.sleep(0.2)
    # 0.2 real seconds at 60x is at least ~6 simulated seconds more than at 1x
    assert (clock.now() - t0).total_seconds() > 5


def test_password_hash_roundtrip():
    h = hash_password("Secret123")
    assert h != "Secret123" and verify_password("Secret123", h)
    assert not verify_password("secret123", h)
    assert not verify_password("x", "not-a-hash")


def test_token_types_and_tamper():
    t = create_access_token(7, "donor")
    assert decode_token(t, "access")["sub"] == "7"
    assert decode_token(t, "refresh") is None
    assert decode_token(t + "x", "access") is None


# ---------------- Safety estimator ----------------
COOKED = datetime(2026, 5, 1, 12, 0)


def test_cooked_meal_room_applies_15_percent_buffer():
    su = safety.compute_safe_until(None, "cooked_meal", "room", COOKED)
    assert su == COOKED + timedelta(hours=3.0 * 0.85)


def test_hot_day_reduces_window():
    normal = safety.compute_safe_until(None, "cooked_meal", "room", COOKED)
    hot = safety.compute_safe_until(None, "cooked_meal", "room", COOKED, hot_day=True)
    assert hot < normal
    assert hot == COOKED + timedelta(hours=3.0 * 0.85 * 0.7)


@pytest.mark.parametrize("cat,storage,hours", [
    ("cooked_meal", "hot_holding", 5), ("cooked_meal", "refrigerated", 24), ("dairy_paneer", "room", 2),
    ("dairy_paneer", "refrigerated", 24), ("nonveg_cooked", "room", 2), ("nonveg_cooked", "refrigerated", 24),
    ("bakery_dry", "room", 24), ("fruits_veg", "room", 12),
])
def test_every_default_rule(cat, storage, hours):
    su = safety.compute_safe_until(None, cat, storage, COOKED)
    assert su == COOKED + timedelta(hours=hours * 0.85)


def test_sealed_uses_printed_expiry():
    exp = datetime(2026, 8, 1)
    assert safety.compute_safe_until(None, "sealed_packaged", "sealed_packaged", COOKED, expiry_at=exp) == exp


def test_sealed_requires_expiry_and_consistent_fields():
    with pytest.raises(AppError) as e:
        safety.compute_safe_until(None, "sealed_packaged", "sealed_packaged", COOKED)
    assert e.value.code == "expiry_required"
    with pytest.raises(AppError) as e:
        safety.compute_safe_until(None, "cooked_meal", "sealed_packaged", COOKED, expiry_at=COOKED)
    assert e.value.code == "invalid_storage"


def test_unsupported_combination():
    with pytest.raises(AppError) as e:
        safety.compute_safe_until(None, "bakery_dry", "hot_holding", COOKED)
    assert e.value.code == "unsupported_combination"


def test_db_rule_overrides_default(db):
    from app.db.models import FoodSafetyRule

    rule = db.query(FoodSafetyRule).filter_by(food_category="cooked_meal", storage_condition="room").one()
    rule.safe_hours = 1.0
    db.commit()
    su = safety.compute_safe_until(db, "cooked_meal", "room", COOKED)
    assert su == COOKED + timedelta(hours=0.85)


def test_check_rescuable_rejects_under_45_min():
    now = datetime(2026, 5, 1, 12, 0)
    assert safety.check_rescuable(now + timedelta(minutes=46), now) == pytest.approx(46)
    with pytest.raises(AppError) as e:
        safety.check_rescuable(now + timedelta(minutes=44), now)
    assert e.value.code == "too_close_to_expiry"
    with pytest.raises(AppError):
        safety.check_rescuable(now - timedelta(minutes=5), now)
