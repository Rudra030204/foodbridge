"""Authentication and account endpoints."""
import threading

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.errors import AppError, conflict
from app.core.security import (
    create_access_token, create_refresh_token, decode_token, hash_password, verify_password,
)
from app.db.models import DonorProfile, NgoProfile, User, VolunteerProfile
from app.schemas.auth import LoginIn, MeOut, ProfileUpdateIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.services.audit import log_action

router = APIRouter(prefix="/auth", tags=["auth"])

_revoked: set[str] = set()  # revoked refresh-token jti values (process memory)
_revoked_lock = threading.Lock()


def _tokens(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id, user.role), refresh_token=create_refresh_token(user.id, user.role)
    )


def profile_dict(user: User) -> dict | None:
    """Role-specific profile as a plain dict."""
    p = {"donor": user.donor_profile, "ngo": user.ngo_profile, "volunteer": user.volunteer_profile}.get(user.role)
    if p is None:
        return None
    return {c.name: getattr(p, c.name) for c in p.__table__.columns if c.name != "user_id"}


@router.post("/register", response_model=MeOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise conflict("email_taken", "An account with this email already exists.")
    user = User(
        name=body.name, email=body.email, phone=body.phone, password_hash=hash_password(body.password),
        role=body.role, is_verified=False,
    )
    if body.role == "donor":
        user.donor_profile = DonorProfile(**body.donor.model_dump())
    elif body.role == "ngo":
        user.ngo_profile = NgoProfile(**body.ngo.model_dump())
    else:
        v = body.volunteer
        user.volunteer_profile = VolunteerProfile(
            vehicle_type=v.vehicle_type, capacity_meals=v.capacity_meals, home_lat=v.home_lat, home_lng=v.home_lng,
            current_lat=v.home_lat, current_lng=v.home_lng,
        )
        user.is_verified = True  # volunteers need no verification to start
    db.add(user)
    db.flush()
    log_action(db, user.id, "register", "user", user.id)
    db.commit()
    return MeOut(user=UserOut.model_validate(user), profile=profile_dict(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    ratelimit.check(f"login:{body.email.lower()}:{ip}", settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_WINDOW_SECONDS)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError(401, "invalid_credentials", "Incorrect email or password.")
    if not user.is_active:
        raise AppError(403, "account_suspended", "This account has been suspended.")
    return _tokens(user)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token, "refresh")
    if payload is None or payload.get("jti") in _revoked:
        raise AppError(401, "invalid_token", "Invalid or expired refresh token.")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise AppError(401, "invalid_token", "Account not found or suspended.")
    return _tokens(user)


@router.post("/logout")
def logout(body: RefreshIn):
    payload = decode_token(body.refresh_token, "refresh")
    if payload:
        with _revoked_lock:
            _revoked.add(payload["jti"])
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(user=UserOut.model_validate(user), profile=profile_dict(user))


@router.put("/me", response_model=MeOut)
def update_me(body: ProfileUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.name is not None:
        user.name = body.name
    if body.phone is not None:
        user.phone = body.phone
    if user.role == "donor" and body.donor and user.donor_profile:
        for k, v in body.donor.model_dump().items():
            setattr(user.donor_profile, k, v)
    elif user.role == "ngo" and body.ngo and user.ngo_profile:
        for k, v in body.ngo.model_dump().items():
            setattr(user.ngo_profile, k, v)
    elif user.role == "volunteer" and body.volunteer and user.volunteer_profile:
        vp = user.volunteer_profile
        vp.vehicle_type, vp.capacity_meals = body.volunteer.vehicle_type, body.volunteer.capacity_meals
        vp.home_lat, vp.home_lng = body.volunteer.home_lat, body.volunteer.home_lng
    log_action(db, user.id, "update_profile", "user", user.id)
    db.commit()
    return MeOut(user=UserOut.model_validate(user), profile=profile_dict(user))
