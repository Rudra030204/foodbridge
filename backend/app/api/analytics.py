"""Analytics (FR-9) and prediction (FR-10) endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.core.errors import forbidden
from app.db.models import FoodListing, User
from app.schemas.listings import to_naive_utc
from app.services import impact, prediction

router = APIRouter(tags=["analytics"])


def _scope(user: User, donor_id: int | None, ngo_id: int | None) -> tuple[int | None, int | None]:
    """Donors and NGOs only ever see their own numbers; admins may filter freely."""
    if user.role == "donor":
        return user.id, None
    if user.role == "ngo":
        return None, user.id
    if user.role == "volunteer":
        raise forbidden("Volunteers do not have an impact dashboard.")
    return donor_id, ngo_id


@router.get("/analytics/public")
def public_impact(db: Session = Depends(get_db)):
    """Unauthenticated landing-page counters (platform totals only)."""
    s = impact.impact_summary(db)
    active = db.scalar(select(func.count(FoodListing.id)).where(FoodListing.status == "open")) or 0
    return {"meals_rescued": s["meals_rescued"], "kg_saved": s["kg_saved"], "co2e_avoided_kg": s["co2e_avoided_kg"],
            "active_listings": active, "deliveries": s["deliveries"]}


@router.get("/analytics/impact")
def impact_view(donor_id: int | None = None, ngo_id: int | None = None, date_from: datetime | None = None,
                date_to: datetime | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d, n = _scope(user, donor_id, ngo_id)
    return impact.impact_summary(db, d, n, to_naive_utc(date_from), to_naive_utc(date_to))


@router.get("/analytics/performance")
def performance_view(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return impact.performance_summary(db)


@router.get("/analytics/export.csv")
def export_csv(donor_id: int | None = None, ngo_id: int | None = None, date_from: datetime | None = None,
               date_to: datetime | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d, n = _scope(user, donor_id, ngo_id)
    body = impact.impact_csv(impact.impact_summary(db, d, n, to_naive_utc(date_from), to_naive_utc(date_to)))
    return Response(body, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="impact.csv"'})


@router.get("/predictions/forecast")
def forecast(days: int = Query(default=7, ge=1, le=14), user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    if user.role not in ("admin", "ngo", "donor"):
        raise forbidden()
    data = prediction.forecast(db, days)
    db.rollback()
    return data


@router.post("/predictions/retrain")
def retrain(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    meta = prediction.train(db)
    db.rollback()
    return meta
