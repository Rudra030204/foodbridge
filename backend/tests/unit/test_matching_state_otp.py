"""Unit tests: matching components, state machine, OTP lock-out."""
from datetime import datetime, timedelta

import pytest

from app.core.errors import AppError
from app.db.models import FoodListing, Pickup
from app.services import matching, otp
from app.services.state import can_transition, transition

NOW = datetime(2026, 6, 1, 6, 30)
BASE = dict(
    dist_km=2.0, safe_until=NOW + timedelta(hours=2.5), cooked_at=NOW, now=NOW, remaining_capacity=100,
    quantity=50, is_veg=True, accepts_veg=True, accepts_nonveg=True, total_claims=10, total_accepted=8,
)


def ev(**kw):
    return matching.evaluate_ngo(**{**BASE, **kw})


def test_distance_component():
    assert matching.distance_component(0, 12) == 1.0
    assert matching.distance_component(6, 12) == pytest.approx(0.5)
    assert matching.distance_component(20, 12) == 0.0


def test_closer_ngo_scores_higher_on_distance():
    assert ev(dist_km=1)["distance"] > ev(dist_km=5)["distance"]


def test_time_component_clamped_and_decreasing_with_travel():
    near, far = ev(dist_km=1)["time"], ev(dist_km=10)["time"]
    assert 0 <= far < near <= 1


def test_capacity_component():
    assert matching.capacity_component(100, 50) == 1.0
    assert matching.capacity_component(25, 50) == 0.5
    assert matching.capacity_component(0, 50) == 0.0


def test_history_component_laplace():
    assert matching.history_component(0, 0) == 0.5
    assert matching.history_component(10, 8) == pytest.approx(9 / 12)
    assert matching.history_component(1000, 0) < 0.01


def test_preference_exclusion_veg_and_nonveg():
    assert ev(is_veg=True, accepts_veg=False)["excluded"] == "food_type_not_accepted"
    assert ev(is_veg=False, accepts_nonveg=False)["excluded"] == "food_type_not_accepted"
    assert ev(is_veg=False, accepts_veg=False)["excluded"] is None


def test_excluded_when_too_far_out_of_time_or_no_capacity():
    assert ev(dist_km=13)["excluded"] == "too_far"
    assert ev(safe_until=NOW + timedelta(minutes=10), dist_km=8)["excluded"] == "cannot_arrive_in_time"
    assert ev(remaining_capacity=0)["excluded"] == "no_capacity_today"
    assert ev()["excluded"] is None


def test_weighted_score_matches_formula():
    comp = ev()
    w = matching.DEFAULT_WEIGHTS
    expected = (0.30 * comp["distance"] + 0.30 * comp["time"] + 0.20 * comp["capacity"]
                + 0.05 * comp["preference"] + 0.15 * comp["history"])
    assert matching.weighted_score(comp, w) == pytest.approx(expected, abs=1e-5)
    assert sum(w.values()) == pytest.approx(1.0)


def test_better_history_wins_all_else_equal():
    a = matching.weighted_score(ev(total_claims=10, total_accepted=9), matching.DEFAULT_WEIGHTS)
    b = matching.weighted_score(ev(total_claims=10, total_accepted=2), matching.DEFAULT_WEIGHTS)
    assert a > b


def test_safe_window_clamped():
    assert matching.safe_window_minutes(NOW + timedelta(minutes=5), NOW) == 30
    assert matching.safe_window_minutes(NOW + timedelta(days=90), NOW) == 1440


def test_operating_hours_including_overnight():
    noon, late = datetime(2026, 1, 1, 12, 0), datetime(2026, 1, 1, 23, 30)
    assert matching.is_open_at("06:00", "23:00", noon)
    assert not matching.is_open_at("06:00", "23:00", late)
    assert matching.is_open_at("20:00", "04:00", late)
    assert matching.is_open_at("00:00", "23:59", late)


# ---------------- state machine
@pytest.mark.parametrize("old,new,ok", [
    ("open", "claimed", True), ("open", "expired", True), ("open", "delivered", False),
    ("claimed", "assigned", True), ("assigned", "picked_up", True), ("picked_up", "delivered", True),
    ("picked_up", "cancelled", False), ("delivered", "cancelled", False), ("expired", "open", False),
    ("cancelled", "open", False), ("assigned", "claimed", True), ("open", "picked_up", False),
])
def test_transition_matrix(old, new, ok):
    assert can_transition(old, new) is ok


def test_illegal_transition_raises_409():
    listing = FoodListing(status="delivered")
    with pytest.raises(AppError) as e:
        transition(listing, "cancelled")
    assert e.value.status == 409 and e.value.code == "illegal_transition"
    listing = FoodListing(status="open")
    transition(listing, "claimed")
    assert listing.status == "claimed"


# ---------------- OTP
def test_otp_hash_verify_and_salt():
    h1, h2 = otp.hash_code("1234"), otp.hash_code("1234")
    assert h1 != h2  # per-code salt
    assert otp.check_code("1234", h1) and not otp.check_code("1235", h1)
    assert not otp.check_code("1234", None)
    assert len(otp.generate_code()) == 4


def test_otp_lockout_after_five_failures():
    p = Pickup(otp_failed_attempts=0, otp_locked_until=None)
    stored = otp.hash_code("4321")
    for _ in range(5):
        assert otp.verify(p, "0000", stored, NOW) is False
    assert otp.is_locked(p, NOW)
    with pytest.raises(AppError) as e:
        otp.verify(p, "4321", stored, NOW)  # even the right code is refused while locked
    assert e.value.status == 423
    later = NOW + timedelta(minutes=10, seconds=1)
    assert not otp.is_locked(p, later)
    assert otp.verify(p, "4321", stored, later) is True
    assert p.otp_failed_attempts == 0
