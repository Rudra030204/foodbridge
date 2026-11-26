"""Integration tests for FR-1 (auth and accounts)."""
from app.core import ratelimit

API = "/api/v1"

DONOR = {
    "name": "New Donor", "email": "new.donor@example.com", "password": "Passw0rdX", "phone": "9999999999",
    "role": "donor",
    "donor": {"org_name": "Test Hostel", "donor_type": "hostel", "address": "Sector 1", "lat": 28.47, "lng": 77.5},
}
NGO = {
    "name": "New NGO", "email": "new.ngo@example.com", "password": "Passw0rdX", "role": "ngo",
    "ngo": {"org_name": "Test NGO", "address": "Sector 2", "lat": 28.48, "lng": 77.51, "daily_capacity_meals": 100},
}
VOL = {
    "name": "New Vol", "email": "new.vol@example.com", "password": "Passw0rdX", "role": "volunteer",
    "volunteer": {"vehicle_type": "bike", "capacity_meals": 30, "home_lat": 28.47, "home_lng": 77.5},
}


def test_register_each_role(client):
    for body, role in ((DONOR, "donor"), (NGO, "ngo"), (VOL, "volunteer")):
        r = client.post(f"{API}/auth/register", json=body)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["user"]["role"] == role
        assert data["profile"] is not None
        assert "password" not in str(data).lower() or "password_hash" not in str(data)


def test_donor_and_ngo_start_unverified_volunteer_verified(client):
    assert client.post(f"{API}/auth/register", json=DONOR).json()["user"]["is_verified"] is False
    assert client.post(f"{API}/auth/register", json=NGO).json()["user"]["is_verified"] is False
    assert client.post(f"{API}/auth/register", json=VOL).json()["user"]["is_verified"] is True


def test_cannot_self_register_as_admin(client):
    body = dict(DONOR, role="admin")
    assert client.post(f"{API}/auth/register", json=body).status_code == 422


def test_register_requires_matching_profile(client):
    body = {k: v for k, v in DONOR.items() if k != "donor"}
    r = client.post(f"{API}/auth/register", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_duplicate_email_conflict(client):
    assert client.post(f"{API}/auth/register", json=DONOR).status_code == 201
    r = client.post(f"{API}/auth/register", json=DONOR)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_taken"


def test_weak_password_rejected(client):
    r = client.post(f"{API}/auth/register", json=dict(DONOR, password="onlyletters"))
    assert r.status_code == 422


def test_ngo_must_accept_some_food_type(client):
    bad = dict(NGO, ngo=dict(NGO["ngo"], accepts_veg=False, accepts_nonveg=False))
    assert client.post(f"{API}/auth/register", json=bad).status_code == 422


def test_login_me_refresh_logout(client):
    client.post(f"{API}/auth/register", json=DONOR)
    r = client.post(f"{API}/auth/login", json={"email": DONOR["email"], "password": DONOR["password"]})
    assert r.status_code == 200
    tokens = r.json()
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200 and me.json()["user"]["email"] == DONOR["email"]
    assert me.json()["profile"]["org_name"] == "Test Hostel"

    r2 = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 200 and r2.json()["access_token"]

    assert client.post(f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
    r3 = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r3.status_code == 401


def test_access_token_cannot_be_used_as_refresh(client):
    tokens = client.post(f"{API}/auth/login", json={"email": "donor1@demo.com", "password": "Demo@1234"}).json()
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert r.status_code == 401


def test_wrong_password_and_unknown_user(client):
    r = client.post(f"{API}/auth/login", json={"email": "donor1@demo.com", "password": "Wrong@123"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    r = client.post(f"{API}/auth/login", json={"email": "nobody@demo.com", "password": "Wrong@123"})
    assert r.status_code == 401


def test_me_requires_auth(client):
    r = client.get(f"{API}/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    r = client.get(f"{API}/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_login_rate_limit(client):
    ratelimit.reset()
    codes = [
        client.post(f"{API}/auth/login", json={"email": "donor1@demo.com", "password": "Bad@12345"}).status_code
        for _ in range(12)
    ]
    assert codes[:10] == [401] * 10
    assert 429 in codes[10:]


def test_update_profile(client, auth):
    h = auth("ngo1")
    new = {"org_name": "Roti Bank Noida", "address": "New address", "lat": 28.5, "lng": 77.5,
           "daily_capacity_meals": 555, "accepts_veg": True, "accepts_nonveg": False}
    r = client.put(f"{API}/auth/me", json={"name": "Renamed", "ngo": new}, headers=h)
    assert r.status_code == 200
    assert r.json()["user"]["name"] == "Renamed"
    assert r.json()["profile"]["daily_capacity_meals"] == 555
    assert r.json()["profile"]["accepts_nonveg"] is False


def test_suspended_user_cannot_login(client, db):
    from app.db.models import User

    u = db.query(User).filter_by(email="donor2@demo.com").one()
    u.is_active = False
    db.commit()
    r = client.post(f"{API}/auth/login", json={"email": "donor2@demo.com", "password": "Demo@1234"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_suspended"
