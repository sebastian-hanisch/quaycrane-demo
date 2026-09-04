import pytest

from quaycrane_cp_solver import solve_exact
from quaycrane_evaluation import build_schedule, check_feasible, evaluate
from quaycrane_heuristic import greedy_and_polish
from quaycrane_scenario import generate_instance

SCENARIOS = [
    dict(n_bays=6, n_cranes=1, safety_margin=0, seed=1),
    dict(n_bays=6, n_cranes=2, safety_margin=1, seed=2),
    dict(n_bays=8, n_cranes=3, safety_margin=2, seed=3),
]


@pytest.mark.parametrize("params", SCENARIOS)
def test_exact_solution_feasible_and_is_lower_bound(params):
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

    result = solve_exact(instance, time_limit_seconds=10)
    assert result.feasible
    ok, violations = check_feasible(instance, result.tasks)
    assert ok, violations

    heuristic_tasks = build_schedule(instance, greedy_and_polish(instance))
    heuristic_makespan = max(t.end for t in heuristic_tasks.values())

    if result.optimal:
        assert result.makespan <= heuristic_makespan + 1e-6


def test_exact_solution_has_no_spurious_wait():
    """CP-SAT's parallel search can land on any one of several equally optimal-makespan
    solutions; without a tie-breaking secondary objective, nothing in the model prefers the
    ones without gratuitous idling on a non-critical crane over ones with it (a user reported
    exactly this: the "Mittleres Schiff" preset sometimes showed the exact solver waiting at
    the start even though the cranes looked far apart on the chart - reproduced by solving the
    same instance repeatedly and finding the reported wait time varied between 0.0 and 1.1
    minutes while the makespan stayed the same optimal value every time). Regression test for
    the fix: solve several times, the makespan must stay optimal and the wait time must stay
    at (numerically) zero every time."""
    instance = generate_instance(
        n_bays=12, n_cranes=3, moves_avg=14, moves_variability=0.4, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=1, seed=7,
    )
    makespans = set()
    for _ in range(5):
        result = solve_exact(instance, time_limit_seconds=10)
        assert result.optimal
        ok, violations = check_feasible(instance, result.tasks)
        assert ok, violations
        r = evaluate(instance, result.tasks, "exact")
        assert r["total_wait_time"] < 1e-6, f"spurious wait despite optimal makespan: {r['total_wait_time']}"
        makespans.add(round(result.makespan, 6))
    assert len(makespans) == 1, f"optimal makespan should be deterministic across solves, got {makespans}"
