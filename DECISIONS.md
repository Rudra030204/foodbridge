# DECISIONS

- D1: The sandbox (and every test run) uses Python 3.13, so the Dockerfile uses python:3.13-slim instead of the 3.11 in the brief; all pinned deps were installed and tested on 3.13. docker-compose.yml could NOT be run here (no Docker daemon).
- D2: Development and all tests run on SQLite (Docker daemon not available in the sandbox). Postgres path is provided via docker-compose and uses SELECT ... FOR UPDATE; SQLite path uses an atomic conditional UPDATE. Both code paths exist.
- D3: All datetimes are naive UTC, produced only via app/core/clock.py (supports TIME_SCALE and test freezing).
- D4: Food safety rules are conservative heuristics, not medical advice.
- D5: Surplus data is synthetic and labelled as such everywhere.
- D6: OTPs are 4-digit one-time codes. A bcrypt-free SHA-256 hash (with per-app pepper) is used for verification; the plain code is kept only so the donor (pickup OTP) / NGO (delivery OTP) can display it, and is wiped on successful use or cancellation.
- D7: JWT expiry and rate limits use real wall-clock time (clock.real_now), never the scaled simulation clock, so TIME_SCALE demos do not log users out.
- D8: On SQLite every transaction starts with BEGIN IMMEDIATE (serialised writers) so concurrent claims are safe; on Postgres the listing row is locked with SELECT ... FOR UPDATE plus an atomic conditional UPDATE guard.
- D9: Partial claims leave the listing `open` until fully claimed (remaining_meals > 0). Listing status afterwards follows the least-advanced pickup (claimed -> assigned -> picked_up -> delivered; `diverted` for fallback-partner claims).
- D10: total_claims on NGO profile counts offers received and total_accepted counts claims made; acceptance_rate = accepted / offered.
- D11: NGO can only claim listings that were actually offered (notified) to it; escalation widens that set, so radius escalation is meaningful. Fallback partners may claim only at escalation level 3.
- D12 (frontend): Leaflet uses coloured CircleMarkers instead of default image markers, so no icon-asset bundling issues. Tokens live in localStorage (api/client.ts) with one automatic refresh; the WebSocket only triggers query invalidation + a toast, REST remains the source of truth. Route guards live in App.tsx (`RequireRole`) and the server re-enforces every role check.

## D12 (session 3) Read-only GETs use a deferred SQLite engine
BEGIN IMMEDIATE on every request let one slow GET block all writers (scheduler tick took 10-20 s, logins timed out, 'database is locked'). GET requests now use `SessionRead` (deferred BEGIN, WAL readers never block writers). Writes keep BEGIN IMMEDIATE. Contract: GET endpoints must not write.
