"""Integration tests: analytics, prediction, admin APIs, seed history."""
import pytest

from app.db.models import AuditLog, FoodListing, FoodSafetyRule, Pickup, SurplusHistory
from app.services.seed_history import seed_history
from tests.conftest import login
from tests.integration.test_flow import API, email_of, post_listing, top_ngos


@pytest.fixture()
def history(db):
    out = seed_history(db)
    db.commit()
    return out


def test_seed_history_is_idempotent(db, history):
    assert history["history_listings"] == 120 and history["surplus_rows"] > 5000
    assert db.query(SurplusHistory).filter_by(is_synthetic=True).count() == history["surplus_rows"]
    assert db.query(FoodListing).count() == 120
    again = seed_history(db)
    db.commit()
    assert again == {"surplus_rows": 0, "history_listings": 0}
    assert db.query(FoodListing).count() == 120


def test_public_and_scoped_impact(client, auth, history):
    pub = client.get(f"{API}/analytics/public").json()
    assert pub["meals_rescued"] > 0 and pub["kg_saved"] > 0 and "active_listings" in pub
    admin = client.get(f"{API}/analytics/impact", headers=auth("admin")).json()
    assert admin["kg_saved"] == pytest.approx((admin["meals_rescued"] + admin["meals_diverted"]) * 0.4, abs=0.1)
    assert admin["co2e_avoided_kg"] == pytest.approx(admin["kg_saved"] * 2.5, abs=0.2)
    assert 0 < admin["delivery_success_rate"] <= 1 and admin["avg_time_to_claim_min"] > 0
    assert 0 <= admin["escalation_rate"] <= 1 and admin["listings_total"] == 120
    d1 = client.get(f"{API}/analytics/impact", headers=auth("donor1")).json()
    assert d1["listings_total"] <= admin["listings_total"]
    # donors cannot peek at someone else's numbers by passing donor_id
    other = client.get(f"{API}/analytics/impact?donor_id=3", headers=auth("donor1")).json()
    assert other["listings_total"] == d1["listings_total"]
    assert client.get(f"{API}/analytics/impact", headers=auth("volunteer1")).status_code == 403
    assert client.get(f"{API}/analytics/impact").status_code == 401
    flt = client.get(f"{API}/analytics/impact?date_from=2999-01-01T00:00:00", headers=auth("admin")).json()
    assert flt["listings_total"] == 0 and flt["meals_rescued"] == 0


def test_csv_export_and_performance(client, auth, history):
    r = client.get(f"{API}/analytics/export.csv", headers=auth("admin"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0] == "date,meals_rescued,kg_saved,co2e_avoided_kg" and lines[-1].startswith("TOTAL")
    perf = client.get(f"{API}/analytics/performance", headers=auth("admin")).json()
    assert set(perf["by_escalation_level"]) == {"0", "1", "2", "3"} and perf["avg_claim_to_delivery_min"] > 0
    assert client.get(f"{API}/analytics/performance", headers=auth("donor1")).status_code == 403


def test_forecast_structure_and_retrain(client, auth, history):
    f = client.get(f"{API}/predictions/forecast", headers=auth("ngo1"))
    assert f.status_code == 200, f.text
    data = f.json()
    assert data["is_synthetic"] is True and "synthetic" in data["note"].lower()
    assert len(data["cells"]) >= 3
    for cell in data["cells"]:
        assert len(cell["days"]) == 7 and all(d["expected_meals"] >= 0 for d in cell["days"])
        assert cell["week_total"] == pytest.approx(sum(d["expected_meals"] for d in cell["days"]), abs=0.5)
    m = data["metrics"]
    for k in ("gradient_boosting", "naive_last_week", "moving_average_7d"):
        assert m[k]["mae"] > 0 and m[k]["rmse"] >= m[k]["mae"]
    assert m["gradient_boosting"]["mae"] < m["moving_average_7d"]["mae"]  # beats the moving-average baseline
    assert client.post(f"{API}/predictions/retrain", headers=auth("ngo1")).status_code == 403
    assert client.post(f"{API}/predictions/retrain", headers=auth("admin")).status_code == 200
    assert client.get(f"{API}/predictions/forecast", headers=auth("volunteer1")).status_code == 403


def test_forecast_without_history_is_a_clear_error(client, auth):
    import os
    from pathlib import Path

    p = Path(os.environ["MODEL_PATH"])
    p.unlink(missing_ok=True)
    r = client.get(f"{API}/predictions/forecast", headers=auth("ngo1"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_history"


def test_admin_endpoints_require_admin(client, auth):
    for path in ("/admin/users", "/admin/verifications", "/admin/safety-rules", "/admin/match-weights",
                 "/admin/audit-log", "/admin/health", "/admin/fallback-partners", "/admin/reports"):
        assert client.get(f"{API}{path}", headers=auth("donor1")).status_code == 403, path
        assert client.get(f"{API}{path}").status_code == 401, path
        assert client.get(f"{API}{path}", headers=auth("admin")).status_code == 200, path


def test_verification_flow_unlocks_claiming(client, auth, db):
    admin_h = auth("admin")
    queue = client.get(f"{API}/admin/verifications", headers=admin_h).json()["items"]
    assert {u["email"] for u in queue} == {"donor14@demo.com", "donor15@demo.com", "ngo10@demo.com"}
    ngo10 = next(u for u in queue if u["email"] == "ngo10@demo.com")
    assert client.post(f"{API}/admin/verifications/{ngo10['id']}", headers=admin_h, json={"approve": True}).json()["is_verified"]
    assert not any(u["email"] == "ngo10@demo.com" for u in client.get(f"{API}/admin/verifications", headers=admin_h).json()["items"])
    donor14 = next(u for u in queue if u["email"] == "donor14@demo.com")
    r = client.post(f"{API}/admin/verifications/{donor14['id']}", headers=admin_h, json={"approve": False})
    assert r.json()["is_active"] is False
    assert client.post(f"{API}/auth/login", json={"email": "donor14@demo.com", "password": "Demo@1234"}).status_code == 403


def test_unverified_donor_listing_has_badge(client, auth):
    out = post_listing(client, auth("donor14")).json()
    assert out["donor_verified"] is False


def test_match_weights_validation_and_effect(client, auth, db):
    admin_h = auth("admin")
    bad = {"distance": 0.5, "time": 0.5, "capacity": 0.5, "preference": 0, "history": 0}
    assert client.put(f"{API}/admin/match-weights", headers=admin_h, json=bad).json()["error"]["code"] == "weights_sum"
    ok = {"distance": 1.0, "time": 0, "capacity": 0, "preference": 0, "history": 0}
    assert client.put(f"{API}/admin/match-weights", headers=admin_h, json=ok).status_code == 200
    h = auth("donor1")
    lid = post_listing(client, h).json()["id"]
    m = client.get(f"{API}/listings/{lid}/matches", headers=h).json()
    assert m["weights"]["distance"] == 1.0
    dists = [x["distance_km"] for x in m["matches"]]
    assert dists == sorted(dists)  # pure-distance weighting ranks the closest NGO first


def test_safety_rule_editor_changes_new_listings(client, auth, db):
    admin_h = auth("admin")
    r = client.post(f"{API}/admin/safety-rules", headers=admin_h,
                    json={"food_category": "cooked_meal", "storage_condition": "room", "safe_hours": 1.2})
    assert r.status_code == 200
    out = post_listing(client, auth("donor1")).json()
    assert out["minutes_left"] == pytest.approx(61.2, abs=0.2)  # 1.2 h * 0.85 buffer = 61.2 min, clock frozen
    assert client.post(f"{API}/admin/safety-rules", headers=admin_h,
                       json={"food_category": "cooked_meal", "storage_condition": "nope", "safe_hours": 2}).status_code == 400
    assert client.post(f"{API}/admin/safety-rules/reset", headers=admin_h).json()["reset"] == 1
    assert db.query(FoodSafetyRule).filter_by(food_category="cooked_meal", storage_condition="room").one().safe_hours == 3.0


def test_suspend_and_activate_user(client, auth, db):
    admin_h = auth("admin")
    from app.db.models import User

    donor2 = db.query(User).filter_by(email="donor2@demo.com").one().id
    admin_id = db.query(User).filter_by(email="admin@demo.com").one().id
    db.rollback()
    assert client.post(f"{API}/admin/users/{admin_id}/suspend", headers=admin_h).status_code == 400
    assert client.post(f"{API}/admin/users/{donor2}/suspend", headers=admin_h).json()["is_active"] is False
    assert client.post(f"{API}/auth/login", json={"email": "donor2@demo.com", "password": "Demo@1234"}).status_code == 403
    assert client.post(f"{API}/admin/users/{donor2}/activate", headers=admin_h).json()["is_active"] is True
    assert client.post(f"{API}/admin/users/99999/suspend", headers=admin_h).status_code == 404
    found = client.get(f"{API}/admin/users?q=donor2", headers=admin_h).json()["items"]
    assert [u["email"] for u in found] == ["donor2@demo.com"]


def test_fallback_partner_toggle_audit_and_health(client, auth, db):
    admin_h = auth("admin")
    from app.db.models import User

    ngo1 = db.query(User).filter_by(email="ngo1@demo.com").one().id
    db.rollback()
    assert client.put(f"{API}/admin/ngos/{ngo1}/fallback", headers=admin_h, json={"is_fallback_partner": True}).json()["is_fallback_partner"]
    log = client.get(f"{API}/admin/audit-log?action=set_fallback_partner", headers=admin_h).json()["items"]
    assert len(log) == 1 and log[0]["entity_id"] == ngo1
    from app.services import escalation

    escalation.run_cycle(db)
    db.commit()
    health = client.get(f"{API}/admin/health", headers=admin_h).json()
    assert health["status"] == "ok" and health["scheduler"]["last_run"] and health["time_scale"] == 1.0


def test_problem_report_resolution(client, auth):
    h = auth("donor1")
    lid = post_listing(client, h).json()["id"]
    client.post(f"{API}/listings/{lid}/report", headers=h, json={"reason": "Food looks wrong"})
    admin_h = auth("admin")
    reports = client.get(f"{API}/admin/reports?status=open", headers=admin_h).json()["items"]
    assert len(reports) == 1
    assert client.post(f"{API}/admin/reports/{reports[0]['id']}/resolve", headers=admin_h).json()["status"] == "resolved"
