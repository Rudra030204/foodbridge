"""Volunteer location/availability, notifications, ratings."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_volunteer
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.db.models import Claim, FoodListing, Notification, Pickup, Rating, User
from app.schemas.listings import RatingIn
from app.services.routing import plan_route_for_volunteer

router = APIRouter(tags=["misc"])


class LocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class AvailabilityIn(BaseModel):
    is_available: bool


@router.put("/volunteers/me/location")
def set_location(body: LocationIn, user: User = Depends(require_volunteer), db: Session = Depends(get_db)):
    vp = user.volunteer_profile
    vp.current_lat, vp.current_lng = body.lat, body.lng
    plan_route_for_volunteer(db, user.id)  # ETAs depend on where the volunteer is now
    db.commit()
    return {"lat": vp.current_lat, "lng": vp.current_lng}


@router.get("/volunteers/me/route")
def my_route(user: User = Depends(require_volunteer), db: Session = Depends(get_db)):
    route = plan_route_for_volunteer(db, user.id)
    db.commit()
    if route is None:
        return {"route_id": None, "stops": [], "total_distance_km": 0, "estimated_minutes": 0, "feasible": True}
    return {"route_id": route.id, "stops": route.planned_stops, "total_distance_km": route.total_distance_km,
            "estimated_minutes": route.estimated_minutes, "feasible": route.feasible}


@router.put("/volunteers/me/availability")
def set_availability(body: AvailabilityIn, user: User = Depends(require_volunteer), db: Session = Depends(get_db)):
    user.volunteer_profile.is_available = body.is_available
    db.commit()
    return {"is_available": user.volunteer_profile.is_available}


def _note(n: Notification) -> dict:
    return {"id": n.id, "type": n.type, "title": n.title, "body": n.body, "channel": n.channel,
            "is_read": n.is_read, "data": n.data, "created_at": n.created_at}


@router.get("/notifications")
def list_notifications(unread_only: bool = False, channel: str = "in_app", limit: int = Query(default=50, ge=1, le=200),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(Notification).where(Notification.user_id == user.id, Notification.channel == channel)
    if unread_only:
        q = q.where(Notification.is_read.is_(False))
    unread = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.channel == "in_app", Notification.is_read.is_(False))) or 0
    rows = db.scalars(q.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).all()
    return {"unread": unread, "items": [_note(n) for n in rows]}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise not_found("Notification")
    n.is_read = True
    db.commit()
    return _note(n)


@router.post("/notifications/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))):
        n.is_read = True
    db.commit()
    return {"ok": True}


@router.post("/ratings", status_code=201)
def create_rating(body: RatingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pickup = db.get(Pickup, body.pickup_id)
    if pickup is None:
        raise not_found("Pickup")
    claim = db.get(Claim, pickup.claim_id)
    listing = db.get(FoodListing, claim.listing_id)
    participants = {listing.donor_id, claim.ngo_id, pickup.volunteer_id} - {None}
    if user.id not in participants or body.to_user not in participants:
        raise forbidden("Both rater and rated user must be part of this pickup.")
    if body.to_user == user.id:
        raise bad_request("self_rating", "You cannot rate yourself.")
    if pickup.status != "delivered":
        raise conflict("not_delivered", "Ratings are possible only after delivery.")
    if db.scalar(select(Rating.id).where(Rating.pickup_id == pickup.id, Rating.from_user == user.id,
                                         Rating.to_user == body.to_user)):
        raise conflict("already_rated", "You already rated this user for this pickup.")
    db.add(Rating(pickup_id=pickup.id, from_user=user.id, to_user=body.to_user, stars=body.stars,
                  comment=body.comment, safety_checklist_ok=body.safety_checklist_ok))
    target = db.get(User, body.to_user)
    target.rating_sum += body.stars
    target.rating_count += 1
    db.commit()
    return {"to_user": target.id, "reliability": target.reliability, "rating_count": target.rating_count}
