import pytest

from quaycrane_cp_solver import solve_exact
from quaycrane_evaluation import build_schedule, check_feasible
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
