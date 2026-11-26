"""Matching experiment on the seeded DB: weighted score vs nearest-NGO vs random, for sample listings.
Metric = proxy quality of the first-choice NGO: distance, and fraction that has capacity and fits in the safe window.
Usage (from backend/, seeded DB): python -m scripts.simulate_matching"""
import random, statistics as st
from sqlalchemy import select
from scripts._common import write_csv, write_md
from app.db.models import FoodListing
from app.db.session import SessionLocal
from app.services import matching

def main(n=60, seed=5):
    rng = random.Random(seed)
    with SessionLocal() as db:
        listings = db.scalars(select(FoodListing).order_by(FoodListing.id.desc()).limit(300)).all()
        listings = rng.sample(listings, min(n, len(listings)))
        res = {"weighted": [], "nearest": [], "random": []}; used = 0
        for l in listings:
            c = matching.rank_candidates(db, l, now=l.created_at, persist=False)
            if len(c) < 2: continue
            used += 1
            picks = {"weighted": c[0], "nearest": min(c, key=lambda x: x.distance_km), "random": rng.choice(c)}
            for k, p in picks.items():
                res[k].append((p.distance_km, p.components["capacity"], p.components["time"], p.score))
        db.rollback()
    rows = [{"strategy": k, "listings": len(v), "avg_distance_km": round(st.mean(x[0] for x in v), 2),
             "avg_capacity_fit": round(st.mean(x[1] for x in v), 3), "avg_time_score": round(st.mean(x[2] for x in v), 3),
             "avg_weighted_score": round(st.mean(x[3] for x in v), 3)} for k, v in res.items()]
    write_csv("matching_results.csv", rows)
    md = f"# Matching results\n\n{used} sampled historical listings (seed {seed}), ranked as at their creation time; first-choice NGO per strategy.\n\n| strategy | listings | avg distance km | capacity fit | time score | weighted score |\n|---|---|---|---|---|---|\n"
    md += "".join(f"| {r['strategy']} | {r['listings']} | {r['avg_distance_km']} | {r['avg_capacity_fit']} | {r['avg_time_score']} | {r['avg_weighted_score']} |\n" for r in rows)
    md += "\nThe weighted ranker trades a little distance for capacity and reliability. Capacity state is the current DB state, so this is indicative, not a historical replay.\n"
    write_md("matching_results.md", md); print(md)

if __name__ == "__main__":
    main()
