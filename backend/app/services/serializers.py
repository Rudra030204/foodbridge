"""Role-aware serialisation (privacy rules live here).

* Donor exact address/coordinates are hidden from NGOs until they hold an active/completed claim.
* Volunteers see the exact pickup location only once they accepted the pickup.
* Volunteer live location is shared with donor/NGO only during an active pickup.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.geo import area_cell, haversine_km
from app.db.models import Claim, FoodListing, ListingMatchScore, NgoProfile, Pickup, User, VolunteerProfile


def urgency(minutes_left: float) -> str:
    return "red" if minutes_left < 60 else "amber" if minutes_left < 120 else "green"


def _has_claim(db: Session, listing_id: int, ngo_id: int) -> Claim | None:
    return db.scalar(select(Claim).where(
        Claim.listing_id == listing_id, Claim.ngo_id == ngo_id, Claim.status.in_(("active", "completed"))))


def can_see_exact_location(db: Session, listing: FoodListing, viewer: User) -> bool:
    if viewer.role == "admin" or viewer.id == listing.donor_id:
        return True
    if viewer.role == "ngo":
        return _has_claim(db, listing.id, viewer.id) is not None
    if viewer.role == "volunteer":
        return db.scalar(
            select(Pickup.id).join(Claim, Claim.id == Pickup.claim_id).where(
                Claim.listing_id == listing.id, Pickup.volunteer_id == viewer.id,
                Pickup.status.in_(("assigned", "en_route", "picked_up", "delivered")))
        ) is not None
    return False


def listing_out(db: Session, listing: FoodListing, viewer: User) -> dict:
    now = clock.now()
    minutes_left = round(clock.minutes_between(now, listing.safe_until), 1)
    donor = db.get(User, listing.donor_id)
    exact = can_see_exact_location(db, listing, viewer)
    out = {
        "id": listing.id, "title": listing.title, "description": listing.description,
        "food_category": listing.food_category, "is_veg": listing.is_veg,
        "quantity_meals": listing.quantity_meals, "claimed_meals": listing.claimed_meals,
        "remaining_meals": listing.remaining_meals, "storage_condition": listing.storage_condition,
        "hot_day": listing.hot_day, "cooked_at": listing.cooked_at, "safe_until": listing.safe_until,
        "minutes_left": minutes_left, "urgency": urgency(minutes_left), "status": listing.status,
        "escalation_level": listing.escalation_level, "photo_url": listing.photo_url,
        "pickup_window_start": listing.pickup_window_start, "pickup_window_end": listing.pickup_window_end,
        "created_at": listing.created_at, "area_cell": area_cell(listing.lat, listing.lng),
        "donor_org": donor.donor_profile.org_name if donor and donor.donor_profile else None,
        "donor_verified": bool(donor and donor.is_verified), "exact_location": exact,
        "pickup_address": listing.pickup_address if exact else None,
        "lat": listing.lat if exact else round(listing.lat, 2),
        "lng": listing.lng if exact else round(listing.lng, 2),
        "donor_id": listing.donor_id if viewer.role in ("donor", "admin") else None,
    }
    if viewer.role == "ngo":
        score = db.scalar(select(ListingMatchScore).where(
            ListingMatchScore.listing_id == listing.id, ListingMatchScore.ngo_id == viewer.id))
        if score:
            out["my_match"] = {"score": score.score, "rank": score.rank, "distance_km": score.distance_km,
                               "components": score.components, "notified": score.notified_at is not None,
                               "response": score.response}
        claim = _has_claim(db, listing.id, viewer.id)
        out["my_claim_id"] = claim.id if claim else None
    return out


def pickup_out(db: Session, pickup: Pickup, viewer: User) -> dict:
    claim = db.get(Claim, pickup.claim_id)
    listing = db.get(FoodListing, claim.listing_id)
    ngo = db.get(User, claim.ngo_id)
    ngo_prof: NgoProfile | None = ngo.ngo_profile if ngo else None
    vol = db.get(User, pickup.volunteer_id) if pickup.volunteer_id else None
    active = pickup.status in ("assigned", "en_route", "picked_up")
    exact = viewer.role in ("admin", "donor") or (
        viewer.role == "ngo" and claim.ngo_id == viewer.id) or (
        viewer.role == "volunteer" and pickup.volunteer_id == viewer.id and pickup.status != "offered")
    out = {
        "id": pickup.id, "claim_id": claim.id, "status": pickup.status, "quantity": claim.claimed_quantity,
        "is_diversion": claim.is_diversion, "assigned_at": pickup.assigned_at, "picked_up_at": pickup.picked_up_at,
        "delivered_at": pickup.delivered_at, "checklist": pickup.checklist,
        "otp_locked_until": pickup.otp_locked_until, "route_id": pickup.route_id,
        "listing": {
            "id": listing.id, "title": listing.title, "status": listing.status, "safe_until": listing.safe_until,
            "minutes_left": round(clock.minutes_between(clock.now(), listing.safe_until), 1),
            "is_veg": listing.is_veg, "donor_id": listing.donor_id,
            "donor_org": listing.donor.donor_profile.org_name if listing.donor and listing.donor.donor_profile else None,
            "pickup_address": listing.pickup_address if exact else None,
            "lat": listing.lat if exact else round(listing.lat, 2),
            "lng": listing.lng if exact else round(listing.lng, 2),
            "pickup_window_end": listing.pickup_window_end,
        },
        "ngo": {"id": claim.ngo_id, "org_name": ngo_prof.org_name if ngo_prof else None,
                "address": ngo_prof.address if ngo_prof else None,
                "lat": ngo_prof.lat if ngo_prof else None, "lng": ngo_prof.lng if ngo_prof else None},
        "volunteer": None, "pickup_otp": None, "delivery_otp": None, "volunteer_location": None,
    }
    if vol and (pickup.status != "offered" or viewer.id == vol.id or viewer.role == "admin"):
        out["volunteer"] = {"id": vol.id, "name": vol.name, "phone": vol.phone}
    if viewer.role == "donor" and pickup.status in ("assigned", "en_route"):
        out["pickup_otp"] = pickup.pickup_otp_plain
    if viewer.role == "ngo" and pickup.status in ("assigned", "en_route", "picked_up"):
        out["delivery_otp"] = pickup.delivery_otp_plain
    if active and viewer.role in ("donor", "ngo") and vol and vol.volunteer_profile:
        vp: VolunteerProfile = vol.volunteer_profile
        out["volunteer_location"] = {"lat": vp.current_lat, "lng": vp.current_lng}
    if viewer.role in ("donor", "ngo", "volunteer") and pickup.status == "delivered":
        out["can_rate"] = True
    return out
