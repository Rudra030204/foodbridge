"""Seed 6 months of SYNTHETIC surplus history and ~120 historical listings with outcomes (idempotent)."""
import random
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Claim, FoodListing, NgoProfile, Pickup, SurplusHistory, SystemSetting, User, VolunteerProfile,
)
from app.services import prediction, safety

CATEGORY_MIX = [("cooked_meal", 0.58), ("bakery_dry", 0.10), ("dairy_paneer", 0.10), ("nonveg_cooked", 0.12),
                ("fruits_veg", 0.10)]
OUTCOMES = [("delivered", 0.66), ("diverted", 0.09), ("expired", 0.15), ("cancelled", 0.10)]


def _weighted(rng: random.Random, pairs):
    r, acc = rng.random(), 0.0
    for value, w in pairs:
        acc += w
        if r <= acc:
            return value
    return pairs[-1][0]


def seed_surplus_history(db: Session, days: int = 180, seed: int = 7) -> int:
    donors = db.execute(select(User).where(User.role == "donor", User.is_verified.is_(True))).scalars().all()
    spec = [(u.id, u.donor_profile.donor_type, prediction.donor_cell(u.donor_profile.lat, u.donor_profile.lng))
            for u in donors if u.donor_profile]
    end = (clock.now() - timedelta(days=1)).date()
    rows = prediction.generate_rows(spec, end, days=days, seed=seed)
    db.bulk_insert_mappings(SurplusHistory, [{**r, "is_synthetic": True} for r in rows])
    return len(rows)


def seed_historical_listings(db: Session, n: int = 120, seed: int = 11) -> int:
    rng = random.Random(seed)
    now = clock.now()
    donors = db.execute(select(User).where(User.role == "donor", User.is_verified.is_(True))).scalars().all()
    ngos = db.execute(select(NgoProfile).join(User, User.id == NgoProfile.user_id).where(
        User.is_verified.is_(True), NgoProfile.is_fallback_partner.is_(False))).scalars().all()
    fallbacks = db.execute(select(NgoProfile).where(NgoProfile.is_fallback_partner.is_(True))).scalars().all()
    vols = db.execute(select(VolunteerProfile)).scalars().all()
    created = 0
    for _ in range(n):
        donor = rng.choice(donors)
        dp = donor.donor_profile
        category = _weighted(rng, CATEGORY_MIX)
        storage = "room"
        created_at = now - timedelta(days=rng.uniform(1, 60), hours=rng.uniform(0, 5))
        cooked_at = created_at - timedelta(minutes=rng.uniform(5, 40))
        safe_until = safety.compute_safe_until(None, category, storage, cooked_at, hot_day=rng.random() < 0.15)
        if safe_until - created_at < timedelta(minutes=60):
            safe_until = created_at + timedelta(minutes=rng.uniform(70, 150))
        qty = rng.randint(10, 150)
        outcome = _weighted(rng, OUTCOMES)
        veg = category != "nonveg_cooked"
        listing = FoodListing(
            donor_id=donor.id, title=f"{dp.org_name} surplus {category.replace('_', ' ')}", food_category=category,
            is_veg=veg, quantity_meals=qty, claimed_meals=0, storage_condition=storage, cooked_at=cooked_at,
            safe_until=safe_until, pickup_address=dp.address, lat=dp.lat, lng=dp.lng,
            pickup_window_start=created_at, pickup_window_end=safe_until - timedelta(minutes=15),
            status="expired", escalation_level=3, created_at=created_at, expiry_warned=True)
        db.add(listing)
        db.flush()
        if outcome == "cancelled":
            listing.status, listing.escalation_level = "cancelled", 0
        elif outcome in ("delivered", "diverted"):
            diversion = outcome == "diverted" and bool(fallbacks)
            wait = rng.uniform(25, 45) if diversion else min(rng.expovariate(1 / 11.0), 28.0)
            level = 3 if diversion else (0 if wait < 10 else 1 if wait < 20 else 2)
            pool = [x for x in ngos if veg or x.accepts_nonveg] or ngos
            ngo = rng.choice(fallbacks) if diversion else rng.choice(pool)
            claimed_at = created_at + timedelta(minutes=wait)
            listing.status, listing.escalation_level = "delivered", level
            listing.claimed_meals, listing.first_claimed_at = qty, claimed_at
            claim = Claim(listing_id=listing.id, ngo_id=ngo.user_id, claimed_quantity=qty, status="completed",
                          claimed_at=claimed_at, is_diversion=diversion)
            db.add(claim)
            db.flush()
            pick_t = claimed_at + timedelta(minutes=rng.uniform(8, 25))
            db.add(Pickup(claim_id=claim.id, volunteer_id=rng.choice(vols).user_id, status="delivered",
                          assigned_at=claimed_at + timedelta(minutes=2), picked_up_at=pick_t,
                          delivered_at=pick_t + timedelta(minutes=rng.uniform(10, 30)), declined_by=[],
                          checklist={"food_covered": True, "container_clean": True, "temperature_ok": True},
                          created_at=claimed_at))
        created += 1
    return created


def seed_history(db: Session) -> dict:
    """Idempotent: a marker row prevents duplicate history on re-runs."""
    if db.get(SystemSetting, "history_seeded") is not None:
        return {"surplus_rows": 0, "history_listings": 0}
    surplus = seed_surplus_history(db)
    listings = seed_historical_listings(db)
    db.add(SystemSetting(key="history_seeded", value={"surplus_rows": surplus, "listings": listings, "synthetic": True}))
    db.flush()
    return {"surplus_rows": surplus, "history_listings": listings}
