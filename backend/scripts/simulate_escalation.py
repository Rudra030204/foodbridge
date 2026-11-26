"""Escalation timeline simulation using the real service code and a frozen/advanced clock on a throwaway DB.
Usage (from backend/): python -m scripts.simulate_escalation   (does NOT touch your dev DB)"""
import os, tempfile
tmp = tempfile.mkdtemp(); os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/sim.db"; os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["MODEL_PATH"] = f"{tmp}/m.joblib"
from datetime import datetime, timedelta
from scripts._common import write_csv, write_md
from app.core import clock
from app.db import models  # noqa
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.seed_core import seed_core
from app.services import escalation, lifecycle
from app.db.models import FoodListing, User, ListingMatchScore
from sqlalchemy import select, func

def main():
    Base.metadata.create_all(engine)
    start = datetime(2026, 6, 1, 6, 30); clock.freeze(start)
    rows = []
    with SessionLocal() as db:
        seed_core(db); db.commit()
        from fastapi.testclient import TestClient
        from app.main import app
        c = TestClient(app)
        tok = c.post("/api/v1/auth/login", json={"email": "donor1@demo.com", "password": "Demo@1234"}).json()["access_token"]
        r = c.post("/api/v1/listings", headers={"authorization": "Bearer " + tok}, json={
            "title": "Escalation sim", "food_category": "cooked_meal", "storage_condition": "room", "is_veg": True,
            "quantity_meals": 50, "cooked_at": (start - timedelta(minutes=30)).isoformat() + "Z"})
        assert r.status_code == 201, r.text
        lst = type("L", (), {"id": r.json()["id"]})
        for minute in range(0, 61, 5):
            clock.freeze(start + timedelta(minutes=minute)); escalation.run_cycle(db); db.commit()
            l = db.get(FoodListing, lst.id)
            n = db.scalar(select(func.count()).select_from(ListingMatchScore).where(ListingMatchScore.listing_id == l.id, ListingMatchScore.notified_at.is_not(None)))
            rows.append({"minute": minute, "status": l.status, "escalation_level": l.escalation_level, "ngos_notified": n})
    write_csv("escalation_timeline.csv", rows)
    md = "# Escalation simulation\n\nOne 50-meal listing nobody claims, clock advanced in 5-minute steps (real service code, throwaway DB).\n\n| minute | status | level | NGOs notified |\n|---|---|---|---|\n"
    md += "".join(f"| {r['minute']} | {r['status']} | {r['escalation_level']} | {r['ngos_notified']} |\n" for r in rows)
    write_md("escalation_timeline.md", md); print(md)

if __name__ == "__main__":
    main()
