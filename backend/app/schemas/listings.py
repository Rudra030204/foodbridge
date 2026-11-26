"""Listing, claim, pickup and rating schemas."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.safety import CATEGORIES, STORAGE_CONDITIONS

Category = Literal[CATEGORIES]  # type: ignore[valid-type]
Storage = Literal[STORAGE_CONDITIONS]  # type: ignore[valid-type]


def to_naive_utc(v: datetime | None) -> datetime | None:
    """Accept ISO strings with or without timezone; store naive UTC."""
    if v is None:
        return None
    if v.tzinfo is not None:
        v = v.astimezone(timezone.utc).replace(tzinfo=None)
    return v


class ListingCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    food_category: Category
    is_veg: bool = True
    quantity_meals: int = Field(ge=1, le=5000)
    storage_condition: Storage
    hot_day: bool = False
    cooked_at: datetime | None = None
    expiry_at: datetime | None = None
    pickup_address: str | None = Field(default=None, min_length=3, max_length=300)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    pickup_window_start: datetime | None = None
    pickup_window_end: datetime | None = None
    photo_url: str | None = Field(default=None, max_length=300)

    _norm = field_validator("cooked_at", "expiry_at", "pickup_window_start", "pickup_window_end")(
        lambda cls, v: to_naive_utc(v)
    )

    @model_validator(mode="after")
    def _veg_rule(self):
        if self.food_category == "nonveg_cooked" and self.is_veg:
            raise ValueError("Non-veg cooked food cannot be flagged as veg.")
        if (self.lat is None) != (self.lng is None):
            raise ValueError("Provide both lat and lng, or neither.")
        return self


class ListingPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    quantity_meals: int | None = Field(default=None, ge=1, le=5000)
    pickup_window_start: datetime | None = None
    pickup_window_end: datetime | None = None
    photo_url: str | None = Field(default=None, max_length=300)

    _norm = field_validator("pickup_window_start", "pickup_window_end")(lambda cls, v: to_naive_utc(v))


class ClaimIn(BaseModel):
    quantity: int | None = Field(default=None, ge=1)


class OtpIn(BaseModel):
    otp: str = Field(pattern=r"^\d{4}$")


class PickupVerifyIn(OtpIn):
    food_covered: bool = False
    container_clean: bool = False
    temperature_ok: bool = False


class RatingIn(BaseModel):
    pickup_id: int
    to_user: int
    stars: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)
    safety_checklist_ok: bool = True


class ReportIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)
    details: str | None = Field(default=None, max_length=2000)
