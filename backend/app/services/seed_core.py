"""Idempotent seeding of users, NGOs, volunteers, safety rules and settings.

Re-running never duplicates rows (users are keyed by e-mail, rules by (category, storage)).
Greater Noida / Delhi-NCR coordinates are used for realism.
"""
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import (
    DonorProfile, FoodSafetyRule, NgoProfile, SystemSetting, User, VolunteerProfile,
)
from app.services.safety import DEFAULT_RULES, DISCLAIMER

DEMO_PASSWORD = "Demo@1234"
CENTER = (28.4744, 77.5040)  # Greater Noida

DEFAULT_WEIGHTS = {"distance": 0.30, "time": 0.30, "capacity": 0.20, "preference": 0.05, "history": 0.15}

DONOR_SPECS = [
    ("Bennett Hostel Mess A", "hostel"), ("Bennett Hostel Mess B", "hostel"), ("Galgotias Boys Hostel", "hostel"),
    ("Shiv Shakti Banquet", "wedding"), ("Royal Palace Wedding Hall", "wedding"), ("Gulmohar Lawns", "wedding"),
    ("Spice Route Restaurant", "restaurant"), ("Tandoor Junction", "restaurant"), ("Veg Delight Cafe", "restaurant"),
    ("Annapurna Caterers", "caterer"), ("Sharma Catering Co", "caterer"), ("Delhi Darbar Caterers", "caterer"),
    ("Corporate Fest Events", "event"), ("Tech Park Canteen", "other"), ("Sunrise Bakery", "other"),
]
NGO_SPECS = [
    # name, daily capacity, veg, nonveg, acceptance rate, claims, fallback
    ("Roti Bank Noida", 400, True, True, 0.90, 80, False),
    ("Seva Kitchen Trust", 300, True, True, 0.82, 60, False),
    ("Hunger Free Greater Noida", 250, True, True, 0.75, 55, False),
    ("Asha Kiran Shelter", 120, True, False, 0.88, 40, False),
    ("Bal Vikas Orphanage", 150, True, True, 0.70, 35, False),
    ("Old Age Care Home Sector 12", 80, True, False, 0.65, 30, False),
    ("Street Kids Foundation", 200, True, True, 0.60, 45, False),
    ("Night Shelter Dadri", 180, True, True, 0.72, 38, False),
    ("Community Langar Seva", 500, True, True, 0.85, 90, False),
    ("Women Empowerment Centre", 100, True, True, 0.55, 20, False),
    ("Green Compost Collective", 1000, True, True, 0.95, 50, True),
    ("AnimalCare Feed Partner", 800, True, True, 0.93, 45, True),
]
VOLUNTEER_SPECS = [
    ("bike", 40), ("bike", 40), ("bike", 50), ("car", 120), ("car", 150),
    ("van", 400), ("van", 500), ("bike", 40), ("car", 100), ("walk", 20),
]


def _jitter(rng: random.Random, spread: float) -> tuple[float, float]:
    return CENTER[0] + rng.uniform(-spread, spread), CENTER[1] + rng.uniform(-spread, spread)


def seed_settings(db: Session) -> None:
    if db.get(SystemSetting, "match_weights") is None:
        db.add(SystemSetting(key="match_weights", value=dict(DEFAULT_WEIGHTS)))
    db.flush()


def seed_safety_rules(db: Session) -> int:
    added = 0
    existing = {(r.food_category, r.storage_condition) for r in db.scalars(select(FoodSafetyRule))}
    for (cat, storage), (hours, note) in DEFAULT_RULES.items():
        if (cat, storage) not in existing:
            db.add(FoodSafetyRule(food_category=cat, storage_condition=storage, safe_hours=hours,
                                  notes=f"{note} {DISCLAIMER}"))
            added += 1
    db.flush()
    return added


def _get_or_create_user(db: Session, email: str, name: str, role: str, pw_hash: str, verified: bool, phone: str) -> tuple[User, bool]:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user, False
    user = User(name=name, email=email, phone=phone, password_hash=pw_hash, role=role, is_verified=verified)
    db.add(user)
    db.flush()
    return user, True


def seed_users(db: Session, seed: int = 42) -> dict[str, int]:
    """Create admin, donors, NGOs and volunteers. Returns counts of newly created rows."""
    rng = random.Random(seed)
    pw = hash_password(DEMO_PASSWORD)
    created = {"admin": 0, "donor": 0, "ngo": 0, "volunteer": 0}

    _, new = _get_or_create_user(db, "admin@demo.com", "Platform Admin", "admin", pw, True, "9000000000")
    created["admin"] += int(new)

    for i, (org, dtype) in enumerate(DONOR_SPECS, start=1):
        lat, lng = _jitter(rng, 0.06)
        user, new = _get_or_create_user(db, f"donor{i}@demo.com", f"{org} Manager", "donor", pw, i <= 13, f"98100000{i:02d}")
        if new:
            user.donor_profile = DonorProfile(
                org_name=org, donor_type=dtype, address=f"{org}, Greater Noida", lat=lat, lng=lng,
                fssai_license_no=f"1002{i:04d}000{i:02d}" if i <= 13 else None,
            )
            created["donor"] += 1

    for i, (org, cap, veg, nonveg, rate, claims, fb) in enumerate(NGO_SPECS, start=1):
        lat, lng = _jitter(rng, 0.07)
        user, new = _get_or_create_user(db, f"ngo{i}@demo.com", f"{org} Coordinator", "ngo", pw, i != 10, f"98200000{i:02d}")
        if new:
            user.ngo_profile = NgoProfile(
                org_name=org, address=f"{org}, Delhi-NCR", lat=lat, lng=lng, daily_capacity_meals=cap,
                accepts_veg=veg, accepts_nonveg=nonveg, registration_no=f"NGO/UP/{2015 + i}/{1000 + i}",
                operating_start="00:00" if i in (1, 2, 3, 9, 11, 12) else "06:00",
                operating_end="23:59" if i in (1, 2, 3, 9, 11, 12) else "23:00",
                acceptance_rate=rate, total_claims=claims, total_accepted=round(claims * rate), is_fallback_partner=fb,
            )
            created["ngo"] += 1

    for i, (vehicle, cap) in enumerate(VOLUNTEER_SPECS, start=1):
        lat, lng = _jitter(rng, 0.06)
        user, new = _get_or_create_user(db, f"volunteer{i}@demo.com", f"Volunteer {i}", "volunteer", pw, True, f"98300000{i:02d}")
        if new:
            user.volunteer_profile = VolunteerProfile(
                vehicle_type=vehicle, capacity_meals=cap, current_lat=lat, current_lng=lng, home_lat=lat, home_lng=lng
            )
            created["volunteer"] += 1
    db.flush()
    return created


def seed_core(db: Session) -> dict:
    """Seed everything needed for a working system (no history). Caller commits."""
    seed_settings(db)
    rules = seed_safety_rules(db)
    users = seed_users(db)
    return {"rules_added": rules, **users}
