"""Listing endpoints (FR-2, FR-3, FR-8)."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.deps import get_current_user, get_db, require_donor, require_roles
from app.core.errors import AppError, bad_request, conflict, forbidden, not_found
from app.core.geo import haversine_km
from app.db.models import Claim, EscalationEvent, FoodListing, ListingMatchScore, Pickup, ProblemReport, User
from app.schemas.listings import ListingCreate, ListingPatch, ReportIn, to_naive_utc
from app.services import matching, safety
from app.services.audit import log_action
from app.services.notifier import notify
from app.services.serializers import listing_out
from app.services.state import transition

router = APIRouter(prefix="/listings", tags=["listings"])


def _get_listing(db: Session, listing_id: int) -> FoodListing:
    listing = db.get(FoodListing, listing_id)
    if listing is None:
        raise not_found("Listing")
    return listing


def _assert_can_view(db: Session, listing: FoodListing, user: User) -> None:
    if user.role == "admin" or user.id == listing.donor_id:
        return
    if user.role == "ngo":
        score = db.scalar(select(ListingMatchScore).where(
            ListingMatchScore.listing_id == listing.id, ListingMatchScore.ngo_id == user.id,
            ListingMatchScore.notified_at.is_not(None)))
        mine = db.scalar(select(Claim.id).where(Claim.listing_id == listing.id, Claim.ngo_id == user.id))
        if score or mine:
            return
    if user.role == "volunteer":
        if db.scalar(select(Pickup.id).join(Claim, Claim.id == Pickup.claim_id).where(
                Claim.listing_id == listing.id, Pickup.volunteer_id == user.id)):
            return
    raise forbidden("You cannot view this listing.")


@router.post("", status_code=201)
def create_listing(body: ListingCreate, user: User = Depends(require_donor), db: Session = Depends(get_db)):
    now = clock.now()
    prof = user.donor_profile
    if prof is None:
        raise bad_request("no_profile", "Donor profile missing.")
    since = now - timedelta(hours=24)
    recent = db.scalar(select(func.count(FoodListing.id)).where(
        FoodListing.donor_id == user.id, FoodListing.created_at >= since)) or 0
    if recent >= settings.MAX_LISTINGS_PER_DAY:
        raise AppError(429, "listing_limit", f"Limit of {settings.MAX_LISTINGS_PER_DAY} listings per day reached.")

    cooked_at = body.cooked_at or now
    if cooked_at > now + timedelta(minutes=5):
        raise bad_request("cooked_in_future", "Cooked time cannot be in the future.")
    if now - cooked_at > timedelta(hours=72) and body.storage_condition != "sealed_packaged":
        raise bad_request("cooked_too_old", "Food cooked more than 72 hours ago cannot be listed.")
    safe_until = safety.compute_safe_until(db, body.food_category, body.storage_condition, cooked_at,
                                           body.hot_day, body.expiry_at)
    safety.check_rescuable(safe_until, now)

    w_start = body.pickup_window_start or now
    w_end = body.pickup_window_end or (safe_until - timedelta(minutes=15))
    if w_end <= w_start:
        raise bad_request("bad_window", "Pickup window end must be after its start.")
    if w_end > safe_until:
        raise bad_request("window_after_expiry", "Pickup window must end before the food's safe-until time.")

    listing = FoodListing(
        donor_id=user.id, title=body.title, description=body.description, food_category=body.food_category,
        is_veg=body.is_veg, quantity_meals=body.quantity_meals, storage_condition=body.storage_condition,
        hot_day=body.hot_day, cooked_at=cooked_at, expiry_at=body.expiry_at, safe_until=safe_until,
        pickup_address=body.pickup_address or prof.address,
        lat=body.lat if body.lat is not None else prof.lat, lng=body.lng if body.lng is not None else prof.lng,
        pickup_window_start=w_start, pickup_window_end=w_end, photo_url=body.photo_url, status="open",
        escalation_level=0, created_at=now,
    )
    db.add(listing)
    db.flush()
    cands = matching.rank_candidates(db, listing, now)
    notified = matching.notify_candidates(db, listing, settings.ESC_RADIUS_L0_KM, settings.TOP_N_NOTIFY,
                                          "Claim it before it expires.")
    db.add(EscalationEvent(listing_id=listing.id, level=0, radius_km=settings.ESC_RADIUS_L0_KM,
                           notified_ngo_ids=notified, triggered_at=now, reason="initial notification"))
    log_action(db, user.id, "create_listing", "listing", listing.id)
    db.commit()
    out = listing_out(db, listing, user)
    out["candidates_ranked"] = len(cands)
    out["notified_count"] = len(notified)
    return out


@router.get("")
def list_listings(
    status: str | None = None, veg: bool | None = None, near: str | None = Query(default=None, description="lat,lng"),
    radius_km: float | None = Query(default=None, gt=0, le=500), donor_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    q = select(FoodListing)
    if user.role == "donor":
        q = q.where(FoodListing.donor_id == user.id)
    elif user.role == "ngo":
        offered = select(ListingMatchScore.listing_id).where(
            ListingMatchScore.ngo_id == user.id, ListingMatchScore.notified_at.is_not(None))
        mine = select(Claim.listing_id).where(Claim.ngo_id == user.id)
        q = q.where(FoodListing.id.in_(offered.union(mine)))
    elif user.role == "volunteer":
        q = q.where(FoodListing.id.in_(
            select(Claim.listing_id).join(Pickup, Pickup.claim_id == Claim.id).where(Pickup.volunteer_id == user.id)))
    elif donor_id is not None:
        q = q.where(FoodListing.donor_id == donor_id)
    if status:
        q = q.where(FoodListing.status.in_([s.strip() for s in status.split(",")]))
    if veg is not None:
        q = q.where(FoodListing.is_veg.is_(veg))
    rows = db.scalars(q.order_by(FoodListing.created_at.desc())).all()
    if near:
        try:
            lat, lng = (float(x) for x in near.split(","))
        except ValueError:
            raise bad_request("bad_near", "near must be 'lat,lng'.")
        rows = [r for r in rows if radius_km is None or haversine_km(lat, lng, r.lat, r.lng) <= radius_km]
    items = [listing_out(db, r, user) for r in rows]
    if user.role == "ngo":  # best match first among open listings, then soonest-expiring
        items.sort(key=lambda i: (i["status"] != "open", -(i.get("my_match") or {}).get("score", 0), i["safe_until"]))
    total = len(items)
    return {"total": total, "items": items[offset:offset + limit]}


@router.get("/safety-estimate")
def safety_estimate(
    food_category: str, storage_condition: str, hot_day: bool = False, cooked_at: datetime | None = None,
    expiry_at: datetime | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Live preview for the donor form: when will this food stop being safe, and can it still be rescued?"""
    now = clock.now()
    cooked = to_naive_utc(cooked_at) or now
    try:
        safe_until = safety.compute_safe_until(db, food_category, storage_condition, cooked, hot_day, to_naive_utc(expiry_at))
    except AppError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message}
    left = clock.minutes_between(now, safe_until)
    rescuable = left >= settings.MIN_SAFE_MINUTES
    return {"ok": True, "safe_until": safe_until, "minutes_left": round(left, 1), "rescuable": rescuable,
            "message": None if rescuable else f"Only {max(0, round(left))} min of safe time left; at least "
                                              f"{round(settings.MIN_SAFE_MINUTES)} min are needed to rescue this food.",
            "disclaimer": safety.DISCLAIMER}


@router.get("/{listing_id}")
def get_listing(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = _get_listing(db, listing_id)
    _assert_can_view(db, listing, user)
    return listing_out(db, listing, user)


@router.patch("/{listing_id}")
def patch_listing(listing_id: int, body: ListingPatch, user: User = Depends(require_donor), db: Session = Depends(get_db)):
    listing = _get_listing(db, listing_id)
    if listing.donor_id != user.id:
        raise forbidden()
    if listing.status != "open" or listing.claimed_meals > 0:
        raise conflict("not_editable", "Only unclaimed open listings can be edited.")
    data = body.model_dump(exclude_unset=True)
    for key in ("title", "description", "photo_url"):
        if key in data:
            setattr(listing, key, data[key])
    if data.get("quantity_meals") is not None:
        listing.quantity_meals = data["quantity_meals"]
    start = data.get("pickup_window_start") or listing.pickup_window_start
    end = data.get("pickup_window_end") or listing.pickup_window_end
    if end <= start or end > listing.safe_until:
        raise bad_request("bad_window", "Pickup window must be valid and end before safe-until.")
    listing.pickup_window_start, listing.pickup_window_end = start, end
    log_action(db, user.id, "edit_listing", "listing", listing.id)
    db.commit()
    return listing_out(db, listing, user)


@router.post("/{listing_id}/cancel")
def cancel_listing(listing_id: int, user: User = Depends(require_roles("donor", "admin")), db: Session = Depends(get_db)):
    listing = _get_listing(db, listing_id)
    if user.role == "donor" and listing.donor_id != user.id:
        raise forbidden()
    transition(listing, "cancelled")  # 409 if delivered / picked up / expired
    claims = db.scalars(select(Claim).where(Claim.listing_id == listing.id, Claim.status == "active")).all()
    for c in claims:
        c.status = "cancelled"
        p = db.scalar(select(Pickup).where(Pickup.claim_id == c.id))
        vol_id = p.volunteer_id if p else None
        if p:
            p.status = "cancelled"
            p.pickup_otp_plain = p.delivery_otp_plain = p.pickup_otp_hash = p.delivery_otp_hash = None
        for uid in {c.ngo_id, vol_id} - {None}:
            notify(db, uid, "listing_cancelled", "Listing cancelled", f"'{listing.title}' was cancelled by the donor.",
                   data={"listing_id": listing.id})
    log_action(db, user.id, "cancel_listing", "listing", listing.id)
    db.commit()
    return listing_out(db, listing, user)


@router.get("/{listing_id}/matches")
def listing_matches(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ranked NGOs with component breakdown ("why ranked"). NGOs only see their own row."""
    listing = _get_listing(db, listing_id)
    if user.role not in ("admin", "ngo") and user.id != listing.donor_id:
        raise forbidden()
    q = select(ListingMatchScore, User).join(User, User.id == ListingMatchScore.ngo_id).where(
        ListingMatchScore.listing_id == listing_id).order_by(ListingMatchScore.rank)
    if user.role == "ngo":
        q = q.where(ListingMatchScore.ngo_id == user.id)
    return {"weights": matching.get_weights(db), "matches": [
        {"ngo_id": s.ngo_id, "org_name": u.ngo_profile.org_name if u.ngo_profile else u.name, "rank": s.rank,
         "score": s.score, "distance_km": s.distance_km, "components": s.components,
         "notified": s.notified_at is not None, "response": s.response}
        for s, u in db.execute(q).all()]}


@router.post("/{listing_id}/report", status_code=201)
def report_problem(listing_id: int, body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = _get_listing(db, listing_id)
    _assert_can_view(db, listing, user)
    rep = ProblemReport(listing_id=listing.id, reporter_id=user.id, reason=body.reason, details=body.details)
    db.add(rep)
    log_action(db, user.id, "report_problem", "listing", listing.id)
    db.commit()
    return {"id": rep.id, "status": rep.status}
