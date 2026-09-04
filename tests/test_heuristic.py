import pytest

from quaycrane_evaluation import ScheduleInfeasibleError, build_schedule, check_feasible
from quaycrane_heuristic import (
    balanced_zone_construction,
    build_schedule_robust,
    greedy_and_polish,
    naive_construction,
)
from quaycrane_scenario import generate_instance

SCENARIOS = [
    dict(n_bays=6, n_cranes=1, safety_margin=0, seed=1),
    dict(n_bays=8, n_cranes=2, safety_margin=1, seed=2),
    dict(n_bays=10, n_cranes=3, safety_margin=1, seed=3),
    dict(n_bays=14, n_cranes=4, safety_margin=2, seed=4),
    dict(n_bays=18, n_cranes=5, safety_margin=1, seed=5),
    # safety_margin=3 (max Regler-Wert) mit denselben 18 Bays/5 Kränen zusätzlich als härtester
    # Fall drin - deckte früher eine echte Verletzung auf (siehe
    # test_cp_solver.py::test_heuristics_stay_feasible_at_extreme_settings), seit deren Fix
    # bewusst wieder Teil der regulären Suite statt separat ausgelagert zu sein.
    dict(n_bays=18, n_cranes=5, safety_margin=3, seed=5),
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


def test_instance_detects_trivial_infeasibility_from_slider_ranges():
    """Own finding: the app's own slider ranges (up to 5 cranes, as few as 6 bays, safety margin
    up to 3) allow combinations where the evenly-spaced crane start positions (see
    `generate_instance`) are closer together than the safety margin - then even two motionless,
    parked cranes already violate it, so NO schedule (not even from the exact solver) can ever
    exist. This must be detected up front instead of surfacing as a crash or a silently
    infeasible result."""
    instance = generate_instance(
        n_bays=8, n_cranes=5, moves_avg=12, moves_variability=0.4, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=3, seed=1,
    )
    assert instance.is_trivially_infeasible()
    assert instance.min_crane_gap() < instance.safety_margin

    # A scenario with the same crane/bay ratio but a safety margin that fits stays solvable.
    roomy = generate_instance(
        n_bays=8, n_cranes=5, moves_avg=12, moves_variability=0.4, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=1, seed=1,
    )
    assert not roomy.is_trivially_infeasible()


def test_build_schedule_robust_recovers_from_a_structurally_unschedulable_construction():
    """Own finding: at tight (but not trivially infeasible, see the test above) safety margins,
    `balanced_zone_construction`'s own contiguous-zone crane assignment can occasionally still
    be structurally unschedulable for ANY timing (see `ScheduleInfeasibleError` and
    `build_schedule_robust`'s docstrings) - locks in both halves: the raw construction really
    does fail here (so this regression case stays meaningful), and the robust wrapper recovers a
    genuinely feasible schedule instead of propagating the exception."""
    instance = generate_instance(
        n_bays=14, n_cranes=4, moves_avg=14, moves_variability=0.3, time_per_move=2.0,
        travel_time_per_bay=0.6, safety_margin=3, seed=16,
    )
    assert not instance.is_trivially_infeasible()

    with pytest.raises(ScheduleInfeasibleError):
        build_schedule(instance, balanced_zone_construction(instance))

    tasks = build_schedule_robust(instance, balanced_zone_construction(instance))
    ok, violations = check_feasible(instance, tasks)
    assert ok, violations
