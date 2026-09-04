import pytest

from quaycrane_evaluation import build_schedule, check_feasible
from quaycrane_heuristic import balanced_zone_construction, greedy_and_polish, naive_construction
from quaycrane_scenario import generate_instance

SCENARIOS = [
    dict(n_bays=6, n_cranes=1, safety_margin=0, seed=1),
    dict(n_bays=8, n_cranes=2, safety_margin=1, seed=2),
    dict(n_bays=10, n_cranes=3, safety_margin=1, seed=3),
    dict(n_bays=14, n_cranes=4, safety_margin=2, seed=4),
    dict(n_bays=18, n_cranes=5, safety_margin=1, seed=5),
    # safety_margin=3 (max Regler-Wert) mit denselben 18 Bays/5 Kränen ist bewusst NICHT
    # hier drin - siehe test_cp_solver.py::test_exact_stays_feasible_where_heuristics_can_fail
    # für die dokumentierte Einschränkung.
]


@pytest.mark.parametrize("params", SCENARIOS)
def test_all_methods_feasible(params):
    instance = generate_instance(
        n_bays=params["n_bays"],
        n_cranes=params["n_cranes"],
        moves_avg=12,
        moves_variability=0.4,
        time_per_move=2.0,
        travel_time_per_bay=0.5,
        safety_margin=params["safety_margin"],
        seed=params["seed"],
    )
    for order in [naive_construction(instance), balanced_zone_construction(instance), greedy_and_polish(instance)]:
        tasks = build_schedule(instance, order)
        ok, violations = check_feasible(instance, tasks)
        assert ok, violations
        assert set(tasks.keys()) == set(range(instance.n_bays))


@pytest.mark.parametrize("params", SCENARIOS)
def test_polish_never_worse_than_best_construction(params):
    instance = generate_instance(
        n_bays=params["n_bays"],
        n_cranes=params["n_cranes"],
        moves_avg=12,
        moves_variability=0.4,
        time_per_move=2.0,
        travel_time_per_bay=0.5,
        safety_margin=params["safety_margin"],
        seed=params["seed"],
    )
    naive_ms = max(t.end for t in build_schedule(instance, naive_construction(instance)).values())
    zone_ms = max(t.end for t in build_schedule(instance, balanced_zone_construction(instance)).values())
    polish_ms = max(t.end for t in build_schedule(instance, greedy_and_polish(instance)).values())
    assert polish_ms <= min(naive_ms, zone_ms) + 1e-6


def test_balanced_zone_gives_every_crane_at_least_one_bay():
    instance = generate_instance(
        n_bays=6, n_cranes=5, moves_avg=10, moves_variability=0.9, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=1, seed=9,
    )
    order = balanced_zone_construction(instance)
    cranes_used = {crane for _, crane in order}
    assert cranes_used == set(range(instance.n_cranes))
