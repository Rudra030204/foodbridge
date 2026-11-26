# Entity-relationship diagram

Source of truth: `backend/app/db/models.py` (17 tables) and the Alembic migration. Render with any Mermaid viewer (GitHub, VS Code Mermaid extension, mermaid.live).

```mermaid
erDiagram
    users ||--o| donor_profiles : "has (role=donor)"
    users ||--o| ngo_profiles : "has (role=ngo)"
    users ||--o| volunteer_profiles : "has (role=volunteer)"
    users ||--o{ food_listings : "donor posts"
    food_listings ||--o{ listing_match_scores : "ranked NGOs"
    users ||--o{ listing_match_scores : "ngo is scored"
    food_listings ||--o{ claims : "claimed by"
    users ||--o{ claims : "ngo claims"
    claims ||--o| pickups : "fulfilled by"
    users ||--o{ pickups : "volunteer carries"
    users ||--o{ routes : "volunteer plans"
    routes ||--o{ pickups : "groups stops"
    food_listings ||--o{ escalation_events : "escalates"
    pickups ||--o{ ratings : "rated after delivery"
    users ||--o{ ratings : "from_user / to_user"
    users ||--o{ notifications : "receives"
    food_listings ||--o{ problem_reports : "reported"
    users ||--o{ problem_reports : "reporter"
    users ||--o{ surplus_history : "donor history"
    users ||--o{ audit_log : "actor"

    users { int id PK string email UK string role bool is_verified bool is_active int rating_sum int rating_count }
    donor_profiles { int user_id PK,FK string org_name string donor_type float lat float lng string fssai_license_no }
    ngo_profiles { int user_id PK,FK string org_name float lat float lng int daily_capacity_meals bool accepts_veg bool accepts_nonveg float acceptance_rate bool is_fallback_partner }
    volunteer_profiles { int user_id PK,FK string vehicle_type int capacity_meals float current_lat float current_lng bool is_available }
    food_safety_rules { int id PK string food_category string storage_condition float safe_hours }
    food_listings { int id PK int donor_id FK string food_category string storage_condition int quantity_meals int claimed_meals datetime cooked_at datetime safe_until string status int escalation_level }
    listing_match_scores { int id PK int listing_id FK int ngo_id FK float score int rank json components datetime notified_at string response }
    claims { int id PK int listing_id FK int ngo_id FK int claimed_quantity string status bool is_diversion }
    routes { int id PK int volunteer_id FK json planned_stops float total_distance_km bool feasible }
    pickups { int id PK int claim_id FK int volunteer_id FK int route_id FK string status string pickup_otp_hash string delivery_otp_hash int otp_failed_attempts datetime otp_locked_until }
    escalation_events { int id PK int listing_id FK int level float radius_km json notified_ngo_ids }
    notifications { int id PK int user_id FK string type string channel bool is_read }
    ratings { int id PK int pickup_id FK int from_user FK int to_user FK int stars }
    surplus_history { int id PK int donor_id FK string area_cell int quantity_meals string event_flag bool is_synthetic }
    problem_reports { int id PK int listing_id FK int reporter_id FK string status }
    system_settings { string key PK json value }
    audit_log { int id PK int actor_id FK string action string entity int entity_id }
```

Notes
- `food_safety_rules` and `system_settings` are standalone configuration tables (admin-editable safe hours and match weights).
- Only password hashes (bcrypt) and OTP hashes are stored for verification; the plain OTP is kept only until used, solely so the donor / NGO can display it (decision D6).
