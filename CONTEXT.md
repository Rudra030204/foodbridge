# FoodBridge Plus: CONTEXT.md (resume file)

Last updated: Phases 1-3 COMPLETE (backend), Phase 4 frontend VERIFIED (build, 22 vitest, 4 Playwright e2e pass, screenshots taken). 2026-11-24. If a chat session hits its limit, give this file plus the project folder to the next session and say: "Continue from CONTEXT.md, follow the same rules."

## What this project is
FoodBridge Plus: AI-assisted surplus food rescue network (donor, NGO, volunteer, admin).
Spec: user's `FoodBridge_Plus_Short_Prompt.md`. Student capstone; Milestone 2 due 2026-11-23 (Milestone 1 Word doc is still missing, offered to write it). Owner: Rudra.

## Environment facts
- Sandbox: Python 3.13, Node 22, Docker CLI present but NO daemon (compose untested). Backend venv: `backend/.venv`.
- Dev/tests on SQLite. Postgres supported (psycopg2 pinned; compose file written, untested).
- Commands (from `backend/`, venv active):
  `alembic upgrade head` | `python -m scripts.seed` | `uvicorn app.main:app --reload` | `python -m pytest tests -q`
  Demo escalation: `TIME_SCALE=60 uvicorn app.main:app` (scheduler interval auto = 30s/TIME_SCALE).
- Demo password for every seeded user: `Demo@1234`. admin@demo.com, donor1..15, ngo1..12, volunteer1..10 @demo.com. donor14/15 + ngo10 unverified; ngo11/ngo12 fallback partners.

## Phase status
| Phase | Status |
|---|---|
| 1 Foundation | DONE |
| 2 Core domain (safety, matching, claims, state machine, OTP, pickups) | DONE |
| 3 Automation (escalation, routing 2-opt, notifier, WebSocket, prediction, impact, admin, seed history) | DONE |
| 4 Frontend (React + Vite + TS + Tailwind + Leaflet + Recharts) | DONE and verified in session 3 (tsc+vite build OK, 22 vitest, 4 Playwright e2e, 22 screenshots in docs/screenshots) |
| 5 Evaluation scripts (5) + docs (UML/DFD/ER/architecture/test-plan/risk/security) + README | DONE (session 3): 5 scripts in backend/scripts (routing, matching, escalation, prediction, benchmark) with outputs in docs/results/; test-plan.md (45 cases); README with no-Docker run steps + 3-min demo; results/summary.md. Mermaid diagrams still not render-checked |
| 6 Bug bash + Definition of Done report | TODO |

## Verified results so far (real runs)
- 110 backend tests passing (`python -m pytest tests -q`, about 95 s), services coverage 97%.
- Double-claim race test: two threads claim same listing, exactly one 201 and one 409.
- Live demo with TIME_SCALE=60: escalation levels 1/2/3 fired at about 10/20/30 real seconds; evidence in `docs/results/escalation_demo.log`.
- Prediction (synthetic data, time split last 28 days, per cell-hour-day MAE/RMSE): gradient boosting MAE 40.1 / RMSE 82.2; naive last-week 42.2 / 86.2; moving average 65.1 / 116.3. GB beats both, but only modestly vs naive. Report honestly. (First attempt was worse than naive because training window lacked wedding-season; fixed by Apr-Jun wedding season + lag-7 feature.)
- Seed is idempotent (checked twice).

## Code map (backend/app)
- `core/`: config, clock (only time source; TIME_SCALE/freeze/real_now), geo, security, errors, ratelimit, deps
- `db/models.py` (17 tables), `alembic/versions/*initial_schema.py`
- `services/`: safety, matching, lifecycle (claim->pickup->delivery), state, otp, routing, escalation, prediction, impact, notifier, realtime, serializers (privacy), seed_core, seed_history, audit
- `api/`: auth, listings, claims, pickups, misc (volunteer loc/availability/route, notifications, ratings), analytics (+predictions), admin, ws
- `jobs/scheduler.py` APScheduler tick -> escalation.run_cycle
- Tests: `tests/conftest.py` (clock frozen 2026-06-01 06:30 UTC = 12:00 IST; fresh seeded DB per test; `auth("donor1")`), `tests/unit`, `tests/integration`.
- Test gotcha: SQLite uses BEGIN IMMEDIATE, so test `db` sessions must `db.rollback()`/`commit()` after reads (helpers in test_flow.py do this).

## API quick reference (prefix /api/v1; docs at /docs)
auth: register, login, refresh, logout, me (GET/PUT). listings: POST, GET (role-scoped), GET/PATCH {id}, POST {id}/cancel, GET {id}/matches, POST {id}/report. claims: POST /listings/{id}/claim, POST /claims/{id}/cancel. pickups: GET mine, GET {id}, POST accept|decline|start|verify-pickup-otp|verify-delivery-otp, GET {id}/route. volunteers: PUT me/location, PUT me/availability, GET me/route. notifications: GET, POST {id}/read, POST read-all. ratings: POST. analytics: GET public (no auth), impact, performance (admin), export.csv. predictions: GET forecast, POST retrain (admin). admin: verifications, users (+suspend/activate), safety-rules (+reset), match-weights, fallback-partners, ngos/{id}/fallback, reports, audit-log, health. WS: /ws?token=. Errors: `{"error":{"code","message"}}`.

## Key decisions (see DECISIONS.md D1-D11)
Python 3.13; SQLite dev; naive-UTC time via clock.py; OTP plain code kept only for donor/NGO display, wiped after use; JWT/rate limits use real time; partial claims keep listing open; NGO can only claim listings offered to it; fallback partners claim only at level 3; volunteer hidden from NGO until accepted; batching = volunteers with a nearby active pickup get 0.5x distance.

## Next steps
1. Phase 4: frontend in `frontend/` (Vite React TS, Tailwind, react-router, TanStack Query, react-leaflet, recharts). Pages per spec section FRONTEND. Vitest tests (countdown, listing form validation, route guards) + one Playwright happy path + screenshots to docs/screenshots.
2. (done) Phase 5: scripts in `backend/scripts/` (simulate_matching, simulate_escalation, simulate_routing, train_prediction, benchmark_api) writing CSV+md to `docs/results/`; docs per spec; README + 3-min demo script; test-plan.md with 30+ real cases.
3. Phase 6: bug bash, Definition of Done report.
4. Separately for the student: Milestone 1 Word doc, Milestone 2 report (requirements, architecture, UML, DFD, test results, risk, progress/next steps, team contributions: ask user for team size and member names).

## Honest known gaps
- Docker compose + Dockerfile not run (no daemon). Frontend, eval scripts, docs not started.
- No browser-level QA yet; Playwright not yet written.
- SMS/WhatsApp are mocks by design. Prediction data is synthetic by design.


## Phase 4 status (frontend) - VERIFIED in session 3
Friend's frontend (session 2) was adopted over the session-1 one (same API client/auth, more pages: reports, rating, retrain, CSV export). Results this session: `npx tsc --noEmit` clean, `npm run build` OK, `vitest` 22 pass, backend `pytest` 111 pass, Playwright e2e 4/4 pass (use `CHROME_PATH=<chromium binary>` env if browsers are preinstalled; first run after a cold Vite start can be slow, expect timeout is 15 s). Screenshots: docs/screenshots (landing, donor dashboard/form/listing, NGO, volunteer en-route+OTP, admin all tabs, impact+forecast, mobile). Map tiles are grey in screenshots only because the sandbox blocks OpenStreetMap.
Bugs fixed in session 3: (1) SQLite "database is locked": slow/aborted GET responses kept a BEGIN IMMEDIATE transaction open; GET requests now use a deferred read engine (`SessionRead` in db/session.py, chosen in core/deps.get_db). (2) Recharts bars invisible in screenshots: animation disabled. (3) Duplicate "Pick up: Pick up:" labels on route. (4) e2e import `type Page`.

## Next steps
1. Phase 4: frontend in `frontend/` (Vite React TS, Tailwind, react-router, TanStack Query, react-leaflet, recharts). Pages per spec section FRONTEND. Vitest tests (countdown, listing form validation, route guards) + one Playwright happy path + screenshots to docs/screenshots.
2. (done) Phase 5: scripts in `backend/scripts/` (simulate_matching, simulate_escalation, simulate_routing, train_prediction, benchmark_api) writing CSV+md to `docs/results/`; docs per spec; README + 3-min demo script; test-plan.md with 30+ real cases.
3. Phase 6: bug bash, Definition of Done report.
4. Separately for the student: Milestone 1 Word doc, Milestone 2 report (requirements, architecture, UML, DFD, test results, risk, progress/next steps, team contributions: ask user for team size and member names).

## Honest known gaps
- Docker compose + Dockerfile not run (no daemon). Frontend, eval scripts, docs not started.
- No browser-level QA yet; Playwright not yet written.
- SMS/WhatsApp are mocks by design. Prediction data is synthetic by design.


## Phase 4 status (frontend) - READ THIS FIRST
All source files now exist (session 2 wrote them with NO network, so nothing was installed, built, or run):
- Shell: main.tsx, App.tsx (exports `RequireRole` guard), components/Layout, NotificationBell, MapView (Leaflet circle markers, OSM tiles), Rate, ui.tsx
- Pages: Landing, Auth (Login + Register), donor/{Dashboard,PostListing,ListingDetail}, ngo/Dashboard (offers + pickups tabs, claim, delivery OTP, rate), volunteer/Dashboard (accept/decline/start, OTP forms with safety checklist, route map, availability, location), Impact (recharts + forecast with synthetic-data warning + CSV export), admin/Admin (6 tabs: verification, users + fallback toggle, safety rules, match weights, reports, system/KPIs/audit/retrain)
- Tests written: src/hooks/useCountdown.test.tsx (countdown, urgency colours, naive-UTC parsing), src/lib/validation.test.ts, src/App.test.tsx (route guard). E2E: frontend/e2e/happy-path.spec.ts + playwright.config.ts (needs backend on :8000, seeded; writes screenshots to docs/screenshots).
What WAS checked: every .ts/.tsx file parses (esbuild), and tsc against stubbed library types found no errors in code that uses our own types (Listing/Pickup/etc). Field names were cross-checked against backend serializers/models by reading them.
What was NOT checked (do these first when you have network): `cd frontend && npm ci && npm run build && npm test`, then fix whatever breaks (expect small type/import issues, e.g. react-leaflet props, recharts typings, `import.meta.env` typing, Tailwind `@apply` with custom classes). Then run backend + `npm run dev`, click through all 4 roles manually, then `npx playwright install chromium && npm run e2e`. Screenshots in docs/screenshots do not exist yet.
Unverified assumptions worth testing: donor `/listings/safety-estimate` query serialisation; volunteer `profile.is_available`/`current_lat` come from `/auth/me` profile dict; admin `/admin/users` accepts `q`; NGO claim 409 message; WebSocket proxy in vite.config.

## Next steps
1. (done) Phase 4 verified.
2. (done) Phase 5: scripts in `backend/scripts/` (simulate_matching, simulate_escalation, simulate_routing, train_prediction, benchmark_api) writing CSV+md to `docs/results/`; docs per spec (see docs/ folder: ER, architecture, DFD, UML, risk, security were drafted in session 2 as Mermaid, review them against code); README + 3-min demo script; test-plan.md with 30+ REAL cases (map to actual test names).
3. Phase 6: bug bash, Definition of Done report.
4. Separately for the student: Milestone 1 Word doc, Milestone 2 report (requirements, architecture, UML, DFD, test results, risk, progress/next steps, team contributions: ask user for team size and member names).

## Honest known gaps
- Backend: 111 tests pass (re-run in session 3 after the read-engine change).
- Docker compose + Dockerfile never run (no daemon). Eval scripts not written. Docs partly drafted (Mermaid never rendered; paste into mermaid.live to check). Risk register R10/R11 list the unverified Docker/frontend items.
- SMS/WhatsApp are mocks by design. Prediction data is synthetic by design.

## Session-start checklist for the next Claude
1. Unzip, `cd backend && python -m venv .venv && pip install -r requirements.txt` (needs network; if the sandbox has none, say so to the user rather than pretending things ran).
2. Re-run `python -m pytest tests -q` to confirm 110 pass before touching anything.
3. Only report numbers you actually produced in this session. Keep CONTEXT.md updated and re-zip before the session ends.

## Session 3 extras
Forecast endpoint cached 5 min (was 6 s/call). Phase 6 DONE (docs/definition-of-done.md; Mermaid all render, PNGs in docs/diagrams; full UI e2e added; VSCODE_RUN_STEPS.md written). Remaining: Milestone 1 doc and Milestone 2 report (need team size and member names from the user), Docker untested.
