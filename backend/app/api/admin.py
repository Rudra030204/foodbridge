"""Admin endpoints (FR-8, FR-11)."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.deps import get_db, require_admin
from app.core.errors import bad_request, not_found
from app.db.models import (
    AuditLog, FoodListing, FoodSafetyRule, NgoProfile, Pickup, ProblemReport, SystemSetting, User,
)
from app.services import matching
from app.services.audit import log_action
from app.services.notifier import notify
from app.services.realtime import manager
from app.services.safety import CATEGORIES, DEFAULT_RULES, STORAGE_CONDITIONS

router = APIRouter(prefix="/admin", tags=["admin"])


def _user_row(u: User) -> dict:
    prof = u.donor_profile or u.ngo_profile or u.volunteer_profile
    return {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role,
            "is_verified": u.is_verified, "is_active": u.is_active, "reliability": u.reliability,
            "rating_count": u.rating_count, "created_at": u.created_at,
            "org_name": getattr(prof, "org_name", None),
            "is_fallback_partner": getattr(prof, "is_fallback_partner", None)}


# ---------------------------------------------------------------- verification & users
@router.get("/verifications")
def verification_queue(role: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = select(User).where(User.role.in_(("donor", "ngo")), User.is_verified.is_(False), User.is_active.is_(True))
    if role:
        q = q.where(User.role == role)
    return {"items": [_user_row(u) for u in db.scalars(q.order_by(User.created_at))]}


class VerifyIn(BaseModel):
    approve: bool = True


@router.post("/verifications/{user_id}")
def decide_verification(user_id: int, body: VerifyIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None or u.role not in ("donor", "ngo"):
        raise not_found("Donor/NGO account")
    if body.approve:
        u.is_verified = True
        notify(db, u.id, "verified", "Account verified", "Your organisation has been verified. Welcome aboard!")
    else:
        u.is_active = False
        notify(db, u.id, "verification_rejected", "Verification rejected", "Your registration could not be verified.")
    log_action(db, admin.id, "verify_user" if body.approve else "reject_user", "user", u.id)
    db.commit()
    return _user_row(u)


@router.get("/users")
def list_users(role: str | None = None, q: str | None = None, is_active: bool | None = None,
               limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db),
               _: User = Depends(require_admin)):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(User.name).like(like) | func.lower(User.email).like(like))
    return {"items": [_user_row(u) for u in db.scalars(stmt.order_by(User.id).limit(limit))]}


def _set_active(db: Session, admin: User, user_id: int, active: bool) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise not_found("User")
    if u.id == admin.id:
        raise bad_request("self_action", "You cannot suspend your own account.")
    u.is_active = active
    log_action(db, admin.id, "activate_user" if active else "suspend_user", "user", u.id)
    db.commit()
    return _user_row(u)


@router.post("/users/{user_id}/suspend")
def suspend(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _set_active(db, admin, user_id, False)


@router.post("/users/{user_id}/activate")
def activate(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _set_active(db, admin, user_id, True)


# ---------------------------------------------------------------- safety rules
class RuleIn(BaseModel):
    food_category: str
    storage_condition: str
    safe_hours: float = Field(gt=0, le=720)
    notes: str | None = Field(default=None, max_length=500)


@router.get("/safety-rules")
def list_rules(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.scalars(select(FoodSafetyRule).order_by(FoodSafetyRule.food_category, FoodSafetyRule.storage_condition))
    return {"disclaimer": "Conservative heuristics for rescue prioritisation; not medical advice.",
            "categories": list(CATEGORIES), "storage_conditions": list(STORAGE_CONDITIONS),
            "items": [{"id": r.id, "food_category": r.food_category, "storage_condition": r.storage_condition,
                       "safe_hours": r.safe_hours, "notes": r.notes} for r in rows]}


@router.post("/safety-rules")
def upsert_rule(body: RuleIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.food_category not in CATEGORIES or body.storage_condition not in STORAGE_CONDITIONS:
        raise bad_request("bad_rule", "Unknown food category or storage condition.")
    if "sealed_packaged" in (body.food_category, body.storage_condition):
        raise bad_request("bad_rule", "Sealed packaged food uses the printed expiry; it has no hours rule.")
    rule = db.scalar(select(FoodSafetyRule).where(FoodSafetyRule.food_category == body.food_category,
                                                  FoodSafetyRule.storage_condition == body.storage_condition))
    if rule is None:
        rule = FoodSafetyRule(food_category=body.food_category, storage_condition=body.storage_condition,
                              safe_hours=body.safe_hours, notes=body.notes)
        db.add(rule)
    else:
        rule.safe_hours, rule.notes = body.safe_hours, body.notes if body.notes is not None else rule.notes
    db.flush()
    log_action(db, admin.id, "upsert_safety_rule", "safety_rule", rule.id)
    db.commit()
    return {"id": rule.id, "food_category": rule.food_category, "storage_condition": rule.storage_condition,
            "safe_hours": rule.safe_hours, "notes": rule.notes}


@router.post("/safety-rules/reset")
def reset_rules(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Restore every rule to the built-in default hours."""
    n = 0
    for rule in db.scalars(select(FoodSafetyRule)):
        default = DEFAULT_RULES.get((rule.food_category, rule.storage_condition))
        if default and rule.safe_hours != default[0]:
            rule.safe_hours, n = default[0], n + 1
    log_action(db, admin.id, "reset_safety_rules", "safety_rule", None)
    db.commit()
    return {"reset": n}


# ---------------------------------------------------------------- matching weights
class WeightsIn(BaseModel):
    distance: float = Field(ge=0, le=1)
    time: float = Field(ge=0, le=1)
    capacity: float = Field(ge=0, le=1)
    preference: float = Field(ge=0, le=1)
    history: float = Field(ge=0, le=1)


@router.get("/match-weights")
def get_weights(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return {"weights": matching.get_weights(db), "defaults": matching.DEFAULT_WEIGHTS}


@router.put("/match-weights")
def set_weights(body: WeightsIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    w = body.model_dump()
    if abs(sum(w.values()) - 1.0) > 0.01:
        raise bad_request("weights_sum", f"Weights must add up to 1.0 (got {sum(w.values()):.3f}).")
    row = db.get(SystemSetting, "match_weights")
    if row is None:
        db.add(SystemSetting(key="match_weights", value=w))
    else:
        row.value = w
    log_action(db, admin.id, "set_match_weights", "settings", None)
    db.commit()
    return {"weights": w}


# ---------------------------------------------------------------- fallback partners, reports, audit, health
class FallbackIn(BaseModel):
    is_fallback_partner: bool


@router.get("/fallback-partners")
def fallback_partners(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.execute(select(NgoProfile, User).join(User, User.id == NgoProfile.user_id)).all()
    return {"items": [{"user_id": p.user_id, "org_name": p.org_name, "is_fallback_partner": p.is_fallback_partner,
                       "is_verified": u.is_verified} for p, u in rows]}


@router.put("/ngos/{user_id}/fallback")
def set_fallback(user_id: int, body: FallbackIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    prof = db.get(NgoProfile, user_id)
    if prof is None:
        raise not_found("NGO")
    prof.is_fallback_partner = body.is_fallback_partner
    log_action(db, admin.id, "set_fallback_partner", "ngo", user_id)
    db.commit()
    return {"user_id": user_id, "is_fallback_partner": prof.is_fallback_partner}


@router.get("/reports")
def problem_reports(status: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = select(ProblemReport).order_by(ProblemReport.created_at.desc())
    if status:
        q = q.where(ProblemReport.status == status)
    return {"items": [{"id": r.id, "listing_id": r.listing_id, "reporter_id": r.reporter_id, "reason": r.reason,
                       "details": r.details, "status": r.status, "created_at": r.created_at}
                      for r in db.scalars(q.limit(200))]}


@router.post("/reports/{report_id}/resolve")
def resolve_report(report_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    r = db.get(ProblemReport, report_id)
    if r is None:
        raise not_found("Report")
    r.status = "resolved"
    log_action(db, admin.id, "resolve_report", "report", r.id)
    db.commit()
    return {"id": r.id, "status": r.status}


@router.get("/audit-log")
def audit_log(limit: int = Query(default=100, ge=1, le=500), action: str | None = None,
              db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        q = q.where(AuditLog.action == action)
    return {"items": [{"id": a.id, "actor_id": a.actor_id, "action": a.action, "entity": a.entity,
                       "entity_id": a.entity_id, "created_at": a.created_at} for a in db.scalars(q.limit(limit))]}


@router.get("/health")
def system_health(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    beat = db.get(SystemSetting, "scheduler_status")
    now = clock.now()
    last = beat.value.get("last_run") if beat else None
    open_n = db.scalar(select(func.count(FoodListing.id)).where(FoodListing.status == "open")) or 0
    pending = db.scalar(select(func.count(Pickup.id)).where(Pickup.status == "pending_assignment")) or 0
    return {"status": "ok", "db": "ok", "time": now, "time_scale": settings.TIME_SCALE,
            "scheduler": {"enabled": settings.SCHEDULER_ENABLED, "last_run": last,
                          "last_result": beat.value.get("last_result") if beat else None},
            "open_listings": open_n, "pickups_waiting_for_volunteer": pending,
            "websocket_users_online": manager.online_users()}
