"""Auth / account schemas."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

DonorType = Literal["hostel", "restaurant", "wedding", "caterer", "event", "other"]
VehicleType = Literal["walk", "bike", "car", "van"]


class DonorProfileIn(BaseModel):
    org_name: str = Field(min_length=2, max_length=160)
    donor_type: DonorType = "other"
    address: str = Field(min_length=3, max_length=300)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    fssai_license_no: str | None = Field(default=None, max_length=40)


class NgoProfileIn(BaseModel):
    org_name: str = Field(min_length=2, max_length=160)
    address: str = Field(min_length=3, max_length=300)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    daily_capacity_meals: int = Field(default=200, ge=1, le=100000)
    accepts_veg: bool = True
    accepts_nonveg: bool = True
    operating_start: str = Field(default="06:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    operating_end: str = Field(default="23:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    registration_no: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def _accepts_something(self):
        if not (self.accepts_veg or self.accepts_nonveg):
            raise ValueError("NGO must accept at least one of veg / non-veg food.")
        return self


class VolunteerProfileIn(BaseModel):
    vehicle_type: VehicleType = "bike"
    capacity_meals: int = Field(default=60, ge=1, le=5000)
    home_lat: float = Field(ge=-90, le=90)
    home_lng: float = Field(ge=-180, le=180)


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    phone: str | None = Field(default=None, max_length=30)
    role: Literal["donor", "ngo", "volunteer"]
    donor: DonorProfileIn | None = None
    ngo: NgoProfileIn | None = None
    volunteer: VolunteerProfileIn | None = None

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def _strong(cls, v: str) -> str:
        if not (any(c.isalpha() for c in v) and any(c.isdigit() for c in v)):
            raise ValueError("Password must contain letters and digits.")
        return v

    @model_validator(mode="after")
    def _profile_matches_role(self):
        needed = {"donor": self.donor, "ngo": self.ngo, "volunteer": self.volunteer}[self.role]
        if needed is None:
            raise ValueError(f"Profile for role '{self.role}' is required (field '{self.role}').")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    phone: str | None
    role: str
    is_verified: bool
    is_active: bool
    reliability: float | None = None
    rating_count: int = 0


class ProfileUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    donor: DonorProfileIn | None = None
    ngo: NgoProfileIn | None = None
    volunteer: VolunteerProfileIn | None = None


class MeOut(BaseModel):
    user: UserOut
    profile: dict | None = None
