# FoodBridge Plus

AI-assisted surplus food rescue network: donors post surplus food with a live safe-until countdown, nearby NGOs are ranked and notified, requests escalate automatically if nobody claims, and volunteers get optimised pickup routes with OTP-verified hand-offs.

**Stack:** FastAPI + SQLAlchemy + APScheduler (backend), React + Vite + TypeScript + Tailwind + Leaflet + Recharts (frontend), SQLite for development (PostgreSQL via Docker Compose), scikit-learn for demand forecasting.

## Run it on your laptop (no Docker - this is the tested path)
Needs Python 3.11+ and Node 20+.

```bash
# 1) backend  (terminal 1)
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head                 # creates foodbridge.db
python -m scripts.seed               # demo data (safe to re-run)
uvicorn app.main:app --port 8000

# 2) frontend (terminal 2)
cd frontend
npm install
npm run dev                          # open http://localhost:5173
```
Windows note: if `python -m scripts.seed` fails, use `python scripts/seed.py`.
Internet is needed once for `pip`/`npm` and while running (map tiles).

Demo logins (password `Demo@1234` for all): `donor1@demo.com`, `ngo1@demo.com` ... `ngo12@demo.com`, `volunteer1@demo.com` ... `volunteer10@demo.com`, `admin@demo.com`.
(donor14, donor15 and ngo10 are unverified on purpose; ngo11/ngo12 are compost/feed fallback partners.)
Reset the data any time: stop the server, delete `backend/foodbridge.db`, run `alembic upgrade head` and the seed again.

## Docker (untested here)
`cp .env.example .env && docker compose up --build` then open http://localhost:5173. Written but never executed in the build sandbox, so treat it as a bonus and use the no-Docker path for the demo.

## 3-minute demo script
Use three browser windows (normal, incognito, a second browser or profile) so you can stay logged in as different users.
1. **Landing page** - live counters (meals rescued, CO2e avoided). Say: "food is safe only for a few hours, so time is the core constraint."
2. **Donor** (`donor1@demo.com`) - Post surplus: type "Wedding buffet", 60 meals, cooked 20 minutes ago. Point at the live safe-for countdown. Post. On the listing page show the escalation steps and "Why these NGOs?" score bars (distance, time, capacity, preference, history).
3. **NGO** (`ngo6@demo.com`, Old Age Care Home) - the offer appears with an alert; open it, note the exact address is hidden until claim, then Claim.
4. **Volunteer** (any volunteer shown on the NGO pickup, e.g. `volunteer7@demo.com`) - Accept, view the optimised route, Start trip. Pickup: tick the safety checklist, enter the donor's 4-digit code (shown on the donor's listing page). Delivery: enter the NGO's code. Delivered.
5. **Escalation** (talking point or `python -m scripts.simulate_escalation`): if no NGO claims, radius widens at 10 and 20 minutes, then compost/animal-feed partners at 30 minutes. For a live demo start the backend with `TIME_SCALE=60` to make a minute take one second.
6. **Admin** (`admin@demo.com`) - verification queue, match weights, safety rules, system health, forecast on the Impact page (note: synthetic data).

## Tests and evaluation
```bash
cd backend && python -m pytest tests -q          # 111 tests
cd frontend && npm test                          # 22 unit tests
cd frontend && npm run e2e                       # needs backend running + seeded
cd backend && python -m scripts.simulate_routing # also: simulate_matching, simulate_escalation, train_prediction, benchmark_api
```
Results are written to `docs/results/`. See `docs/test-plan.md`, `docs/results/summary.md`, and the design documents in `docs/` (architecture, ER, DFD, UML, risk register, security). Design decisions: `DECISIONS.md`.

## Honest limits
Safety windows are conservative heuristics, not certified food-safety advice. SMS/WhatsApp are mocks. The forecast uses synthetic data. SQLite is the tested database; PostgreSQL/Docker is untested.
