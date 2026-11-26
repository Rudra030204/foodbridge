# UML

## Use cases
```mermaid
flowchart LR
    Donor([Donor]) --- UC1(Post surplus food)
    Donor --- UC2(Track listing, countdown, escalation)
    Donor --- UC3(Hand pickup OTP to volunteer)
    NGO([NGO]) --- UC4(View ranked offers + why)
    NGO --- UC5(Claim full or partial quantity)
    NGO --- UC6(Confirm delivery OTP)
    Vol([Volunteer]) --- UC7(Accept / decline job)
    Vol --- UC8(Follow optimised route)
    Vol --- UC9(Verify pickup + safety checklist)
    Admin([Admin]) --- UC10(Verify donors and NGOs)
    Admin --- UC11(Edit safety rules and match weights)
    Admin --- UC12(Monitor KPIs, reports, audit log)
    UC1 -. includes .-> UCS(Compute safe-until time)
    UC5 -. includes .-> UCL(Atomic first-wins lock)
    UC2 -. extends .-> UCE(Auto-escalation)
```

## Sequence: post, match, claim, deliver
```mermaid
sequenceDiagram
    actor Donor
    actor NGO
    actor Vol as Volunteer
    participant API
    participant DB
    participant Sch as Scheduler
    Donor->>API: POST /listings
    API->>DB: safe_until = cooked_at + rule hours
    API->>DB: score and rank NGOs, store components
    API-->>NGO: notification (WebSocket + in-app + mock SMS)
    NGO->>API: POST /listings/{id}/claim
    API->>DB: lock listing row, check remaining, create claim + pickup
    API-->>NGO: 201 (loser of a race gets 409)
    API->>DB: pick nearest available volunteer
    API-->>Vol: job offered
    Vol->>API: POST /pickups/{id}/accept, then /start
    Donor-->>Vol: tells 4-digit pickup OTP
    Vol->>API: verify-pickup-otp + checklist
    NGO-->>Vol: tells 4-digit delivery OTP
    Vol->>API: verify-delivery-otp
    API->>DB: pickup delivered, listing delivered, OTPs wiped
    Note over Sch,DB: Every tick: escalate unclaimed listings, expire, warn, retry unassigned pickups
```

## State machine: listing (`services/state.py`)
```mermaid
stateDiagram-v2
    [*] --> open
    open --> claimed
    open --> diverted
    open --> expired
    open --> cancelled
    claimed --> assigned
    claimed --> open
    claimed --> cancelled
    diverted --> assigned
    diverted --> open
    diverted --> cancelled
    assigned --> picked_up
    assigned --> claimed
    assigned --> diverted
    assigned --> open
    assigned --> cancelled
    picked_up --> delivered
    delivered --> [*]
    expired --> [*]
    cancelled --> [*]
```
Illegal transitions raise HTTP 409 `illegal_transition`.

## State machine: pickup (`services/lifecycle.py`)
```mermaid
stateDiagram-v2
    [*] --> pending_assignment
    pending_assignment --> offered: volunteer chosen
    offered --> assigned: accept
    offered --> pending_assignment: decline / timeout
    assigned --> en_route: start
    assigned --> pending_assignment: volunteer drops
    en_route --> picked_up: pickup OTP + checklist
    picked_up --> delivered: delivery OTP
    pending_assignment --> cancelled: claim cancelled
    offered --> cancelled
    assigned --> cancelled
    en_route --> failed: food no longer safe
    picked_up --> failed
    delivered --> [*]
```
After 5 wrong OTP attempts the pickup is locked for 10 minutes.

## Class view (services)
```mermaid
classDiagram
    class SafetyService { +compute_safe_until(category, storage, cooked_at, hot_day, expiry) }
    class MatchingService { +rank_ngos(listing) +get_weights() }
    class LifecycleService { +claim() +accept_pickup() +verify_pickup_otp() +verify_delivery_otp() +cancel_claim() }
    class EscalationService { +target_level(age, minutes_left) +run_cycle() }
    class RoutingService { +plan_route_for_volunteer() 2-opt with deadline feasibility }
    class PredictionService { +train() +forecast(days) }
    class NotifierService { +notify(user, type, title, body) }
    LifecycleService --> SafetyService
    LifecycleService --> RoutingService
    EscalationService --> MatchingService
    EscalationService --> LifecycleService
    MatchingService --> NotifierService
    EscalationService --> NotifierService
```
