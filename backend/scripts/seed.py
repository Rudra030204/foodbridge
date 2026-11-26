"""Seed the database with demo data (idempotent).

Usage (from backend/):  python -m scripts.seed
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.services.seed_core import DEMO_PASSWORD, seed_core  # noqa: E402


def run() -> dict:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        summary = seed_core(db)
        try:
            from app.services.seed_history import seed_history

            summary.update(seed_history(db))
        except ImportError:
            pass
        db.commit()
    return summary


def main() -> None:
    summary = run()
    print("Seed summary:", summary)
    print("\nDemo credentials (password for all: %s)" % DEMO_PASSWORD)
    print("  admin      admin@demo.com")
    print("  donor      donor1@demo.com ... donor15@demo.com   (donor14, donor15 unverified)")
    print("  ngo        ngo1@demo.com ... ngo12@demo.com       (ngo10 unverified; ngo11 and ngo12 are fallback compost/feed partners)")
    print("  volunteer  volunteer1@demo.com ... volunteer10@demo.com")


if __name__ == "__main__":
    main()
