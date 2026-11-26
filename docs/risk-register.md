# Risk register

| # | Risk | Likelihood | Impact | Mitigation in this project | Status |
|---|---|---|---|---|---|
| R1 | Unsafe food distributed | Medium | High | Conservative safe-hours rules, minimum 45 min safe time to post, countdown shown to all, volunteer safety checklist, problem reports, disclaimer on every estimate. Rules are heuristics, **not** food-safety certification. | Mitigated, residual risk accepted for a prototype |
| R2 | Two NGOs claim the same food | Medium | Medium | Row lock (PostgreSQL) / serialised writers (SQLite) + conditional update. Race test: exactly one 201, one 409. | Tested (SQLite only) |
| R3 | No NGO responds before spoilage | High | High | Escalation L1/L2/L3, fallback compost / feed partners, expiry warnings | Tested with automated tests and a TIME_SCALE=60 live run |
| R4 | Fake or abusive accounts | Medium | Medium | Admin verification for donors and NGOs, suspend/activate, login rate limit, daily listing cap, audit log | Implemented |
| R5 | OTP guessing | Low | Medium | 4-digit OTP, 5 attempts then 10 min lock, hashed storage | Tested |
| R6 | Location privacy | Medium | Medium | Approximate coordinates and no address until a claim; volunteer contact hidden until accepted | Tested |
| R7 | Forecast model looks better than it is | Medium | Low | Trained on synthetic data; UI shows a warning; metrics reported against naive baselines (gain over last-week baseline is modest) | Disclosed |
| R8 | SMS/WhatsApp not real | Certain | Low | Mock adapters by design, interface isolated in `notifier.py` | Disclosed |
| R9 | Single-process limits | Medium | Medium | Rate limiter, token revocation list and WebSocket registry are in process memory; would need Redis for multiple workers | Known limitation |
| R10 | Docker deployment untested | Medium | Medium | Compose and Dockerfiles written but never run (no daemon in the build sandbox) | Open |
| R11 | Frontend unverified | High (as of this checkpoint) | Medium | Needs `npm ci && npm run build && npm test` and a browser click-through | Open |
