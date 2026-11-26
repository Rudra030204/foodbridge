"""Integration tests: escalation, expiry, warnings, re-assignment, routing, batching."""
from datetime import timedelta

from sqlalchemy import select, update

from app.core import clock
from app.db.models import EscalationEvent, FoodListing, ListingMatchScore, Notification, Pickup, VolunteerProfile
from app.services import escalation
from tests.conftest import login
from tests.integration.test_flow import API, email_of, notify_all, otps, post_listing, top_ngos, volunteer_id


def cycle(db):
    out = escalation.run_cycle(db)
    db.commit()
    return out


def level_of(db, lid):
    lvl = db.get(FoodListing, lid)
    db.refresh(lvl)
    out = (lvl.escalation_level, lvl.status)
    db.rollback()
    return out


def test_target_level_function():
    assert escalation.target_level(0, 150) == 0
    assert escalation.target_level(10, 150) == 1
    assert escalation.target_level(20, 150) == 2
    assert escalation.target_level(30, 150) == 3
    assert escalation.target_level(1, 44) == 3  # little safe time left -> straight to final level


def test_escalation_progresses_through_levels(client, auth, db):
    donor_h = auth("donor1")
    body = post_listing(client, donor_h).json()
    lid, first_notified = body["id"], body["notified_count"]
    assert cycle(db)["escalations"] == 0 and level_of(db, lid)[0] == 0

    clock.advance(minutes=11)
    assert cycle(db)["escalations"] >= 1 and level_of(db, lid)[0] == 1
    clock.advance(minutes=10)
    cycle(db)
    assert level_of(db, lid)[0] == 2
    clock.advance(minutes=10)
    cycle(db)
    assert level_of(db, lid)[0] == 3

    events = db.scalars(select(EscalationEvent).where(EscalationEvent.listing_id == lid).order_by(EscalationEvent.level)).all()
    assert [e.level for e in events] == [0, 1, 2, 3]
    assert events[1].radius_km == 6.0 and events[2].radius_km == 12.0
    assert len(events[3].notified_ngo_ids) == 2  # both fallback partners
    notified_total = db.scalar(select(ListingMatchScore).where(ListingMatchScore.listing_id == lid).with_only_columns(
        ListingMatchScore.id).where(ListingMatchScore.notified_at.is_not(None)).order_by(None).limit(1))
    assert notified_total is not None and first_notified >= 0
    db.rollback()
    cycle(db)  # idempotent: nothing more to do
    assert db.scalar(select(EscalationEvent.id).where(EscalationEvent.listing_id == lid, EscalationEvent.level == 3))
    db.rollback()


def test_widened_radius_lets_more_ngos_claim(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    before = {m["ngo_id"] for m in client.get(f"{API}/listings/{lid}/matches", headers=donor_h).json()["matches"] if m["notified"]}
    clock.advance(minutes=21)
    cycle(db)
    after = {m["ngo_id"] for m in client.get(f"{API}/listings/{lid}/matches", headers=donor_h).json()["matches"] if m["notified"]}
    assert before < after  # strictly more organisations were offered the food


def test_fallback_partner_can_claim_only_at_final_level_and_status_is_diverted(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    fb = auth("ngo11")
    assert client.post(f"{API}/listings/{lid}/claim", headers=fb).status_code == 403  # not offered yet
    clock.advance(minutes=31)
    cycle(db)
    r = client.post(f"{API}/listings/{lid}/claim", headers=fb)
    assert r.status_code == 201, r.text
    assert r.json()["is_diversion"] is True and r.json()["listing"]["status"] == "diverted"


def test_low_remaining_time_jumps_to_level_three_applying_all_levels(client, auth, db):
    donor_h = auth("donor1")
    cooked = (clock.now() - timedelta(hours=1, minutes=45)).isoformat()  # ~48 min of safe time left
    lid = post_listing(client, donor_h, cooked_at=cooked).json()["id"]
    clock.advance(minutes=5)  # now < 45 min left
    cycle(db)
    assert level_of(db, lid)[0] == 3
    levels = [e.level for e in db.scalars(select(EscalationEvent).where(EscalationEvent.listing_id == lid).order_by(EscalationEvent.id))]
    db.rollback()
    assert levels == [0, 1, 2, 3]


def test_expiry_marks_listing_expired_and_notifies_donor(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    clock.advance(hours=3)
    out = cycle(db)
    assert out["expired"] == 1
    assert level_of(db, lid)[1] == "expired"
    assert any(n["type"] == "listing_expired" for n in client.get(f"{API}/notifications", headers=donor_h).json()["items"])


def test_expiry_warning_sent_once(client, auth, db):
    donor_h = auth("donor1")
    post_listing(client, donor_h)
    clock.advance(hours=2, minutes=5)  # safe window is 2h33m -> about 28 min left
    assert cycle(db)["warnings"] == 1
    assert cycle(db)["warnings"] == 0
    items = client.get(f"{API}/notifications", headers=donor_h).json()["items"]
    assert sum(1 for n in items if n["type"] == "expiry_warning") == 1


def test_stale_pickup_is_failed_and_listing_expires(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
    pk = client.post(f"{API}/listings/{lid}/claim", headers=login(client, email_of(db, top))).json()["pickup"]
    clock.advance(hours=3)
    out = cycle(db)
    assert out["pickups_failed"] == 1
    row = db.get(Pickup, pk["id"])
    db.refresh(row)
    status = row.status
    db.rollback()
    assert status == "failed" and level_of(db, lid)[1] == "expired"


def test_unassigned_pickup_is_retried_when_volunteer_returns(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
    db.execute(update(VolunteerProfile).values(is_available=False))
    db.commit()
    pk = client.post(f"{API}/listings/{lid}/claim", headers=login(client, email_of(db, top))).json()["pickup"]
    assert pk["status"] == "pending_assignment"
    assert cycle(db)["reassigned"] == 0
    db.execute(update(VolunteerProfile).values(is_available=True))
    db.commit()
    assert cycle(db)["reassigned"] == 1
    assert volunteer_id(db, pk["id"]) is not None


def test_route_is_planned_on_accept_and_volunteer_endpoint(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
    pk = client.post(f"{API}/listings/{lid}/claim", headers=login(client, email_of(db, top))).json()["pickup"]
    vol_h = login(client, email_of(db, volunteer_id(db, pk["id"])))
    assert client.get(f"{API}/pickups/{pk['id']}/route", headers=vol_h).status_code == 404  # not accepted yet
    client.post(f"{API}/pickups/{pk['id']}/accept", headers=vol_h)
    r = client.get(f"{API}/pickups/{pk['id']}/route", headers=vol_h).json()
    kinds = [s["kind"] for s in r["stops"]]
    assert kinds == ["pickup", "delivery"] and r["feasible"] and r["total_distance_km"] > 0
    assert r["stops"][0]["eta"] < r["stops"][1]["eta"]
    mine = client.get(f"{API}/volunteers/me/route", headers=vol_h).json()
    assert len(mine["stops"]) == 2
    # location update re-plans using the new position
    moved = client.put(f"{API}/volunteers/me/location", headers=vol_h, json={"lat": 28.50, "lng": 77.52})
    assert moved.status_code == 200
    p_otp, d_otp = otps(db, pk["id"])
    ok = {"food_covered": True, "container_clean": True, "temperature_ok": True}
    client.post(f"{API}/pickups/{pk['id']}/verify-pickup-otp", headers=vol_h, json={"otp": p_otp, **ok})
    after_pickup = client.get(f"{API}/volunteers/me/route", headers=vol_h).json()
    assert [s["kind"] for s in after_pickup["stops"]] == ["delivery"]
    client.post(f"{API}/pickups/{pk['id']}/verify-delivery-otp", headers=vol_h, json={"otp": d_otp})
    assert client.get(f"{API}/volunteers/me/route", headers=vol_h).json()["stops"] == []


def test_nearby_claims_are_batched_onto_one_volunteer_and_route(client, auth, db):
    donor_h = auth("donor1")
    vols, claims = [], []
    for i in range(2):
        lid = post_listing(client, donor_h, title=f"Batch lunch {i}", quantity_meals=10).json()["id"]
        top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
        pk = client.post(f"{API}/listings/{lid}/claim", headers=login(client, email_of(db, top))).json()["pickup"]
        vid = volunteer_id(db, pk["id"])
        client.post(f"{API}/pickups/{pk['id']}/accept", headers=login(client, email_of(db, vid)))
        vols.append(vid)
        claims.append(pk["id"])
    assert vols[0] == vols[1], "second pickup next to the first should go to the same volunteer"
    route = client.get(f"{API}/volunteers/me/route", headers=login(client, email_of(db, vols[0]))).json()
    assert len(route["stops"]) == 4
    seen = set()
    for s in route["stops"]:  # precedence holds in the stored plan
        if s["kind"] == "delivery":
            assert s["pickup_id"] in seen
        else:
            seen.add(s["pickup_id"])
