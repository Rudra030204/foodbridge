# Test plan and results

Automated: **111 backend tests (pytest) + 22 frontend unit tests (Vitest) + 5 browser end-to-end tests (Playwright, including a full donor-NGO-volunteer delivery through the UI) - all passing** on the last run (2026-11-24).
Run them: `cd backend && python -m pytest tests -q`, `cd frontend && npm test`, `cd frontend && npm run e2e` (backend running and freshly seeded).

| ID | Area | Test case | Expected | Automated test | Result |
|---|---|---|---|---|---|
| T01 | Auth | Register donor / NGO / volunteer | 201, profile created | test_auth::test_register_each_role | Pass |
| T02 | Auth | Donor and NGO start unverified, volunteer verified | flags correct | test_donor_and_ngo_start_unverified_volunteer_verified | Pass |
| T03 | Auth | Self-register as admin | rejected | test_cannot_self_register_as_admin | Pass |
| T04 | Auth | Duplicate email / weak password | 409 / 422 | test_duplicate_email_conflict, test_weak_password_rejected | Pass |
| T05 | Auth | Login, refresh, logout; access token as refresh | works / rejected | test_login_me_refresh_logout, test_access_token_cannot_be_used_as_refresh | Pass |
| T06 | Auth | Brute-force login | rate limited (429) | test_login_rate_limit | Pass |
| T07 | Auth | Suspended user login | blocked | test_suspended_user_cannot_login | Pass |
| T08 | Safety | Cooked meal at room temp gets 15% buffer | safe_until reduced | test_cooked_meal_room_applies_15_percent_buffer | Pass |
| T09 | Safety | Hot day shortens window | shorter | test_hot_day_reduces_window | Pass |
| T10 | Safety | Every default (category, storage) rule | matches table | test_every_default_rule[...] (8 cases) | Pass |
| T11 | Safety | Less than 45 min left | rejected as not rescuable | test_check_rescuable_rejects_under_45_min | Pass |
| T12 | Safety | Sealed food needs printed expiry | validation error | test_sealed_requires_expiry_and_consistent_fields | Pass |
| T13 | Safety | Admin edits a rule | new listings use it | test_safety_rule_editor_changes_new_listings | Pass |
| T14 | Matching | Distance / time / capacity / history components | formula values | test_matching_state_otp (components) | Pass |
| T15 | Matching | Weighted score equals formula | exact | test_weighted_score_matches_formula | Pass |
| T16 | Matching | Veg / non-veg preference exclusion | excluded | test_preference_exclusion_veg_and_nonveg | Pass |
| T17 | Matching | Out of capacity, too far, out of time | excluded | test_excluded_when_too_far_out_of_time_or_no_capacity | Pass |
| T18 | Matching | Overnight operating hours | correct | test_operating_hours_including_overnight | Pass |
| T19 | Matching | Admin weights validation and effect | ranking changes | test_match_weights_validation_and_effect | Pass |
| T20 | Listing | Create listing, rank, notify top NGOs | notified | test_create_listing_matches_and_notifies_top5 | Pass |
| T21 | Listing | Validation and daily limit | 422 / 429 | test_listing_validation_and_rescue_window, test_daily_listing_limit | Pass |
| T22 | Claim | Two NGOs claim at once | exactly one wins | test_double_claim_race_exactly_one_wins | Pass |
| T23 | Claim | Partial claim | remainder stays open | test_partial_claim_leaves_remainder_open | Pass |
| T24 | Claim | Claim after expiry | rejected | test_claim_after_expiry_rejected | Pass |
| T25 | Claim | Cancel claim re-opens listing | open again | test_cancel_claim_reopens_listing_and_cancel_listing | Pass |
| T26 | State | Illegal transitions | 409 | test_transition_matrix (12 cases), test_illegal_transition_raises_409 | Pass |
| T27 | Flow | Full path donor to delivery with privacy and ratings | delivered | test_full_happy_path_with_privacy_and_ratings | Pass |
| T28 | Privacy | NGO sees only approximate location before claim; access control | enforced | test_listing_access_control, happy path | Pass |
| T29 | OTP | 5 wrong codes | locked 10 min (423) | test_otp_lockout_after_five_failures, test_pickup_otp_lockout_via_api | Pass |
| T30 | OTP | Hashed with salt | verify ok | test_otp_hash_verify_and_salt | Pass |
| T31 | Volunteer | Decline triggers reassignment | reassigned | test_volunteer_decline_reassigns | Pass |
| T32 | Automation | Escalation L0 to L3 on schedule | levels advance | test_escalation_progresses_through_levels | Pass |
| T33 | Automation | Fallback partner only at final level, status diverted | correct | test_fallback_partner_can_claim_only_at_final_level_and_status_is_diverted | Pass |
| T34 | Automation | Little time left jumps to L3 | jumps | test_low_remaining_time_jumps_to_level_three_applying_all_levels | Pass |
| T35 | Automation | Expiry, warning sent once, stale pickup failed | correct | test_expiry_*, test_expiry_warning_sent_once, test_stale_pickup_is_failed_and_listing_expires | Pass |
| T36 | Routing | NN keeps pickup-before-delivery; 2-opt never worse | holds | test_routing (7 tests) | Pass |
| T37 | Routing | Nearby claims batched on one volunteer | one route | test_nearby_claims_are_batched_onto_one_volunteer_and_route | Pass |
| T38 | Realtime | WebSocket push on notification | received | test_websocket_receives_push | Pass |
| T39 | Analytics | Public and scoped impact, CSV, performance | correct | test_analytics_admin (public_and_scoped_impact, csv_export...) | Pass |
| T40 | Prediction | Forecast structure, retrain, no-data error | ok | test_forecast_structure_and_retrain, test_forecast_without_history_is_a_clear_error | Pass |
| T41 | Admin | Verification, suspend, fallback toggle, reports, audit, health | ok | test_analytics_admin (7 tests) | Pass |
| T42 | UI | Countdown counts down and changes colour; shows Expired | green/amber/red | useCountdown.test.tsx (5) | Pass |
| T43 | UI | Listing form validation | errors shown | validation.test.ts (13) | Pass |
| T44 | UI | Route guard: anonymous, wrong role, right role | redirects | App.test.tsx (4) | Pass |
| T46 | E2E | Full rescue through the UI: NGO claims, volunteer accepts, wrong OTP shows error, correct OTPs, delivered | listing delivered | e2e/full-flow.spec.ts | Pass |
| T45 | E2E | Landing counters; donor posts and sees countdown and match explanation; volunteer blocked from /admin; NGO and admin dashboards | as described | e2e/happy-path.spec.ts (4) | Pass |

## Manual checks (done 2026-11-24, screenshots in docs/screenshots)
Donor, NGO, volunteer, admin (all tabs), impact page and mobile (390 px) layouts rendered and looked correct. Real browser flow: post listing, NGO claim, volunteer accept and start trip.

## Not tested / limits
- Docker Compose and PostgreSQL were not run (no Docker daemon in the build sandbox). SQLite is the tested database.
- Map tiles need internet (OpenStreetMap); they were blocked in the test sandbox so screenshots show grey maps.
- SMS/WhatsApp are mock adapters. Forecast data is synthetic.
- No load test beyond `scripts/benchmark_api.py`; no real users yet, so no real user feedback (see results/summary.md for how to collect it).
