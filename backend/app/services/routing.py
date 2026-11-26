"""Volunteer route planning (FR-5): nearest-neighbour baseline improved by 2-opt.

Constraints honoured by both algorithms:
  * precedence: a delivery stop must come after its own pickup stop (when the pickup is still pending)
  * time windows: pickup deadline = min(pickup window end, safe_until); delivery deadline = safe_until
Cost is lexicographic: (number of deadline violations, total distance), so feasibility always wins over distance.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.geo import haversine_km, travel_minutes
from app.db.models import Claim, FoodListing, NgoProfile, Pickup, Route

SERVICE_MINUTES = 5.0  # time spent at each stop (loading / handover)


@dataclass(frozen=True)
class Stop:
    kind: str  # "pickup" | "delivery"
    lat: float
    lng: float
    pickup_id: int
    deadline: datetime | None
    label: str


def _d(a_lat: float, a_lng: float, s: Stop) -> float:
    return haversine_km(a_lat, a_lng, s.lat, s.lng)


def precedence_ok(order: list[Stop]) -> bool:
    """True if every delivery appears after the pickup stop with the same pickup_id (if that pickup is in the route)."""
    seen_pickup: set[int] = set()
    pickup_ids = {s.pickup_id for s in order if s.kind == "pickup"}
    for s in order:
        if s.kind == "pickup":
            seen_pickup.add(s.pickup_id)
        elif s.pickup_id in pickup_ids and s.pickup_id not in seen_pickup:
            return False
    return True


def evaluate(start: tuple[float, float], order: list[Stop], now: datetime, speed_kmph: float | None = None) -> dict:
    """Distance, duration, per-stop ETA and deadline violations of visiting ``order`` from ``start``."""
    speed = speed_kmph or settings.AVG_SPEED_KMPH
    lat, lng, t, dist, viol = start[0], start[1], now, 0.0, 0
    etas, legs = [], []
    for s in order:
        leg = haversine_km(lat, lng, s.lat, s.lng)
        t = t + timedelta(minutes=travel_minutes(leg, speed))
        dist += leg
        etas.append(t)
        legs.append(leg)
        if s.deadline is not None and t > s.deadline:
            viol += 1
        t = t + timedelta(minutes=SERVICE_MINUTES)
        lat, lng = s.lat, s.lng
    return {"distance_km": dist, "minutes": (t - now).total_seconds() / 60.0 if order else 0.0,
            "etas": etas, "legs": legs, "violations": viol, "feasible": viol == 0}


def _cost(start, order, now, speed=None):
    e = evaluate(start, order, now, speed)
    return (e["violations"], e["distance_km"])


def nearest_neighbor(start: tuple[float, float], stops: list[Stop]) -> list[Stop]:
    """Greedy baseline that always respects precedence."""
    remaining, order, pos = list(stops), [], start
    pickup_ids_pending = {s.pickup_id for s in stops if s.kind == "pickup"}
    done_pickups: set[int] = set()
    while remaining:
        eligible = [s for s in remaining
                    if s.kind == "pickup" or s.pickup_id in done_pickups or s.pickup_id not in pickup_ids_pending]
        nxt = min(eligible, key=lambda s: _d(pos[0], pos[1], s))
        remaining.remove(nxt)
        order.append(nxt)
        pos = (nxt.lat, nxt.lng)
        if nxt.kind == "pickup":
            done_pickups.add(nxt.pickup_id)
    return order


def two_opt(start: tuple[float, float], order: list[Stop], now: datetime, speed: float | None = None,
            max_passes: int = 100) -> list[Stop]:
    """Improve ``order`` by reversing segments while (violations, distance) strictly decreases."""
    best = list(order)
    best_cost = _cost(start, best, now, speed)
    for _ in range(max_passes):
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                if not precedence_ok(cand):
                    continue
                c = _cost(start, cand, now, speed)
                if c[0] < best_cost[0] or (c[0] == best_cost[0] and c[1] < best_cost[1] - 1e-9):
                    best, best_cost, improved = cand, c, True
        if not improved:
            break
    return best


def optimize(start: tuple[float, float], stops: list[Stop], now: datetime | None = None, speed: float | None = None) -> dict:
    """Plan a route: NN baseline -> 2-opt. Returns the plan plus baseline numbers for comparison."""
    now = now or clock.now()
    baseline = nearest_neighbor(start, stops)
    base_eval = evaluate(start, baseline, now, speed)
    best = two_opt(start, baseline, now, speed)
    ev = evaluate(start, best, now, speed)
    return {"order": best, "eval": ev, "baseline_order": baseline, "baseline_eval": base_eval}


def _serialize(order: list[Stop], ev: dict) -> list[dict]:
    return [{"seq": i + 1, "kind": s.kind, "label": s.label, "lat": s.lat, "lng": s.lng, "pickup_id": s.pickup_id,
             "eta": ev["etas"][i].isoformat(), "deadline": s.deadline.isoformat() if s.deadline else None,
             "leg_km": round(ev["legs"][i], 3)} for i, s in enumerate(order)]


def stops_for_volunteer(db: Session, volunteer_id: int) -> list[Stop]:
    rows = db.execute(
        select(Pickup, Claim, FoodListing).join(Claim, Claim.id == Pickup.claim_id)
        .join(FoodListing, FoodListing.id == Claim.listing_id)
        .where(Pickup.volunteer_id == volunteer_id, Pickup.status.in_(("assigned", "en_route", "picked_up")))
    ).all()
    stops: list[Stop] = []
    for pickup, claim, listing in rows:
        ngo = db.get(NgoProfile, claim.ngo_id)
        if pickup.status in ("assigned", "en_route"):
            deadline = min(listing.pickup_window_end, listing.safe_until)
            stops.append(Stop("pickup", listing.lat, listing.lng, pickup.id, deadline, f"Pick up: {listing.title}"))
        stops.append(Stop("delivery", ngo.lat, ngo.lng, pickup.id, listing.safe_until, f"Deliver to {ngo.org_name}"))
    return stops


def plan_route_for_volunteer(db: Session, volunteer_id: int) -> Route | None:
    """(Re)plan and persist the volunteer's route from their live position. None if they have no active stops."""
    from app.db.models import VolunteerProfile

    stops = stops_for_volunteer(db, volunteer_id)
    if not stops:
        return None
    vp = db.get(VolunteerProfile, volunteer_id)
    start = (vp.current_lat, vp.current_lng)
    plan = optimize(start, stops)
    ev = plan["eval"]
    route = Route(volunteer_id=volunteer_id, planned_stops=_serialize(plan["order"], ev),
                  total_distance_km=round(ev["distance_km"], 3), estimated_minutes=round(ev["minutes"], 1),
                  feasible=ev["feasible"])
    db.add(route)
    db.flush()
    for pid in {s.pickup_id for s in stops}:
        p = db.get(Pickup, pid)
        if p:
            p.route_id = route.id
    return route
