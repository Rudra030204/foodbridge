"""Impact and performance analytics (FR-9)."""
import csv
import io
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Claim, FoodListing, Pickup, User


def _filters(q, donor_id, ngo_id, d_from, d_to):
    if donor_id is not None:
        q = q.where(FoodListing.donor_id == donor_id)
    if ngo_id is not None:
        q = q.where(Claim.ngo_id == ngo_id)
    if d_from is not None:
        q = q.where(FoodListing.created_at >= d_from)
    if d_to is not None:
        q = q.where(FoodListing.created_at <= d_to)
    return q


def impact_summary(db: Session, donor_id: int | None = None, ngo_id: int | None = None,
                   d_from: datetime | None = None, d_to: datetime | None = None) -> dict:
    """Totals for meals rescued / kg / CO2e / success rate / time-to-claim / escalation rate (date = listing created)."""
    rows = db.execute(_filters(
        select(Pickup, Claim, FoodListing).join(Claim, Claim.id == Pickup.claim_id)
        .join(FoodListing, FoodListing.id == Claim.listing_id), donor_id, ngo_id, d_from, d_to)).all()
    delivered = [(p, c, l) for p, c, l in rows if p.status == "delivered"]
    failed = sum(1 for p, _c, _l in rows if p.status in ("failed", "cancelled"))
    rescued = sum(c.claimed_quantity for _p, c, _l in delivered if not c.is_diversion)
    diverted = sum(c.claimed_quantity for _p, c, _l in delivered if c.is_diversion)
    kg = round((rescued + diverted) * settings.KG_PER_MEAL, 1)

    lq = select(FoodListing)
    if donor_id is not None:
        lq = lq.where(FoodListing.donor_id == donor_id)
    if ngo_id is not None:
        lq = lq.where(FoodListing.id.in_(select(Claim.listing_id).where(Claim.ngo_id == ngo_id)))
    if d_from is not None:
        lq = lq.where(FoodListing.created_at >= d_from)
    if d_to is not None:
        lq = lq.where(FoodListing.created_at <= d_to)
    listings = db.scalars(lq).all()
    waits = [(l.first_claimed_at - l.created_at).total_seconds() / 60 for l in listings if l.first_claimed_at]
    by_status: dict[str, int] = defaultdict(int)
    for l in listings:
        by_status[l.status] += 1
    by_day: dict[str, int] = defaultdict(int)
    for p, c, l in delivered:
        by_day[(p.delivered_at or l.created_at).date().isoformat()] += c.claimed_quantity
    handled = len(delivered) + failed
    return {
        "meals_rescued": rescued, "meals_diverted": diverted, "kg_saved": kg,
        "co2e_avoided_kg": round(kg * settings.CO2E_PER_KG, 1),
        "delivery_success_rate": round(len(delivered) / handled, 4) if handled else None,
        "avg_time_to_claim_min": round(sum(waits) / len(waits), 1) if waits else None,
        "escalation_rate": round(sum(1 for l in listings if l.escalation_level >= 1) / len(listings), 4) if listings else None,
        "listings_total": len(listings), "listings_by_status": dict(by_status),
        "deliveries": len(delivered), "by_day": [{"date": d, "meals": m} for d, m in sorted(by_day.items())],
        "assumptions": {"kg_per_meal": settings.KG_PER_MEAL, "co2e_per_kg_food": settings.CO2E_PER_KG},
    }


def performance_summary(db: Session) -> dict:
    """Operational KPIs: claim speed per escalation level, claim -> delivery time, claim rate by level."""
    listings = db.scalars(select(FoodListing)).all()
    by_level: dict[int, dict] = {}
    for lvl in range(4):
        group = [l for l in listings if l.escalation_level == lvl and l.status != "cancelled"]
        claimed = [l for l in group if l.first_claimed_at]
        waits = [(l.first_claimed_at - l.created_at).total_seconds() / 60 for l in claimed]
        by_level[lvl] = {"listings": len(group), "claim_rate": round(len(claimed) / len(group), 4) if group else None,
                         "avg_time_to_claim_min": round(sum(waits) / len(waits), 1) if waits else None}
    deliveries = db.execute(select(Pickup, Claim).join(Claim, Claim.id == Pickup.claim_id)
                            .where(Pickup.status == "delivered")).all()
    durations = [(p.delivered_at - c.claimed_at).total_seconds() / 60 for p, c in deliveries if p.delivered_at]
    users = {r: db.query(User).filter(User.role == r).count() for r in ("donor", "ngo", "volunteer")}
    return {"by_escalation_level": by_level,
            "avg_claim_to_delivery_min": round(sum(durations) / len(durations), 1) if durations else None,
            "deliveries": len(deliveries), "users": users}


def impact_csv(summary: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "meals_rescued", "kg_saved", "co2e_avoided_kg"])
    for row in summary["by_day"]:
        kg = row["meals"] * settings.KG_PER_MEAL
        w.writerow([row["date"], row["meals"], round(kg, 1), round(kg * settings.CO2E_PER_KG, 1)])
    w.writerow([])
    w.writerow(["TOTAL", summary["meals_rescued"] + summary["meals_diverted"], summary["kg_saved"], summary["co2e_avoided_kg"]])
    return buf.getvalue()
