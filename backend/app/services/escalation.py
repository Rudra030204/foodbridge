"""Auto-escalation, expiry, expiry warnings and re-assignment (FR-4). Called by the scheduler.

Levels (minutes are simulated minutes since the listing was created, see core/clock + TIME_SCALE):
  L1 >= T1: radius 3 -> 6 km, notify the next-best NGOs
  L2 >= T2: radius 12 km, notify every eligible NGO
  L3 >= T3 or < 45 min of safe time left: offer to fallback compost / animal-feed partners
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.models import (
    Claim, EscalationEvent, FoodListing, ListingMatchScore, Pickup, SystemSetting,
)
from app.services import lifecycle, matching
from app.services.notifier import notify
from app.services.state import transition

log = logging.getLogger("foodbridge.escalation")
OPEN_LIKE = ("open", "claimed", "assigned", "diverted")


def target_level(age_min: float, minutes_left: float) -> int:
    """Escalation level a listing should be at, given its age and remaining safe time."""
    if age_min >= settings.ESC_T3_MIN or minutes_left < settings.ESC_MIN_TIME_LEFT_MIN:
        return 3
    if age_min >= settings.ESC_T2_MIN:
        return 2
    if age_min >= settings.ESC_T1_MIN:
        return 1
    return 0


def _apply_level(db: Session, listing: FoodListing, level: int, now: datetime) -> list[int]:
    if level in (1, 2):
        matching.rank_candidates(db, listing, now)  # refresh scores: time and capacity changed
    if level == 1:
        radius = settings.ESC_RADIUS_L1_KM
        ids = matching.notify_candidates(db, listing, radius, settings.TOP_N_NOTIFY, "Search radius widened.")
        reason = f"no claim after {settings.ESC_T1_MIN:g} min: radius {radius:g} km, next {settings.TOP_N_NOTIFY} NGOs"
    elif level == 2:
        radius = settings.ESC_RADIUS_L2_KM
        ids = matching.notify_candidates(db, listing, radius, None, "Urgent: still unclaimed.")
        reason = f"no claim after {settings.ESC_T2_MIN:g} min: radius {radius:g} km, all eligible NGOs"
    else:
        radius = 1000.0
        existing = {s.ngo_id for s in db.scalars(select(ListingMatchScore).where(ListingMatchScore.listing_id == listing.id))}
        for rank, c in enumerate(matching.rank_fallback_partners(db, listing, now), start=1):
            if c.ngo_id not in existing:
                db.add(ListingMatchScore(listing_id=listing.id, ngo_id=c.ngo_id, score=c.score, rank=1000 + rank,
                                         distance_km=c.distance_km, components=c.components))
        db.flush()
        ids = matching.notify_candidates(db, listing, radius, None, "Final diversion: compost / animal feed.")
        reason = "final level: diverted to compost / animal-feed partners"
        # Only fallback partners can be newly notified here; regular NGOs were covered by level 2.
    db.add(EscalationEvent(listing_id=listing.id, level=level, radius_km=radius, notified_ngo_ids=ids,
                           triggered_at=now, reason=reason))
    listing.escalation_level = level
    notify(db, listing.donor_id, "escalation", f"Escalation level {level}",
           f"'{listing.title}' is still unclaimed; {reason}.", data={"listing_id": listing.id, "level": level})
    return ids


def run_escalation(db: Session, now: datetime | None = None) -> dict:
    """Escalate unclaimed open listings. Each missing level is applied once, in order."""
    now = now or clock.now()
    escalated = 0
    listings = db.scalars(select(FoodListing).where(
        FoodListing.status == "open", FoodListing.safe_until > now)).all()
    for listing in listings:
        if listing.remaining_meals <= 0:
            continue
        age = clock.minutes_between(listing.created_at, now)
        left = clock.minutes_between(now, listing.safe_until)
        target = target_level(age, left)
        for level in range(listing.escalation_level + 1, target + 1):
            _apply_level(db, listing, level, now)
            escalated += 1
    return {"escalations": escalated, "checked": len(listings)}


def run_expiry(db: Session, now: datetime | None = None) -> dict:
    """Expire unclaimed listings past safe_until and fail stale, un-collected pickups."""
    now = now or clock.now()
    expired = failed = 0
    for listing in db.scalars(select(FoodListing).where(FoodListing.status == "open", FoodListing.safe_until <= now)):
        transition(listing, "expired")
        notify(db, listing.donor_id, "listing_expired", "Listing expired",
               f"'{listing.title}' passed its safe-until time without a full claim.", data={"listing_id": listing.id})
        expired += 1
    stale = db.execute(
        select(Pickup, Claim, FoodListing).join(Claim, Claim.id == Pickup.claim_id)
        .join(FoodListing, FoodListing.id == Claim.listing_id)
        .where(Pickup.status.in_(("pending_assignment", "offered", "assigned", "en_route")),
               FoodListing.safe_until <= now)
    ).all()
    for pickup, claim, listing in stale:
        pickup.status = "failed"
        pickup.pickup_otp_plain = pickup.delivery_otp_plain = None
        claim.status = "cancelled"
        listing.claimed_meals = max(0, listing.claimed_meals - claim.claimed_quantity)
        db.flush()
        lifecycle.recompute_listing_status(db, listing)
        if listing.status == "open":
            transition(listing, "expired")
        for uid in {listing.donor_id, claim.ngo_id}:
            notify(db, uid, "pickup_failed", "Pickup failed", f"'{listing.title}' expired before collection.",
                   data={"listing_id": listing.id, "pickup_id": pickup.id})
        failed += 1
    return {"expired": expired, "pickups_failed": failed}


def run_expiry_warnings(db: Session, now: datetime | None = None) -> int:
    """One warning per listing when <= 30 simulated minutes of safe time remain and it is not yet picked up."""
    now = now or clock.now()
    n = 0
    for listing in db.scalars(select(FoodListing).where(
            FoodListing.status.in_(OPEN_LIKE), FoodListing.expiry_warned.is_(False), FoodListing.safe_until > now)):
        if clock.minutes_between(now, listing.safe_until) <= settings.EXPIRY_WARNING_MIN:
            listing.expiry_warned = True
            targets = {listing.donor_id} | set(db.scalars(select(Claim.ngo_id).where(
                Claim.listing_id == listing.id, Claim.status == "active")))
            for uid in targets:
                notify(db, uid, "expiry_warning", "Food expires soon",
                       f"'{listing.title}' expires in about {round(clock.minutes_between(now, listing.safe_until))} minutes.",
                       data={"listing_id": listing.id})
            n += 1
    return n


def retry_assignments(db: Session) -> int:
    """Offer pickups that currently have no volunteer to whoever is available now."""
    n = 0
    for pickup in db.scalars(select(Pickup).where(Pickup.status == "pending_assignment")):
        if lifecycle.assign_volunteer(db, pickup):
            n += 1
    return n


def run_cycle(db: Session) -> dict:
    """One scheduler tick: expire, escalate, warn, re-assign; records a heartbeat for /admin/health."""
    now = clock.now()
    out = {**run_expiry(db, now), **run_escalation(db, now),
           "warnings": run_expiry_warnings(db, now), "reassigned": retry_assignments(db)}
    beat = {"last_run": now.isoformat(), "last_result": out}
    row = db.get(SystemSetting, "scheduler_status")
    if row is None:
        db.add(SystemSetting(key="scheduler_status", value=beat))
    else:
        row.value = beat
    if out["escalations"]:
        log.info("Escalation cycle: %s", out)
    return out
