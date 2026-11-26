"""Shared pytest fixtures. Uses an isolated SQLite file; scheduler disabled."""
import os
import sys
from pathlib import Path

TEST_DB = Path(__file__).resolve().parents[1] / "test_foodbridge.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789"
os.environ["TIME_SCALE"] = "1"
os.environ["MODEL_PATH"] = str(Path(__file__).resolve().parents[1] / "model_artifacts" / "test_model.joblib")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from datetime import datetime  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.core import clock, ratelimit  # noqa: E402
from app.db import models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.seed_core import DEMO_PASSWORD, seed_core  # noqa: E402


# 12:00 IST on a weekday: every NGO with normal operating hours is open.
FIXED_NOW = datetime(2026, 6, 1, 6, 30)


@pytest.fixture(autouse=True)
def fresh_db():
    """Rebuild and seed the schema for every test; reset clock and rate limits."""
    clock.freeze(FIXED_NOW)
    ratelimit.reset()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_core(db)
        db.commit()
    yield
    clock.unfreeze()


@pytest.fixture()
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def login(client: TestClient, email: str, password: str = DEMO_PASSWORD) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def auth(client):
    """Callable returning auth headers for a seeded demo account, e.g. auth('donor1')."""

    def _auth(handle: str) -> dict:
        return login(client, f"{handle}@demo.com")

    return _auth
