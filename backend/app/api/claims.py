"""Claim endpoints (FR-3): race-safe, idempotent claiming."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.deps import get_db, require_ngo, require_roles
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.db.models import Claim, FoodListing, ListingMatchScore, NgoProfile, User
from app.schemas.listings import ClaimIn
from app.services import lifecycle, matching
from app.services.audit import log_action
from app.services.notifier import notify
from app.services.serializers import listing_out, pickup_out

router = APIRouter(tags=["claims"])


def _claim_out(db: Session, claim: Claim, user: User, created: bool) -> dict:
    from app.db.models import Pickup

    pickup = db.scalar(select(Pickup).where(Pickup.claim_id == claim.id))
    listing = db.get(FoodListing, claim.listing_id)
    return {
        "claim_id": claim.id, "listing_id": claim.listing_id, "claimed_quantity": claim.claimed_quantity,
        "status": claim.status, "is_diversion": claim.is_diversion, "created": created,
        "listing": listing_out(db, listing, user), "pickup": pickup_out(db, pickup, user) if pickup else None,
    }


@router.post("/listings/{listing_id}/claim", status_code=201)
def claim_listing(listing_id: int, body: ClaimIn | None = None, user: User = Depends(require_ngo),
                  db: Session = Depends(get_db)):
    """First valid NGO wins. Idempotent: repeating the call returns the existing claim."""
    from fastapi.responses import JSONResponse
    from fastapi.encoders import jsonable_encoder

    prof: NgoProfile | None = user.ngo_profile
    if prof is None:
        raise bad_request("no_profile", "NGO profile missing.")
    if not user.is_verified:
        raise forbidden("Your organisation must be verified by an admin before it can claim food.")
    wanted = body.quantity if body else None

    for _attempt in range(3):  # retry only if we lost a race for part of the quantity
        now = clock.now()
        listing = db.get(FoodListing, listing_id, with_for_update=True)  # row lock on PostgreSQL
        if listing is None:
            raise not_found("Listing")
        db.refresh(listing)
        existing = db.scalar(select(Claim).where(
            Claim.listing_id == listing_id, Claim.ngo_id == user.id, Claim.status.in_(("active", "completed"))))
        if existing:
            return JSONResponse(status_code=200, content=jsonable_encoder(_claim_out(db, existing, user, False)))
        if listing.safe_until <= now or listing.status == "expired":
            raise conflict("listing_expired", "This food is past its safe-until time.")
        if listing.status != "open":
            raise conflict("already_claimed", "This listing has already been claimed or is no longer available.")
        score = db.scalar(select(ListingMatchScore).where(
            ListingMatchScore.listing_id == listing_id, ListingMatchScore.ngo_id == user.id,
            ListingMatchScore.notified_at.is_not(None)))
        if score is None:
            raise forbidden("This listing has not been offered to your organisation.")
        is_diversion = bool(prof.is_fallback_partner)
        if is_diversion and listing.escalation_level < 3:
            raise forbidden("Fallback partners can only claim listings that reached the final escalation level.")
        capacity = matching.remaining_capacity(db, prof, now)
        if capacity <= 0:
            raise conflict("no_capacity", "Your daily capacity is used up.")
        qty = min(wanted or listing.remaining_meals, listing.remaining_meals, capacity)
        if qty < 1:
            raise conflict("already_claimed", "Nothing left to claim on this listing.")
        res = db.execute(
            update(FoodListing)
            .where(FoodListing.id == listing_id, FoodListing.status == "open",
                   FoodListing.quantity_meals - FoodListing.claimed_meals >= qty)
            .values(claimed_meals=FoodListing.claimed_meals + qty)
            .execution_options(synchronize_session=False)
        )
        if res.rowcount == 1:
            break
        db.rollback()  # lost the race; re-read and try with what is left
    else:
        raise conflict("already_claimed", "Another organisation claimed this listing first.")

    db.refresh(listing)
    claim = Claim(listing_id=listing_id, ngo_id=user.id, claimed_quantity=qty, status="active",
                  claimed_at=now, is_diversion=is_diversion)
    db.add(claim)
    if listing.first_claimed_at is None:
        listing.first_claimed_at = now
    score.response = "accepted"
    prof.total_accepted += 1
    prof.acceptance_rate = round(prof.total_accepted / max(1, prof.total_claims), 4)
    db.flush()
    lifecycle.recompute_listing_status(db, listing)
    lifecycle.create_pickup(db, claim)
    notify(db, listing.donor_id, "claimed", "Your food was claimed",
           f"{prof.org_name} claimed {qty} meals of '{listing.title}'. A volunteer is being assigned.",
           data={"listing_id": listing.id, "claim_id": claim.id}, sms=True)
    log_action(db, user.id, "claim_listing", "listing", listing.id)
    db.commit()
    return _claim_out(db, claim, user, True)


@router.post("/claims/{claim_id}/cancel")
def cancel_claim(claim_id: int, user: User = Depends(require_roles("ngo", "admin")), db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise not_found("Claim")
    if user.role == "ngo" and claim.ngo_id != user.id:
        raise forbidden()
    lifecycle.cancel_claim(db, claim, user)
    log_action(db, user.id, "cancel_claim", "claim", claim.id)
    db.commit()
    return {"claim_id": claim.id, "status": claim.status}
