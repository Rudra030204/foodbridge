"""Pickup endpoints (FR-5, FR-6): offer/accept/decline, OTP verification, volunteer status."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_volunteer
from app.core.errors import forbidden, not_found
from app.db.models import Claim, FoodListing, Pickup, Route, User
from app.schemas.listings import OtpIn, PickupVerifyIn
from app.services import lifecycle
from app.services.routing import plan_route_for_volunteer
from app.services.audit import log_action
from app.services.serializers import pickup_out

router = APIRouter(prefix="/pickups", tags=["pickups"])


def _get_pickup(db: Session, pickup_id: int) -> Pickup:
    p = db.get(Pickup, pickup_id)
    if p is None:
        raise not_found("Pickup")
    return p


def _assert_participant(db: Session, pickup: Pickup, user: User) -> None:
    claim = db.get(Claim, pickup.claim_id)
    listing = db.get(FoodListing, claim.listing_id)
    ok = (user.role == "admin" or pickup.volunteer_id == user.id or claim.ngo_id == user.id
          or listing.donor_id == user.id)
    if not ok:
        raise forbidden("You are not part of this pickup.")


@router.get("/mine")
def my_pickups(status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(Pickup).join(Claim, Claim.id == Pickup.claim_id).join(FoodListing, FoodListing.id == Claim.listing_id)
    if user.role == "volunteer":
        q = q.where(Pickup.volunteer_id == user.id)
    elif user.role == "ngo":
        q = q.where(Claim.ngo_id == user.id)
    elif user.role == "donor":
        q = q.where(FoodListing.donor_id == user.id)
    if status:
        q = q.where(Pickup.status.in_([s.strip() for s in status.split(",")]))
    rows = db.scalars(q.order_by(Pickup.created_at.desc())).all()
    return {"total": len(rows), "items": [pickup_out(db, p, user) for p in rows]}


@router.get("/{pickup_id}")
def get_pickup(pickup_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _get_pickup(db, pickup_id)
    _assert_participant(db, p, user)
    return pickup_out(db, p, user)


@router.post("/{pickup_id}/accept")
def accept(pickup_id: int, user: User = Depends(require_volunteer), db: Session = Depends(get_db)):
    p = lifecycle.accept_pickup(db, _get_pickup(db, pickup_id), user)
    plan_route_for_volunteer(db, user.id)
    log_action(db, user.id, "accept_pickup", "pickup", p.id)
    db.commit()
    return pickup_out(db, p, user)


@router.post("/{pickup_id}/decline")
def decline(pickup_id: int, user: User = Depends(require_volunteer), db: Session = Depends(get_db)):
    p = lifecycle.decline_pickup(db, _get_pickup(db, pickup_id), user)
    plan_route_for_volunteer(db, user.id)
    log_action(db, user.id, "decline_pickup", "pickup", p.id)
    db.commit()
    return pickup_out(db, p, user)


@router.post("/{pickup_id}/start")
def start(pickup_id: int, user: User = Depends(require_volunteer), db: Session = Depends(get_db)):
    p = lifecycle.start_pickup(db, _get_pickup(db, pickup_id), user)
    db.commit()
    return pickup_out(db, p, user)


@router.post("/{pickup_id}/verify-pickup-otp")
def verify_pickup(pickup_id: int, body: PickupVerifyIn, user: User = Depends(require_volunteer),
                  db: Session = Depends(get_db)):
    p = lifecycle.verify_pickup_otp(
        db, _get_pickup(db, pickup_id), user, body.otp,
        {"food_covered": body.food_covered, "container_clean": body.container_clean,
         "temperature_ok": body.temperature_ok})
    plan_route_for_volunteer(db, user.id)
    log_action(db, user.id, "verify_pickup_otp", "pickup", p.id)
    db.commit()
    return pickup_out(db, p, user)


@router.post("/{pickup_id}/verify-delivery-otp")
def verify_delivery(pickup_id: int, body: OtpIn, user: User = Depends(require_volunteer), db: Session = Depends(get_db)):
    p = lifecycle.verify_delivery_otp(db, _get_pickup(db, pickup_id), user, body.otp)
    plan_route_for_volunteer(db, user.id)
    log_action(db, user.id, "verify_delivery_otp", "pickup", p.id)
    db.commit()
    return pickup_out(db, p, user)


@router.get("/{pickup_id}/route")
def pickup_route(pickup_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _get_pickup(db, pickup_id)
    _assert_participant(db, p, user)
    if p.route_id is None:
        raise not_found("Route")
    r = db.get(Route, p.route_id)
    return {"route_id": r.id, "volunteer_id": r.volunteer_id, "stops": r.planned_stops,
            "total_distance_km": r.total_distance_km, "estimated_minutes": r.estimated_minutes,
            "feasible": r.feasible}
