"""Routing experiment: input order vs nearest-neighbour vs NN + 2-opt on random multi-pickup scenarios.
Usage (from backend/): python -m scripts.simulate_routing"""
import random, statistics as st
from datetime import datetime
from scripts._common import write_csv, write_md
from app.services import routing
from app.services.routing import Stop

NOW = datetime(2026, 6, 1, 6, 30); START = (28.47, 77.50)

def scenario(rng, n, tight):
    stops = []
    for i in range(n):
        dl = NOW.replace(hour=7, minute=30) if tight and rng.random() < .5 else None
        stops.append(Stop("pickup", 28.47 + rng.uniform(-.08, .08), 77.50 + rng.uniform(-.08, .08), i, dl, f"p{i}"))
        stops.append(Stop("delivery", 28.47 + rng.uniform(-.08, .08), 77.50 + rng.uniform(-.08, .08), i, dl, f"d{i}"))
    return stops

def naive(stops):  # visit each pickup then its delivery, in the order requested
    return stops

def main(trials=200, seed=11):
    rng = random.Random(seed); rows = []
    for n in (2, 3, 4):
        for tight in (False, True):
            a, b, c, va, vc = [], [], [], 0, 0
            for _ in range(trials):
                s = scenario(rng, n, tight)
                ea = routing.evaluate(START, naive(s), NOW)
                r = routing.optimize(START, s, NOW)
                a.append(ea["distance_km"]); b.append(r["baseline_eval"]["distance_km"]); c.append(r["eval"]["distance_km"])
                va += ea["violations"] > 0; vc += r["eval"]["violations"] > 0
                assert routing.precedence_ok(r["order"])
            rows.append({"pickups": n, "tight_deadlines": tight, "trials": trials, "naive_km": round(st.mean(a), 2),
                         "nn_km": round(st.mean(b), 2), "nn_2opt_km": round(st.mean(c), 2),
                         "saving_vs_naive_pct": round(100 * (1 - st.mean(c) / st.mean(a)), 1),
                         "deadline_miss_rate_naive": round(va / trials, 3), "deadline_miss_rate_optimised": round(vc / trials, 3)})
    write_csv("routing_results.csv", rows)
    md = "# Routing results\n\nRandom scenarios in a ~18 km box (seed %d, %d trials each). 'naive' = stops in request order.\n\n| pickups | tight deadlines | naive km | NN km | NN+2-opt km | saving vs naive | miss rate naive | miss rate optimised |\n|---|---|---|---|---|---|---|---|\n" % (seed, trials)
    for r in rows:
        md += f"| {r['pickups']} | {r['tight_deadlines']} | {r['naive_km']} | {r['nn_km']} | {r['nn_2opt_km']} | {r['saving_vs_naive_pct']}% | {r['deadline_miss_rate_naive']} | {r['deadline_miss_rate_optimised']} |\n"
    md += "\nAll optimised routes passed the pickup-before-delivery precedence check. Synthetic geometry; straight-line (haversine) distances, not road distances.\n"
    write_md("routing_results.md", md); print(md)

if __name__ == "__main__":
    main()
