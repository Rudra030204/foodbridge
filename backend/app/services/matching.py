"""Multi-factor NGO matching engine (FR-3).

score = w_distance*distance + w_time*time_left + w_capacity*capacity + w_preference*preference + w_history*history
Each component is in [0, 1]; the breakdown is stored so the UI can explain "why ranked".
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.geo import haversine_km, travel_minutes
from app.db.models import Claim, FoodListing, ListingMatchScore, NgoProfile, SystemSetting, User
from app.services.notifier import notify

DEFAULT_WEIGHTS = {"distance": 0.30, "time": 0.30, "capacity": 0.20, "preference": 0.05, "history": 0.15}
WEIGHT_KEYS = tuple(DEFAULT_WEIGHTS)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ------------------------------------------------------------------ pure scoring
def is_open_at(start: str, end: str, local_dt: datetime) -> bool:
    """True if ``local_dt``'s time-of-day is within [start, end] ('HH:MM'); handles overnight windows."""
    hm = local_dt.strftime("%H:%M")
    if start <= end:
        return start <= hm <= end
    return hm >= start or hm <= end


def history_component(total_claims: int, total_accepted: int) -> float:
    """Laplace-smoothed acceptance rate."""
    return (total_accepted + 1) / (total_claims + 2)


def capacity_component(remaining_capacity: int, quantity: int) -> float:
    if remaining_capacity <= 0 or quantity <= 0:
        return 0.0
    return min(1.0, remaining_capacity / quantity)


def distance_component(dist_km: float, max_radius_km: float) -> float:
    return max(0.0, 1.0 - dist_km / max_radius_km)


def time_component(minutes_left_after_travel: float, safe_window_min: float) -> float:
    return clamp(minutes_left_after_travel / safe_window_min)


def safe_window_minutes(safe_until: datetime, cooked_at: datetime) -> float:
    """Total safe window, clamped to [30 min, 24 h] so very long shelf lives do not flatten the time score."""
    return clamp((safe_until - cooked_at).total_seconds() / 60.0, 30.0, 1440.0)


def evaluate_ngo(
    *, dist_km: float, safe_until: datetime, cooked_at: datetime, now: datetime, remaining_capacity: int,
    quantity: int, is_veg: bool, accepts_veg: bool, accepts_nonveg: bool, total_claims: int, total_accepted: int,
    max_radius_km: float | None = None, speed_kmph: float | None = None,
) -> dict:
    """Score one NGO for one listing. Returns components plus ``excluded`` (reason string or None)."""
    max_r = max_radius_km if max_radius_km is not None else settings.MAX_RADIUS_KM
    speed = speed_kmph if speed_kmph is not None else settings.AVG_SPEED_KMPH
    travel = travel_minutes(dist_km, speed)
    left_after = clock.minutes_between(now, safe_until) - travel
    out = {
        "distance": distance_component(dist_km, max_r),
        "time": time_component(left_after, safe_window_minutes(safe_until, cooked_at)),
        "capacity": capacity_component(remaining_capacity, quantity),
        "preference": 1.0,
        "history": history_component(total_claims, total_accepted),
        "travel_minutes": round(travel, 1),
        "excluded": None,
    }
    if (is_veg and not accepts_veg) or (not is_veg and not accepts_nonveg):
        out["preference"], out["excluded"] = 0.0, "food_type_not_accepted"
    elif dist_km > max_r:
        out["excluded"] = "too_far"
    elif left_after <= 0:
        out["excluded"] = "cannot_arrive_in_time"
    elif remaining_capacity <= 0:
        out["excluded"] = "no_capacity_today"
    return out


def weighted_score(components: dict, weights: dict) -> float:
    return round(sum(weights[k] * components[k] for k in WEIGHT_KEYS), 6)


# ------------------------------------------------------------------ DB helpers
def get_weights(db: Session) -> dict:
    row = db.get(SystemSetting, "match_weights")
    w = dict(DEFAULT_WEIGHTS)
    if row:
        w.update({k: float(v) for k, v in row.value.items() if k in WEIGHT_KEYS})
    return w


def local_day_start_utc(now: datetime) -> datetime:
    off = timedelta(minutes=settings.LOCAL_TZ_OFFSET_MIN)
    return (now + off).replace(hour=0, minute=0, second=0, microsecond=0) - off


def capacity_used_today(db: Session, now: datetime) -> dict[int, int]:
    rows = db.execute(
        select(Claim.ngo_id, func.sum(Claim.claimed_quantity))
        .where(Claim.status.in_(("active", "completed")), Claim.claimed_at >= local_day_start_utc(now))
        .group_by(Claim.ngo_id)
    ).all()
    return {ngo_id: int(total or 0) for ngo_id, total in rows}


def remaining_capacity(db: Session, ngo: NgoProfile, now: datetime | None = None) -> int:
    now = now or clock.now()
    used = capacity_used_today(db, now).get(ngo.user_id, 0)
    return max(0, ngo.daily_capacity_meals - used)


@dataclass
class Candidate:
    ngo_id: int
    score: float
    components: dict
    distance_km: float


def _eligible_ngos(db: Session, fallback: bool):
    return db.execute(
        select(NgoProfile, User).join(User, User.id == NgoProfile.user_id).where(
            User.role == "ngo", User.is_verified.is_(True), User.is_active.is_(True),
            NgoProfile.is_fallback_partner.is_(fallback),
        )
    ).all()


def rank_candidates(db: Session, listing: FoodListing, now: datetime | None = None, persist: bool = True) -> list[Candidate]:
    """Rank all eligible regular NGOs for a listing (best first) and persist the scores."""
    now = now or clock.now()
    weights = get_weights(db)
    used = capacity_used_today(db, now)
    local = now + timedelta(minutes=settings.LOCAL_TZ_OFFSET_MIN)
    qty = max(1, listing.remaining_meals)
    cands: list[Candidate] = []
    for prof, _user in _eligible_ngos(db, fallback=False):
        if not is_open_at(prof.operating_start, prof.operating_end, local):
            continue
        dist = haversine_km(listing.lat, listing.lng, prof.lat, prof.lng)
        comp = evaluate_ngo(
            dist_km=dist, safe_until=listing.safe_until, cooked_at=listing.cooked_at, now=now,
            remaining_capacity=max(0, prof.daily_capacity_meals - used.get(prof.user_id, 0)), quantity=qty,
            is_veg=listing.is_veg, accepts_veg=prof.accepts_veg, accepts_nonveg=prof.accepts_nonveg,
            total_claims=prof.total_claims, total_accepted=prof.total_accepted,
        )
        if comp["excluded"]:
            continue
        cands.append(Candidate(prof.user_id, weighted_score(comp, weights), comp, round(dist, 3)))
    cands.sort(key=lambda c: (-c.score, c.distance_km, c.ngo_id))
    if persist:
        _persist(db, listing, cands)
    return cands


def _persist(db: Session, listing: FoodListing, cands: list[Candidate]) -> None:
    existing = {s.ngo_id: s for s in db.scalars(select(ListingMatchScore).where(ListingMatchScore.listing_id == listing.id))}
    for rank, c in enumerate(cands, start=1):
        row = existing.get(c.ngo_id)
        if row is None:
            db.add(ListingMatchScore(listing_id=listing.id, ngo_id=c.ngo_id, score=c.score, rank=rank,
                                     distance_km=c.distance_km, components=c.components))
        else:
            row.score, row.rank, row.distance_km, row.components = c.score, rank, c.distance_km, c.components
    db.flush()


def notify_candidates(db: Session, listing: FoodListing, radius_km: float, limit: int | None, reason: str) -> list[int]:
    """Notify the next-best un-notified NGOs inside ``radius_km``. Returns the NGO ids notified."""
    rows = db.scalars(
        select(ListingMatchScore).where(
            ListingMatchScore.listing_id == listing.id, ListingMatchScore.notified_at.is_(None),
            ListingMatchScore.distance_km <= radius_km,
        ).order_by(ListingMatchScore.rank)
    ).all()
    if limit is not None:
        rows = rows[:limit]
    now = clock.now()
    ids: list[int] = []
    for row in rows:
        row.notified_at = now
        prof = db.get(NgoProfile, row.ngo_id)
        if prof:
            prof.total_claims += 1  # "offers received"; acceptance_rate = accepted / offered
            prof.acceptance_rate = round(prof.total_accepted / max(1, prof.total_claims), 4)
        notify(
            db, row.ngo_id, "listing_match", "New surplus food near you",
            f"{listing.quantity_meals} meals of {listing.title} ({row.distance_km:.1f} km away). {reason}",
            data={"listing_id": listing.id, "rank": row.rank, "score": row.score}, sms=True,
        )
        ids.append(row.ngo_id)
    db.flush()
    return ids


def rank_fallback_partners(db: Session, listing: FoodListing, now: datetime | None = None) -> list[Candidate]:
    """Fallback (compost / animal-feed) partners, nearest first. No time-window exclusion: food is near expiry."""
    now = now or clock.now()
    used = capacity_used_today(db, now)
    cands = []
    for prof, _user in _eligible_ngos(db, fallback=True):
        if used.get(prof.user_id, 0) >= prof.daily_capacity_meals:
            continue
        dist = haversine_km(listing.lat, listing.lng, prof.lat, prof.lng)
        comp = {"distance": distance_component(dist, 100.0), "time": 0.0, "capacity": 1.0, "preference": 1.0,
                "history": history_component(prof.total_claims, prof.total_accepted), "excluded": None,
                "travel_minutes": round(travel_minutes(dist, settings.AVG_SPEED_KMPH), 1), "fallback": True}
        cands.append(Candidate(prof.user_id, round(comp["distance"], 6), comp, round(dist, 3)))
    cands.sort(key=lambda c: (-c.score, c.distance_km))
    return cands
