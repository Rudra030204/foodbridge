# Security notes

Implemented (verified by reading the code; backend behaviours are covered by the session-1 test suite):
- **Passwords**: bcrypt (`core/security.py`), minimum 8 characters with letters and digits.
- **Tokens**: JWT access (60 min) and refresh (7 days); logout revokes the refresh token jti (in memory, see R9). Frontend keeps tokens in `localStorage` (XSS would expose them; an httpOnly cookie is the stronger production choice).
- **Authorisation**: role dependencies on every router (`require_donor`, `require_ngo`, ...); donors only see their own listings, NGOs only listings offered to them, volunteers only their own pickups; the frontend guard is convenience only.
- **Abuse limits**: login 10 attempts / 5 min per email+IP, 20 listings per donor per day, OTP lock after 5 wrong attempts for 10 min.
- **Privacy**: exact address and coordinates only for participants who need them (`serializers.py`); donor id hidden from NGOs/volunteers on listings.
- **Input validation**: Pydantic schemas with bounds (quantity 1-5000, lat/lng ranges, OTP `^\d{4}$`).
- **Audit**: sensitive actions written to `audit_log`.
- **CORS**: origin allow-list from settings.

Not done / limitations: no HTTPS termination (deploy behind a proxy), no email verification, no CSRF concerns because bearer tokens are used, in-memory limiter and revocation list, plain OTP retained until use (decision D6).
