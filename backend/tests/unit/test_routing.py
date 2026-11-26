"""Unit tests: nearest-neighbour + 2-opt routing with precedence and time windows."""
import random
from datetime import datetime, timedelta

import pytest

from app.core.geo import haversine_km
from app.services import routing
from app.services.routing import Stop

NOW = datetime(2026, 6, 1, 6, 30)
START = (28.47, 77.50)


def rnd_stops(rng, n_pickups, deadline=None):
    stops = []
    for i in range(n_pickups):
        stops.append(Stop("pickup", 28.47 + rng.uniform(-.06, .06), 77.50 + rng.uniform(-.06, .06), i, deadline, f"p{i}"))
        stops.append(Stop("delivery", 28.47 + rng.uniform(-.06, .06), 77.50 + rng.uniform(-.06, .06), i, deadline, f"d{i}"))
    return stops


def test_evaluate_distance_is_sum_of_legs_and_has_etas():
    stops = [Stop("pickup", 28.48, 77.50, 1, None, "p"), Stop("delivery", 28.49, 77.52, 1, None, "d")]
    ev = routing.evaluate(START, stops, NOW, speed_kmph=30)
    expected = haversine_km(*START, 28.48, 77.50) + haversine_km(28.48, 77.50, 28.49, 77.52)
    assert ev["distance_km"] == pytest.approx(expected)
    assert ev["etas"][0] < ev["etas"][1] and ev["feasible"] and ev["violations"] == 0
    assert ev["minutes"] > (expected / 30) * 60  # includes 5-minute service time per stop


def test_nearest_neighbor_respects_precedence():
    rng = random.Random(1)
    for _ in range(20):
        order = routing.nearest_neighbor(START, rnd_stops(rng, 4))
        assert routing.precedence_ok(order) and len(order) == 8


def test_precedence_checker_detects_violation():
    p, d = Stop("pickup", 1, 1, 7, None, "p"), Stop("delivery", 2, 2, 7, None, "d")
    assert routing.precedence_ok([p, d]) and not routing.precedence_ok([d, p])
    assert routing.precedence_ok([d])  # picked-up already: delivery alone is fine


def test_two_opt_never_worse_than_nn_and_keeps_precedence():
    rng, improved = random.Random(42), 0
    for _ in range(60):
        stops = rnd_stops(rng, rng.randint(2, 5))
        plan = routing.optimize(START, stops, NOW)
        assert plan["eval"]["distance_km"] <= plan["baseline_eval"]["distance_km"] + 1e-9
        assert routing.precedence_ok(plan["order"]) and sorted(map(id, plan["order"])) == sorted(map(id, stops))
        improved += plan["eval"]["distance_km"] < plan["baseline_eval"]["distance_km"] - 1e-9
    assert improved >= 5, "2-opt should strictly improve a fair share of random scenarios"


def test_two_opt_prefers_feasibility_over_distance():
    near = Stop("delivery", 28.4705, 77.5005, 1, NOW + timedelta(hours=5), "near-late-ok")
    far_urgent = Stop("delivery", 28.52, 77.55, 2, NOW + timedelta(minutes=20), "far-urgent")
    # NN visits the near stop first and then misses the urgent deadline; 2-opt reorders to meet it.
    nn = routing.nearest_neighbor(START, [near, far_urgent])
    assert nn[0] is near
    base = routing.evaluate(START, nn, NOW)
    plan = routing.optimize(START, [near, far_urgent], NOW)
    assert plan["eval"]["violations"] <= base["violations"]
    assert plan["order"][0] is far_urgent and plan["eval"]["feasible"]


def test_infeasible_route_is_flagged():
    s = Stop("delivery", 28.9, 77.9, 1, NOW + timedelta(minutes=5), "impossible")
    assert routing.optimize(START, [s], NOW)["eval"]["feasible"] is False


def test_empty_and_single_stop():
    assert routing.optimize(START, [], NOW)["order"] == []
    s = Stop("pickup", 28.48, 77.5, 1, None, "p")
    assert routing.optimize(START, [s], NOW)["order"] == [s]
