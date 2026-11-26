# Definition of Done report (2026-11-24)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Backend runs; API documented | PASS | uvicorn starts; Swagger at http://localhost:8000/docs |
| 2 | DB schema + migration + seed | PASS | alembic upgrade head; `python -m scripts.seed` (15 donors, 12 NGOs, 10 volunteers, 89 delivered pickups) |
| 3 | Safety-based safe-until with 45-min rescue rule | PASS | 14 unit tests |
| 4 | Matching with explainable scores | PASS | unit tests; "Why these NGOs?" in the UI |
| 5 | Race-safe claiming | PASS | test_double_claim_race_exactly_one_wins |
| 6 | Auto-escalation L0-L3 and expiry | PASS | integration tests, simulate_escalation, live demo log |
| 7 | Volunteer assignment, batching, route optimisation | PASS | routing tests; routing_results.md |
| 8 | OTP hand-off with lockout; safety checklist | PASS | unit, API and browser tests |
| 9 | Privacy (approximate location until claim; volunteer hidden until accepted) | PASS | test_full_happy_path_with_privacy_and_ratings |
| 10 | Real-time notifications | PASS | WebSocket test; toast seen in browser |
| 11 | Four role UIs, responsive | PASS | screenshots incl. 390 px mobile |
| 12 | Analytics, CSV export, forecast | PASS (forecast data synthetic) | impact page, prediction_results.md |
| 13 | Admin: verification, rules, weights, reports, audit, health | PASS | integration tests, admin screenshots |
| 14 | Automated tests | PASS | 111 backend, 22 frontend, 5 browser |
| 15 | Evaluation scripts with results | PASS | docs/results |
| 16 | Docs: requirements/architecture/ER/DFD/UML/risk/security/test plan | PASS (see note) | docs/*.md; all 9 Mermaid diagrams render; PNGs in docs/diagrams |
| 17 | README with run steps and demo script | PASS | README.md, VSCODE_RUN_STEPS.md |
| 18 | Docker Compose | NOT VERIFIED | written, never run (no Docker in the build sandbox) |
| 19 | PostgreSQL | NOT VERIFIED | SQLite is the tested database |
| 20 | Real user feedback | NOT DONE | no users yet; collect 5 responses before the milestone |

Note: docs/requirements.md is not a separate file; requirements are in the README, test plan and architecture docs. Write the Milestone 2 report from these.

## Bugs found and fixed in the bug bash
1. "database is locked" under browser use (GET held the SQLite write lock): fixed with a deferred read connection.
2. Forecast endpoint 6 s per call: cached.
3. Empty charts in screenshots (animation) and duplicated route labels: fixed.
4. E2E config: wrong type import and cold-start timeouts: fixed.

## Known limits
Mock SMS/WhatsApp; synthetic forecast data; heuristic safety rules (not certified); haversine distances not road distances; map tiles need internet.
