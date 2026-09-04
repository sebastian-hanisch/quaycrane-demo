import pytest

from quaycrane_cp_solver import solve_exact
from quaycrane_evaluation import build_schedule, check_feasible, evaluate
from quaycrane_heuristic import balanced_zone_construction, greedy_and_polish, naive_construction
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
        # Toleranz statt 1e-6: `quaycrane_cp_solver.scaled()` rundet Zeiten bewusst AUF (nicht
        # zum naechsten Wert) - vermeidet, dass das skalierte Modell eine Fahrzeit/Dauer je
        # knapp zu kurz annimmt und dadurch eine "optimale" Loesung meldet, die nach dem
        # Zurueckskalieren die (strengere) stetige check_feasible-Pruefung verfehlt (siehe
        # scaled()-Docstring). Preis dafuer: das gemeldete Optimum kann um bis zu einer
        # SCALE-Einheit (0.1 min) pessimistischer sein als das wahre stetige Optimum, das eine
        # Heuristik zufaellig treffen kann - Sicherheit vor Zulaessigkeit geht hier bewusst vor
        # Millisekunden-genauer Optimalitaet.
        assert result.makespan <= heuristic_makespan + 0.15


def test_exact_solution_has_no_spurious_wait():
    """CP-SAT's parallel search can land on any one of several equally optimal-makespan
    solutions; without a tie-breaking secondary objective, nothing in the model prefers the
    ones without gratuitous idling on a non-critical crane over ones with it (a user reported
    exactly this: the "Mittleres Schiff" preset sometimes showed the exact solver waiting at
    the start even though the cranes looked far apart on the chart - reproduced by solving the
    same instance repeatedly and finding the reported wait time varied between 0.0 and 1.1
    minutes while the makespan stayed the same optimal value every time). Regression test for
    the fix: solve several times, the makespan must stay optimal and the wait time must stay
    at (numerically) zero every time.

    Time limit generous (not the usual few seconds): CI runners have far fewer cores than a
    typical dev machine, and CP-SAT's parallel search needs real wall-clock time per worker to
    close the optimality gap, not just to find a good solution (own finding: this instance
    reliably proves optimal in ~14s with 2 search workers, matching a 2-vCPU CI runner - see
    `NUM_SEARCH_WORKERS` in quaycrane_cp_solver.py)."""
    instance = generate_instance(
        n_bays=12, n_cranes=3, moves_avg=14, moves_variability=0.4, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=1, seed=7,
    )
    makespans = set()
    for _ in range(5):
        result = solve_exact(instance, time_limit_seconds=25)
        assert result.optimal
        ok, violations = check_feasible(instance, result.tasks)
        assert ok, violations
        r = evaluate(instance, result.tasks, "exact")
        assert r["total_wait_time"] < 1e-6, f"spurious wait despite optimal makespan: {r['total_wait_time']}"
        makespans.add(round(result.makespan, 6))
    assert len(makespans) == 1, f"optimal makespan should be deterministic across solves, got {makespans}"


def test_exact_solution_never_crosses_during_travel():
    """User-reported: the trajectory chart is supposed to show crane lines that never cross
    (that's the whole non-crossing story), but the exact solver could return a schedule where
    one crane's TRAVEL between two of its own tasks passes straight through the bay another
    crane is still processing - the original non-crossing constraints only compared task
    PROCESSING intervals against each other, never a crane's travel path in between. Reproduced
    on the "Mittleres Schiff" preset: crane 0 finished bay 3 at t=77.5, crane 1 traveled from
    bay 4 to bay 2 during [77.0, 78.0] - passing directly through bay 3's position (3.0) at
    t=77.5, the exact moment crane 0 was still standing there. Regression test for the fix
    (_add_travel_non_crossing_constraints in quaycrane_cp_solver.py): check_feasible's
    segment-based crossing check (which itself models travel, not just task intervals) must
    pass on the exact preset parameters that exposed the bug. Time limit generous for the same
    CI-hardware reason as `test_exact_solution_has_no_spurious_wait` above."""
    instance = generate_instance(
        n_bays=12, n_cranes=3, moves_avg=14, moves_variability=0.4, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=1, seed=7,
    )
    for _ in range(3):
        result = solve_exact(instance, time_limit_seconds=25)
        assert result.optimal
        ok, violations = check_feasible(instance, result.tasks)
        assert ok, violations


def test_exact_solution_covers_first_travel_from_start_position():
    """Follow-up to the travel-crossing fix above: a crane's VERY FIRST trip (from its fixed
    start position on the rail to its first assigned bay) has no preceding task and was missed
    by the first pass of the fix, which only linked immediately-consecutive TASK pairs.
    Reproduced on the "Großes Schiff, viele Kräne" preset (20 bays, 5 cranes): crane 3's first
    trip (start position 14.0 -> bay 5) crossed crane 2's first trip (start position 10.0 ->
    bay 13) during their overlapping initial travel windows. Time limit generous for the same
    CI-hardware reason as the tests above (this one only needs `feasible`, not `optimal`, but
    even reaching feasibility takes longer with fewer real search workers)."""
    instance = generate_instance(
        n_bays=20, n_cranes=5, moves_avg=16, moves_variability=0.4, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=1, seed=11,
    )
    hint = build_schedule(instance, greedy_and_polish(instance, seed=11))
    result = solve_exact(instance, time_limit_seconds=25, hint_tasks=hint)
    assert result.feasible
    ok, violations = check_feasible(instance, result.tasks)
    assert ok, violations


def test_heuristics_stay_feasible_at_extreme_settings():
    """Regression test for a since-fixed limitation: at this exact scenario (maximum safety
    margin, 5 cranes, an 18-bay ship, seed=5) the heuristics' construction used to produce a
    genuine margin violation during a very long forced wait - an earlier "wait at last known
    position" idle convention couldn't guarantee safety there. Fixed by making `build_schedule`
    construct every task via an exhaustive, per-insertion VERIFIED breakpoint search (see
    `_safe_breakpoint_departure`'s docstring in quaycrane_evaluation.py) instead of trusting a
    single "safe" formula plus a separate fallback for when that formula turned out wrong. All
    three heuristics must now be feasible here too, matching the exact solver (see
    `test_exact_solution_never_crosses_during_travel` and friends above)."""
    instance = generate_instance(
        n_bays=18, n_cranes=5, moves_avg=12, moves_variability=0.4, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=3, seed=5,
    )
    for order in [naive_construction(instance), balanced_zone_construction(instance), greedy_and_polish(instance)]:
        tasks = build_schedule(instance, order)
        ok, violations = check_feasible(instance, tasks)
        assert ok, violations
