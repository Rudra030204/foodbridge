"""Claim -> volunteer -> pickup -> delivery lifecycle (FR-5/FR-6 core logic)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.errors import AppError, bad_request, conflict
from app.core.geo import haversine_km
from app.db.models import Claim, FoodListing, ListingMatchScore, NgoProfile, Pickup, User, VolunteerProfile
from app.services import otp as otp_service
from app.services.notifier import notify
from app.services.state import transition

ACTIVE_PICKUP = ("offered", "assigned", "en_route", "picked_up")
STAGE = {"pending_assignment": 0, "offered": 0, "assigned": 1, "en_route": 1, "picked_up": 2, "delivered": 3}
STAGE_TO_STATUS = {0: "claimed", 1: "assigned", 2: "picked_up", 3: "delivered"}


# ------------------------------------------------------------------ listing status
def recompute_listing_status(db: Session, listing: FoodListing) -> None:
    """Derive the listing status from its claims/pickups and apply it through the state machine."""
    if listing.status in ("cancelled", "expired"):
        return
    if listing.remaining_meals > 0:
        target = "open"
    else:
        rows = db.execute(
            select(Claim, Pickup).outerjoin(Pickup, Pickup.claim_id == Claim.id).where(
                Claim.listing_id == listing.id, Claim.status.in_(("active", "completed"))
            )
        ).all()
        if not rows:
            target = "open"
        else:
            stage = min(STAGE.get(p.status, 0) if p is not None else 0 for _c, p in rows)
            target = STAGE_TO_STATUS[stage]
            if stage == 0 and any(c.is_diversion for c, _p in rows):
                target = "diverted"
    if listing.status in ("claimed", "diverted") and target in ("claimed", "diverted"):
        listing.status = target  # claimed <-> diverted is a relabel, not a lifecycle step
        return
    if listing.status == "delivered":
        return
    transition(listing, target)


# ------------------------------------------------------------------ volunteer assignment
def _volunteer_load(db: Session, volunteer_id: int) -> int:
    rows = db.execute(
        select(Claim.claimed_quantity).join(Pickup, Pickup.claim_id == Claim.id).where(
            Pickup.volunteer_id == volunteer_id, Pickup.status.in_(ACTIVE_PICKUP)
        )
    ).all()
    return sum(r[0] for r in rows)


def pick_volunteer(db: Session, listing: FoodListing, quantity: int, excluded: list[int]) -> User | None:
    """Nearest available volunteer with enough spare vehicle capacity."""
    best, best_d = None, float("inf")
    # Volunteers already collecting nearby get priority so several claims share one route (batching).
    busy = db.execute(
        select(Pickup.volunteer_id, FoodListing.lat, FoodListing.lng)
        .join(Claim, Claim.id == Pickup.claim_id).join(FoodListing, FoodListing.id == Claim.listing_id)
        .where(Pickup.status.in_(("assigned", "en_route")))
    ).all()
    batch_ids = {vid for vid, lat, lng in busy
                 if haversine_km(lat, lng, listing.lat, listing.lng) <= settings.BATCH_RADIUS_KM}
    vols = db.execute(
        select(VolunteerProfile, User).join(User, User.id == VolunteerProfile.user_id).where(
            User.is_active.is_(True), VolunteerProfile.is_available.is_(True)
        )
    ).all()
    for prof, user in vols:
        if user.id in excluded or prof.capacity_meals < quantity + _volunteer_load(db, user.id):
            continue
        d = haversine_km(prof.current_lat, prof.current_lng, listing.lat, listing.lng)
        if user.id in batch_ids:
            d *= 0.5
        if d < best_d:
            best, best_d = user, d
    return best


def assign_volunteer(db: Session, pickup: Pickup) -> bool:
    """Offer ``pickup`` to the best volunteer. Returns True if an offer was made."""
    claim = db.get(Claim, pickup.claim_id)
    listing = db.get(FoodListing, claim.listing_id)
    vol = pick_volunteer(db, listing, claim.claimed_quantity, list(pickup.declined_by or []))
    if vol is None:
        pickup.status, pickup.volunteer_id = "pending_assignment", None
        return False
    pickup.volunteer_id, pickup.status = vol.id, "offered"
    notify(
        db, vol.id, "pickup_offer", "New pickup task",
        f"Pick up {claim.claimed_quantity} meals ({listing.title}). Please accept or decline.",
        data={"pickup_id": pickup.id, "listing_id": listing.id}, sms=True,
    )
    return True


def create_pickup(db: Session, claim: Claim) -> Pickup:
    pickup = Pickup(claim_id=claim.id, status="pending_assignment", declined_by=[])
    db.add(pickup)
    db.flush()
    assign_volunteer(db, pickup)
    return pickup


def _load(db: Session, pickup: Pickup) -> tuple[Claim, FoodListing]:
    claim = db.get(Claim, pickup.claim_id)
    return claim, db.get(FoodListing, claim.listing_id)


def accept_pickup(db: Session, pickup: Pickup, volunteer: User) -> Pickup:
    if pickup.volunteer_id != volunteer.id or pickup.status != "offered":
        raise conflict("not_offered", "This pickup is not currently offered to you.")
    claim, listing = _load(db, pickup)
    p_code, d_code = otp_service.generate_code(), otp_service.generate_code()
    pickup.pickup_otp_plain, pickup.delivery_otp_plain = p_code, d_code
    pickup.pickup_otp_hash, pickup.delivery_otp_hash = otp_service.hash_code(p_code), otp_service.hash_code(d_code)
    pickup.status, pickup.assigned_at = "assigned", clock.now()
    recompute_listing_status(db, listing)
    for uid, role_msg in ((listing.donor_id, "Share the pickup OTP with the volunteer on arrival."),
                          (claim.ngo_id, "Your delivery OTP is ready in the app.")):
        notify(db, uid, "volunteer_assigned", "Volunteer assigned",
               f"{volunteer.name} will collect '{listing.title}'. {role_msg}",
               data={"pickup_id": pickup.id, "listing_id": listing.id}, sms=True)
    return pickup


def decline_pickup(db: Session, pickup: Pickup, volunteer: User) -> Pickup:
    if pickup.volunteer_id != volunteer.id or pickup.status not in ("offered", "assigned"):
        raise conflict("cannot_decline", "You cannot decline this pickup now.")
    declined = list(pickup.declined_by or [])
    declined.append(volunteer.id)
    pickup.declined_by = declined
    pickup.volunteer_id, pickup.status = None, "pending_assignment"
    pickup.pickup_otp_hash = pickup.delivery_otp_hash = pickup.pickup_otp_plain = pickup.delivery_otp_plain = None
    claim, listing = _load(db, pickup)
    recompute_listing_status(db, listing)
    assign_volunteer(db, pickup)  # next-best volunteer; stays pending if nobody is left
    return pickup


def start_pickup(db: Session, pickup: Pickup, volunteer: User) -> Pickup:
    if pickup.volunteer_id != volunteer.id or pickup.status != "assigned":
        raise conflict("illegal_transition", f"Cannot start a pickup that is '{pickup.status}'.")
    pickup.status = "en_route"
    return pickup


REQUIRED_CHECKS = ("food_covered", "container_clean", "temperature_ok")


def verify_pickup_otp(db: Session, pickup: Pickup, volunteer: User, code: str, checklist: dict) -> Pickup:
    if pickup.volunteer_id != volunteer.id or pickup.status not in ("assigned", "en_route"):
        raise conflict("illegal_transition", f"Pickup is '{pickup.status}', not ready for pickup verification.")
    if not all(checklist.get(k) is True for k in REQUIRED_CHECKS):
        raise bad_request("checklist_incomplete", "All safety checklist items must be confirmed before pickup.")
    claim, listing = _load(db, pickup)
    now = clock.now()
    if now > listing.safe_until:
        _fail(db, pickup, claim, listing, "Food passed its safe-until time before pickup.")
        raise conflict("food_expired", "This food is past its safe-until time and cannot be collected.")
    if not otp_service.verify(pickup, code, pickup.pickup_otp_hash, now):
        db.commit()  # persist the failure counter / lock
        raise AppError(400, "invalid_otp", "Incorrect pickup OTP.")
    pickup.status, pickup.picked_up_at, pickup.checklist = "picked_up", now, {k: True for k in REQUIRED_CHECKS}
    pickup.pickup_otp_plain = None
    recompute_listing_status(db, listing)
    notify(db, claim.ngo_id, "picked_up", "Food picked up", f"'{listing.title}' is on its way to you.",
           data={"pickup_id": pickup.id, "listing_id": listing.id})
    return pickup


def verify_delivery_otp(db: Session, pickup: Pickup, volunteer: User, code: str) -> Pickup:
    if pickup.volunteer_id != volunteer.id or pickup.status != "picked_up":
        raise conflict("illegal_transition", f"Pickup is '{pickup.status}', not ready for delivery verification.")
    claim, listing = _load(db, pickup)
    now = clock.now()
    if not otp_service.verify(pickup, code, pickup.delivery_otp_hash, now):
        db.commit()
        raise AppError(400, "invalid_otp", "Incorrect delivery OTP.")
    pickup.status, pickup.delivered_at, pickup.delivery_otp_plain = "delivered", now, None
    claim.status = "completed"
    recompute_listing_status(db, listing)
    for uid in (listing.donor_id, claim.ngo_id, volunteer.id):
        notify(db, uid, "delivered", "Delivery complete",
               f"{claim.claimed_quantity} meals of '{listing.title}' delivered. Please rate your experience.",
               data={"pickup_id": pickup.id, "listing_id": listing.id})
    return pickup


def _fail(db: Session, pickup: Pickup, claim: Claim, listing: FoodListing, reason: str) -> None:
    pickup.status = "failed"
    pickup.pickup_otp_plain = pickup.delivery_otp_plain = None
    claim.status = "cancelled"
    listing.claimed_meals = max(0, listing.claimed_meals - claim.claimed_quantity)
    db.flush()
    for uid in (listing.donor_id, claim.ngo_id):
        notify(db, uid, "pickup_failed", "Pickup failed", reason, data={"pickup_id": pickup.id, "listing_id": listing.id})
    db.commit()  # keep the failure even though the request errors out
    recompute_listing_status(db, listing)
    if listing.status == "open" and clock.now() >= listing.safe_until:
        transition(listing, "expired")
    db.commit()


def cancel_claim(db: Session, claim: Claim, actor: User, reason: str = "cancelled by NGO") -> None:
    """Cancel an active claim before pick-up; the listing re-opens for other NGOs."""
    pickup = db.scalar(select(Pickup).where(Pickup.claim_id == claim.id))
    if claim.status != "active" or (pickup and pickup.status in ("picked_up", "delivered")):
        raise conflict("illegal_transition", "This claim can no longer be cancelled.")
    listing = db.get(FoodListing, claim.listing_id)
    claim.status = "cancelled"
    listing.claimed_meals = max(0, listing.claimed_meals - claim.claimed_quantity)
    score = db.scalar(select(ListingMatchScore).where(
        ListingMatchScore.listing_id == listing.id, ListingMatchScore.ngo_id == claim.ngo_id))
    if score:
        score.response = "declined"
    prof = db.get(NgoProfile, claim.ngo_id)
    if prof and prof.total_accepted > 0:
        prof.total_accepted -= 1
        prof.acceptance_rate = round(prof.total_accepted / max(1, prof.total_claims), 4)
    vol_id = None
    if pickup:
        vol_id = pickup.volunteer_id
        pickup.status = "cancelled"
        pickup.pickup_otp_plain = pickup.delivery_otp_plain = pickup.pickup_otp_hash = pickup.delivery_otp_hash = None
    db.flush()
    recompute_listing_status(db, listing)
    for uid in {listing.donor_id, vol_id} - {None, actor.id}:
        notify(db, uid, "claim_cancelled", "Claim cancelled", f"'{listing.title}': {reason}.",
               data={"listing_id": listing.id})
