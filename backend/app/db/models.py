"""ORM models for FoodBridge Plus (all tables from the spec)."""
from datetime import datetime

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow

ROLES = ("donor", "ngo", "volunteer", "admin")
LISTING_STATUSES = ("open", "claimed", "assigned", "picked_up", "delivered", "expired", "cancelled", "diverted")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rating_sum: Mapped[int] = mapped_column(Integer, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    donor_profile = relationship("DonorProfile", uselist=False, back_populates="user", cascade="all, delete-orphan")
    ngo_profile = relationship("NgoProfile", uselist=False, back_populates="user", cascade="all, delete-orphan")
    volunteer_profile = relationship("VolunteerProfile", uselist=False, back_populates="user", cascade="all, delete-orphan")

    @property
    def reliability(self) -> float | None:
        """Average star rating (None until rated)."""
        return round(self.rating_sum / self.rating_count, 2) if self.rating_count else None


class DonorProfile(Base):
    __tablename__ = "donor_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    org_name: Mapped[str] = mapped_column(String(160))
    donor_type: Mapped[str] = mapped_column(String(30), default="other")
    address: Mapped[str] = mapped_column(String(300))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    fssai_license_no: Mapped[str | None] = mapped_column(String(40), nullable=True)
    user = relationship("User", back_populates="donor_profile")


class NgoProfile(Base):
    __tablename__ = "ngo_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    org_name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(300))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    daily_capacity_meals: Mapped[int] = mapped_column(Integer, default=200)
    accepts_veg: Mapped[bool] = mapped_column(Boolean, default=True)
    accepts_nonveg: Mapped[bool] = mapped_column(Boolean, default=True)
    operating_start: Mapped[str] = mapped_column(String(5), default="06:00")
    operating_end: Mapped[str] = mapped_column(String(5), default="23:00")
    registration_no: Mapped[str | None] = mapped_column(String(60), nullable=True)
    acceptance_rate: Mapped[float] = mapped_column(Float, default=0.5)
    total_claims: Mapped[int] = mapped_column(Integer, default=0)
    total_accepted: Mapped[int] = mapped_column(Integer, default=0)
    is_fallback_partner: Mapped[bool] = mapped_column(Boolean, default=False)
    user = relationship("User", back_populates="ngo_profile")


class VolunteerProfile(Base):
    __tablename__ = "volunteer_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    vehicle_type: Mapped[str] = mapped_column(String(20), default="bike")
    capacity_meals: Mapped[int] = mapped_column(Integer, default=60)
    current_lat: Mapped[float] = mapped_column(Float)
    current_lng: Mapped[float] = mapped_column(Float)
    home_lat: Mapped[float] = mapped_column(Float)
    home_lng: Mapped[float] = mapped_column(Float)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    user = relationship("User", back_populates="volunteer_profile")


class FoodSafetyRule(Base):
    __tablename__ = "food_safety_rules"
    __table_args__ = (UniqueConstraint("food_category", "storage_condition", name="uq_rule"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    food_category: Mapped[str] = mapped_column(String(60))
    storage_condition: Mapped[str] = mapped_column(String(30))
    safe_hours: Mapped[float] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FoodListing(Base):
    __tablename__ = "food_listings"
    __table_args__ = (Index("ix_listing_geo", "lat", "lng"), Index("ix_listing_status_safe", "status", "safe_until"))
    id: Mapped[int] = mapped_column(primary_key=True)
    donor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    food_category: Mapped[str] = mapped_column(String(60))
    is_veg: Mapped[bool] = mapped_column(Boolean, default=True)
    quantity_meals: Mapped[int] = mapped_column(Integer)
    claimed_meals: Mapped[int] = mapped_column(Integer, default=0)
    storage_condition: Mapped[str] = mapped_column(String(30))
    hot_day: Mapped[bool] = mapped_column(Boolean, default=False)
    cooked_at: Mapped[datetime] = mapped_column(DateTime)
    expiry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # printed expiry (sealed food)
    safe_until: Mapped[datetime] = mapped_column(DateTime, index=True)
    pickup_address: Mapped[str] = mapped_column(String(300))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    pickup_window_start: Mapped[datetime] = mapped_column(DateTime)
    pickup_window_end: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    photo_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    first_claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    expiry_warned: Mapped[bool] = mapped_column(Boolean, default=False)

    donor = relationship("User", foreign_keys=[donor_id])

    @property
    def remaining_meals(self) -> int:
        return max(0, self.quantity_meals - self.claimed_meals)


class ListingMatchScore(Base):
    __tablename__ = "listing_match_scores"
    __table_args__ = (UniqueConstraint("listing_id", "ngo_id", name="uq_score"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id", ondelete="CASCADE"), index=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    components: Mapped[dict] = mapped_column(JSON)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    response: Mapped[str] = mapped_column(String(12), default="pending")


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id"), index=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    claimed_quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="active")
    claimed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_diversion: Mapped[bool] = mapped_column(Boolean, default=False)


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(primary_key=True)
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    planned_stops: Mapped[list] = mapped_column(JSON)
    total_distance_km: Mapped[float] = mapped_column(Float)
    estimated_minutes: Mapped[float] = mapped_column(Float)
    feasible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Pickup(Base):
    __tablename__ = "pickups"
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), unique=True, index=True)
    volunteer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_assignment")
    pickup_otp_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_otp_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pickup_otp_plain: Mapped[str | None] = mapped_column(String(8), nullable=True)  # shown to donor only
    delivery_otp_plain: Mapped[str | None] = mapped_column(String(8), nullable=True)  # shown to NGO only
    otp_failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    otp_locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    declined_by: Mapped[list] = mapped_column(JSON, default=list)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    checklist: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EscalationEvent(Base):
    __tablename__ = "escalation_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id", ondelete="CASCADE"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    radius_km: Mapped[float] = mapped_column(Float)
    notified_ngo_ids: Mapped[list] = mapped_column(JSON)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reason: Mapped[str] = mapped_column(String(200))


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default="in_app")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("pickup_id", "from_user", "to_user", name="uq_rating"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    pickup_id: Mapped[int] = mapped_column(ForeignKey("pickups.id"), index=True)
    from_user: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_user: Mapped[int] = mapped_column(ForeignKey("users.id"))
    stars: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_checklist_ok: Mapped[bool] = mapped_column(Boolean, default=True)


class SurplusHistory(Base):
    __tablename__ = "surplus_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    donor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime, index=True)
    hour: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[int] = mapped_column(Integer)
    area_cell: Mapped[str] = mapped_column(String(30), index=True)
    quantity_meals: Mapped[int] = mapped_column(Integer)
    event_flag: Mapped[str] = mapped_column(String(20), default="none")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class ProblemReport(Base):
    __tablename__ = "problem_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id"), index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(200))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SystemSetting(Base):
    """Key/value JSON settings (match weights, scheduler heartbeat...)."""
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
