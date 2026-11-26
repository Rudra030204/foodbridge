# Data flow diagrams

## Level 0 (context)
```mermaid
flowchart LR
    D([Donor]) -- "surplus listing, pickup OTP" --> FB((FoodBridge Plus))
    FB -- "match alerts, claim status, impact stats" --> D
    N([NGO]) -- "claim, delivery OTP" --> FB
    FB -- "offers, volunteer details" --> N
    V([Volunteer]) -- "availability, location, OTP entries" --> FB
    FB -- "job offers, route" --> V
    A([Admin]) -- "verification, rules, weights" --> FB
    FB -- "KPIs, reports, audit log" --> A
    FB -- "SMS / WhatsApp (mock)" --> X([Messaging providers])
```

## Level 1
```mermaid
flowchart TB
    D([Donor]) --> P1["1. Safety check<br/>compute safe_until"]
    P1 --> DS1[("food_listings, food_safety_rules")]
    DS1 --> P2["2. Match & notify<br/>score and rank NGOs"]
    P2 --> DS2[("listing_match_scores, notifications")]
    DS2 --> N([NGO])
    N --> P3["3. Claim<br/>atomic first-wins"]
    P3 --> DS3[("claims, pickups")]
    DS3 --> P4["4. Assign & route<br/>volunteer offer, 2-opt route"]
    P4 --> DS4[("routes")]
    V([Volunteer]) --> P5["5. Pickup & delivery<br/>OTP + safety checklist"]
    DS3 --> P5
    P5 --> DS3
    SCH[Scheduler] --> P6["6. Escalate / expire<br/>L1 6 km, L2 12 km, L3 fallback"]
    DS1 --> P6
    P6 --> DS5[("escalation_events")]
    P6 --> P2
    DS1 & DS3 --> P7["7. Impact & forecast"]
    P7 --> A([Admin / dashboards])
```
