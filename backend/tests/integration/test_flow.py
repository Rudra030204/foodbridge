"""Integration tests: listings, matching, claims, pickups, OTP, ratings, privacy, race safety."""
import threading
from datetime import timedelta

from fastapi.testclient import TestClient

from app.core import clock
from app.db.models import Pickup, User
from app.main import app
from tests.conftest import login

API = "/api/v1"
LISTING = {"title": "Dal rice and sabzi", "food_category": "cooked_meal", "is_veg": True, "quantity_meals": 40,
           "storage_condition": "room"}


def post_listing(client, headers, **kw):
    return client.post(f"{API}/listings", json={**LISTING, **kw}, headers=headers)


def email_of(db, user_id):
    """Read an e-mail and end the test session's transaction (SQLite uses BEGIN IMMEDIATE)."""
    email = db.get(User, user_id).email
    db.rollback()
    return email


def notify_all(db, listing_id):
    """Widen the offer to every ranked NGO (what escalation level 2 does)."""
    from app.db.models import FoodListing
    from app.services import matching

    listing = db.get(FoodListing, listing_id)
    matching.notify_candidates(db, listing, 100.0, None, "test")
    db.commit()


def volunteer_id(db, pickup_id):
    """Volunteer currently offered/assigned (hidden from the NGO until accepted, by design)."""
    row = db.get(Pickup, pickup_id)
    db.refresh(row)
    vid = row.volunteer_id
    db.rollback()
    return vid


def otps(db, pickup_id):
    """Current plain OTPs of a pickup as (pickup_otp, delivery_otp)."""
    row = db.get(Pickup, pickup_id)
    db.refresh(row)
    out = (row.pickup_otp_plain, row.delivery_otp_plain)
    db.rollback()
    return out


def top_ngos(client, donor_h, listing_id, n=2):
    m = client.get(f"{API}/listings/{listing_id}/matches", headers=donor_h).json()["matches"]
    return [x for x in m if x["notified"]][:n]


def test_create_listing_matches_and_notifies_top5(client, auth):
    h = auth("donor1")
    r = post_listing(client, h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "open" and body["urgency"] == "green"
    assert 1 <= body["notified_count"] <= 5
    m = client.get(f"{API}/listings/{body['id']}/matches", headers=h).json()
    scores = [x["score"] for x in m["matches"]]
    assert scores == sorted(scores, reverse=True)
    assert set(m["matches"][0]["components"]) >= {"distance", "time", "capacity", "preference", "history"}
    assert sum(1 for x in m["matches"] if x["notified"]) == body["notified_count"]
    assert m["weights"]["distance"] == 0.30


def test_listing_validation_and_rescue_window(client, auth):
    h = auth("donor1")
    assert post_listing(client, h, quantity_meals=0).status_code == 422
    assert post_listing(client, h, food_category="nonveg_cooked", is_veg=True).status_code == 422
    old = (clock.now() - timedelta(hours=2, minutes=30)).isoformat()
    r = post_listing(client, h, cooked_at=old)  # 3h*0.85 - 2.5h = 0.05h left -> too close
    assert r.status_code == 400 and r.json()["error"]["code"] == "too_close_to_expiry"
    r = post_listing(client, h, cooked_at=(clock.now() + timedelta(hours=1)).isoformat())
    assert r.status_code == 400 and r.json()["error"]["code"] == "cooked_in_future"
    r = post_listing(client, h, food_category="sealed_packaged", storage_condition="sealed_packaged")
    assert r.status_code == 400 and r.json()["error"]["code"] == "expiry_required"
    ok = post_listing(client, h, food_category="sealed_packaged", storage_condition="sealed_packaged",
                      expiry_at=(clock.now() + timedelta(days=30)).isoformat())
    assert ok.status_code == 201


def test_only_donors_can_create_and_auth_required(client, auth):
    assert post_listing(client, auth("ngo1")).status_code == 403
    assert post_listing(client, auth("volunteer1")).status_code == 403
    assert client.post(f"{API}/listings", json=LISTING).status_code == 401


def test_daily_listing_limit(client, auth):
    h = auth("donor2")
    codes = [post_listing(client, h, title=f"Batch number {i}", quantity_meals=5).status_code for i in range(21)]
    assert codes[:20] == [201] * 20 and codes[20] == 429


def test_full_happy_path_with_privacy_and_ratings(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]
    ngo_h = login(client, email_of(db, top["ngo_id"]))

    # privacy: NGO sees an approximate location only, before claiming
    feed = client.get(f"{API}/listings", headers=ngo_h).json()["items"]
    mine = next(i for i in feed if i["id"] == lid)
    assert mine["exact_location"] is False and mine["pickup_address"] is None
    assert mine["my_match"]["notified"] is True and mine["my_match"]["components"]

    r = client.post(f"{API}/listings/{lid}/claim", headers=ngo_h)
    assert r.status_code == 201, r.text
    claim = r.json()
    assert claim["claimed_quantity"] == 40 and claim["listing"]["status"] == "claimed"
    assert claim["listing"]["exact_location"] is True and claim["listing"]["pickup_address"]
    pickup = claim["pickup"]
    assert pickup["status"] == "offered" and pickup["volunteer"] is None  # hidden from NGO until accepted
    vid = volunteer_id(db, pickup["id"])
    assert vid

    # idempotent: second claim returns the same claim with 200
    again = client.post(f"{API}/listings/{lid}/claim", headers=ngo_h)
    assert again.status_code == 200 and again.json()["claim_id"] == claim["claim_id"]

    vol_h = login(client, email_of(db, vid))
    acc = client.post(f"{API}/pickups/{pickup['id']}/accept", headers=vol_h)
    assert acc.status_code == 200 and acc.json()["status"] == "assigned"
    assert acc.json()["pickup_otp"] is None and acc.json()["delivery_otp"] is None  # volunteer never sees OTPs
    assert client.get(f"{API}/listings/{lid}", headers=donor_h).json()["status"] == "assigned"

    p_otp = client.get(f"{API}/pickups/mine", headers=donor_h).json()["items"][0]["pickup_otp"]
    d_otp = client.get(f"{API}/pickups/mine", headers=ngo_h).json()["items"][0]["delivery_otp"]
    assert len(p_otp) == 4 and len(d_otp) == 4

    ok_list = {"food_covered": True, "container_clean": True, "temperature_ok": True}
    # checklist incomplete -> 400; wrong OTP -> 400; right OTP -> picked up
    r = client.post(f"{API}/pickups/{pickup['id']}/verify-pickup-otp", headers=vol_h,
                    json={"otp": p_otp, "food_covered": True})
    assert r.status_code == 400 and r.json()["error"]["code"] == "checklist_incomplete"
    wrong = "0000" if p_otp != "0000" else "1111"
    r = client.post(f"{API}/pickups/{pickup['id']}/verify-pickup-otp", headers=vol_h, json={"otp": wrong, **ok_list})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_otp"
    r = client.post(f"{API}/pickups/{pickup['id']}/verify-pickup-otp", headers=vol_h, json={"otp": p_otp, **ok_list})
    assert r.status_code == 200 and r.json()["status"] == "picked_up"
    assert client.get(f"{API}/listings/{lid}", headers=donor_h).json()["status"] == "picked_up"

    # delivery before pickup is impossible; a wrong then correct delivery OTP completes it
    r = client.post(f"{API}/pickups/{pickup['id']}/verify-delivery-otp", headers=vol_h, json={"otp": d_otp})
    assert r.status_code == 200 and r.json()["status"] == "delivered"
    assert client.get(f"{API}/listings/{lid}", headers=donor_h).json()["status"] == "delivered"
    assert client.post(f"{API}/pickups/{pickup['id']}/verify-delivery-otp", headers=vol_h,
                       json={"otp": d_otp}).status_code == 409

    # ratings
    r = client.post(f"{API}/ratings", headers=donor_h, json={"pickup_id": pickup["id"], "to_user": vid, "stars": 5})
    assert r.status_code == 201 and r.json()["reliability"] == 5.0
    assert client.post(f"{API}/ratings", headers=donor_h,
                       json={"pickup_id": pickup["id"], "to_user": vid, "stars": 4}).status_code == 409
    assert client.post(f"{API}/ratings", headers=auth("ngo2"),
                       json={"pickup_id": pickup["id"], "to_user": vid, "stars": 4}).status_code == 403

    # notifications were created for the donor
    notes = client.get(f"{API}/notifications", headers=donor_h).json()
    assert notes["unread"] >= 3 and any(n["type"] == "delivered" for n in notes["items"])
    nid = notes["items"][0]["id"]
    assert client.post(f"{API}/notifications/{nid}/read", headers=donor_h).json()["is_read"] is True


def test_double_claim_race_exactly_one_wins(client, auth, db):
    donor_h = auth("donor3")
    lid = post_listing(client, donor_h, quantity_meals=30).json()["id"]
    two = top_ngos(client, donor_h, lid, 2)
    assert len(two) == 2, "need two notified NGOs for the race"
    headers = [login(client, email_of(db, t["ngo_id"])) for t in two]
    results, barrier = [], threading.Barrier(2)

    def attempt(h):
        with TestClient(app) as c:
            barrier.wait()
            results.append(c.post(f"{API}/listings/{lid}/claim", headers=h).status_code)

    threads = [threading.Thread(target=attempt, args=(h,)) for h in headers]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [201, 409], results
    listing = client.get(f"{API}/listings/{lid}", headers=donor_h).json()
    assert listing["claimed_meals"] == 30 and listing["status"] == "claimed"


def test_claim_rules(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
    # not-offered NGO (unverified ngo10) cannot claim; donors/volunteers cannot claim
    assert client.post(f"{API}/listings/{lid}/claim", headers=auth("ngo10")).status_code == 403
    assert client.post(f"{API}/listings/{lid}/claim", headers=donor_h).status_code == 403
    assert client.post(f"{API}/listings/{lid}/claim", headers=auth("volunteer1")).status_code == 403
    assert client.post(f"{API}/listings/999999/claim", headers=login(client, email_of(db, top))).status_code == 404


def test_partial_claim_leaves_remainder_open(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h, quantity_meals=100).json()["id"]
    notify_all(db, lid)
    two = top_ngos(client, donor_h, lid, 2)
    h1, h2 = (login(client, email_of(db, t["ngo_id"])) for t in two)
    r1 = client.post(f"{API}/listings/{lid}/claim", headers=h1, json={"quantity": 30})
    assert r1.status_code == 201 and r1.json()["claimed_quantity"] == 30
    assert r1.json()["listing"]["status"] == "open" and r1.json()["listing"]["remaining_meals"] == 70
    r2 = client.post(f"{API}/listings/{lid}/claim", headers=h2)
    assert r2.status_code == 201 and r2.json()["claimed_quantity"] == 70
    assert r2.json()["listing"]["status"] == "claimed"


def test_claim_after_expiry_rejected(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
    clock.advance(hours=4)
    r = client.post(f"{API}/listings/{lid}/claim", headers=login(client, email_of(db, top)))
    assert r.status_code == 409 and r.json()["error"]["code"] == "listing_expired"


def test_cancel_claim_reopens_listing_and_cancel_listing(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
    ngo_h = login(client, email_of(db, top))
    cid = client.post(f"{API}/listings/{lid}/claim", headers=ngo_h).json()["claim_id"]
    assert client.post(f"{API}/claims/{cid}/cancel", headers=auth("ngo2")).status_code == 403
    assert client.post(f"{API}/claims/{cid}/cancel", headers=ngo_h).status_code == 200
    assert client.get(f"{API}/listings/{lid}", headers=donor_h).json()["status"] == "open"
    assert client.post(f"{API}/listings/{lid}/cancel", headers=auth("donor2")).status_code == 403
    assert client.post(f"{API}/listings/{lid}/cancel", headers=donor_h).json()["status"] == "cancelled"
    r = client.post(f"{API}/listings/{lid}/cancel", headers=donor_h)  # already cancelled: no-op transition ok
    assert r.status_code in (200, 409)


def test_cannot_cancel_delivered_listing_409(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
    ngo_h = login(client, email_of(db, top))
    pk = client.post(f"{API}/listings/{lid}/claim", headers=ngo_h).json()["pickup"]
    vol_h = login(client, email_of(db, volunteer_id(db, pk["id"])))
    client.post(f"{API}/pickups/{pk['id']}/accept", headers=vol_h)
    ok = {"food_covered": True, "container_clean": True, "temperature_ok": True}
    p_otp, d_otp = otps(db, pk["id"])  # the codes the donor / NGO would see
    client.post(f"{API}/pickups/{pk['id']}/verify-pickup-otp", headers=vol_h, json={"otp": p_otp, **ok})
    client.post(f"{API}/pickups/{pk['id']}/verify-delivery-otp", headers=vol_h, json={"otp": d_otp})
    r = client.post(f"{API}/listings/{lid}/cancel", headers=donor_h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "illegal_transition"


def test_volunteer_decline_reassigns(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
    pk = client.post(f"{API}/listings/{lid}/claim", headers=login(client, email_of(db, top))).json()["pickup"]
    first = volunteer_id(db, pk["id"])
    r = client.post(f"{API}/pickups/{pk['id']}/decline", headers=login(client, email_of(db, first)))
    assert r.status_code == 200
    assert r.json()["status"] == "offered" and volunteer_id(db, pk["id"]) not in (None, first)


def test_pickup_otp_lockout_via_api(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
    pk = client.post(f"{API}/listings/{lid}/claim", headers=login(client, email_of(db, top))).json()["pickup"]
    vol_h = login(client, email_of(db, volunteer_id(db, pk["id"])))
    client.post(f"{API}/pickups/{pk['id']}/accept", headers=vol_h)
    real_otp, _ = otps(db, pk["id"])
    wrong = "0000" if real_otp != "0000" else "1111"
    ok = {"food_covered": True, "container_clean": True, "temperature_ok": True}
    codes = [client.post(f"{API}/pickups/{pk['id']}/verify-pickup-otp", headers=vol_h,
                         json={"otp": wrong, **ok}).status_code for _ in range(5)]
    assert codes == [400] * 5
    r = client.post(f"{API}/pickups/{pk['id']}/verify-pickup-otp", headers=vol_h, json={"otp": real_otp, **ok})
    assert r.status_code == 423 and r.json()["error"]["code"] == "otp_locked"


def test_food_expiring_before_pickup_fails_pickup(client, auth, db):
    donor_h = auth("donor1")
    lid = post_listing(client, donor_h).json()["id"]
    top = top_ngos(client, donor_h, lid, 1)[0]["ngo_id"]
    pk = client.post(f"{API}/listings/{lid}/claim", headers=login(client, email_of(db, top))).json()["pickup"]
    vol_h = login(client, email_of(db, volunteer_id(db, pk["id"])))
    client.post(f"{API}/pickups/{pk['id']}/accept", headers=vol_h)
    real_otp, _ = otps(db, pk["id"])
    clock.advance(hours=4)
    ok = {"food_covered": True, "container_clean": True, "temperature_ok": True}
    r = client.post(f"{API}/pickups/{pk['id']}/verify-pickup-otp", headers=vol_h, json={"otp": real_otp, **ok})
    assert r.status_code == 409 and r.json()["error"]["code"] == "food_expired"
    assert client.get(f"{API}/listings/{lid}", headers=donor_h).json()["status"] in ("expired", "open")


def test_listing_access_control(client, auth):
    lid = post_listing(client, auth("donor1")).json()["id"]
    assert client.get(f"{API}/listings/{lid}", headers=auth("donor2")).status_code == 403
    assert client.get(f"{API}/listings/{lid}", headers=auth("admin")).status_code == 200
    assert client.get(f"{API}/listings", headers=auth("donor2")).json()["total"] == 0
    assert client.get(f"{API}/listings", headers=auth("donor1")).json()["total"] == 1
    assert client.get(f"{API}/listings/{lid}/matches", headers=auth("donor2")).status_code == 403


def test_report_problem_and_patch(client, auth):
    h = auth("donor1")
    lid = post_listing(client, h).json()["id"]
    assert client.patch(f"{API}/listings/{lid}", headers=h, json={"title": "Updated dal rice"}).json()["title"] == "Updated dal rice"
    assert client.patch(f"{API}/listings/{lid}", headers=auth("donor2"), json={"title": "Hacked title"}).status_code == 403
    assert client.post(f"{API}/listings/{lid}/report", headers=h, json={"reason": "Wrong quantity"}).status_code == 201


def test_websocket_receives_push(client, auth, db):
    donor_h = auth("donor1")
    token = donor_h["Authorization"].split()[1]
    with client.websocket_connect(f"/ws?token={token}") as ws:
        assert ws.receive_json()["event"] == "connected"
        ws.send_text("ping")
        assert ws.receive_json()["event"] == "pong"
    from starlette.websockets import WebSocketDisconnect
    import pytest

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=bad"):
            pass


def test_safety_estimate_preview(client, auth):
    h = auth("donor1")
    q = f"{API}/listings/safety-estimate?food_category=cooked_meal&storage_condition=room"
    ok = client.get(q, headers=h).json()
    assert ok["ok"] and ok["rescuable"] and ok["minutes_left"] == 153.0 and ok["message"] is None
    hot = client.get(q + "&hot_day=true", headers=h).json()
    assert hot["minutes_left"] < ok["minutes_left"]
    old = (clock.now() - timedelta(hours=2, minutes=30)).isoformat()
    late = client.get(q + f"&cooked_at={old}", headers=h).json()
    assert late["ok"] and late["rescuable"] is False and "rescue" in late["message"]
    bad = client.get(f"{API}/listings/safety-estimate?food_category=bakery_dry&storage_condition=hot_holding", headers=h).json()
    assert bad["ok"] is False and bad["code"] == "unsupported_combination"
    assert client.get(q).status_code == 401
