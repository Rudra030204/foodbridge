# Results summary (2026-11-24)

| Area | Result | Source |
|---|---|---|
| Backend tests | 111 / 111 pass | pytest |
| Frontend unit tests | 22 / 22 pass | Vitest |
| Browser end-to-end | 5 / 5 pass (incl. full delivery via UI) | Playwright |
| Routing | NN + 2-opt cuts route length 12-31% vs request order (2-4 pickups); every route keeps pickup-before-delivery; deadline misses fall but remain with 1-hour deadlines over ~30 km routes | routing_results.md |
| Escalation | Level 0 at 0 min, level 1 at 10, level 2 at 20 (8 NGOs), level 3 at 30 (fallback partners) | escalation_timeline.md |
| Matching | Weighted first choice averages 3.2 km vs 3.06 km nearest-only and 5.67 km random, with slightly higher capacity fit and time score than random. Gain over nearest-only is small on this seed data | matching_results.md |
| Forecast (synthetic data) | MAE 42.0 vs 43.6 naive last-week vs 67.8 moving average: modest win over naive, clear win over moving average | prediction_results.md |
| API latency (SQLite, dev machine) | p50 70-145 ms, p95 under 215 ms for core GET endpoints at concurrency 8; forecast cached after the first call (the first call after a restart takes about 6 s) | benchmark_api.md |
| Seeded history | 89 delivered pickups, 121 listings, escalation rate 55% | admin KPIs |

## Bugs found and fixed while testing
1. SQLite "database is locked": slow GET responses held the write lock. GET now uses a deferred read connection (DECISIONS.md D12).
2. Forecast endpoint took about 6 s per call: result cached for 5 minutes, cleared on retrain.
3. Charts rendered empty in screenshots (animation) and duplicated route labels: fixed.

## User feedback
No real users yet. Suggested for the milestone: have 5 classmates play donor/NGO/volunteer with the demo script and fill a 5-question form (clarity of the countdown, ease of posting, trust in OTP step, what is confusing, one improvement). Report the actual answers; do not invent them.
