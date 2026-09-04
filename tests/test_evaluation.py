from quaycrane_evaluation import Task, check_feasible
from quaycrane_scenario import generate_instance


def _instance(n_bays=6, n_cranes=2, safety_margin=1):
    return generate_instance(
        n_bays=n_bays,
        n_cranes=n_cranes,
        moves_avg=10,
        moves_variability=0.3,
        time_per_move=2.0,
        travel_time_per_bay=0.5,
        safety_margin=safety_margin,
        seed=1,
    )


def test_detects_missing_bay():
    instance = _instance(n_bays=3, n_cranes=1)
    tasks = {
        0: Task(bay=0, crane=0, start=0, end=10, wait=0),
        1: Task(bay=1, crane=0, start=10, end=20, wait=0),
    }
    ok, violations = check_feasible(instance, tasks)
    assert not ok
    assert violations


def test_detects_same_crane_overlap():
    instance = _instance(n_bays=2, n_cranes=1)
    tasks = {
        0: Task(bay=0, crane=0, start=0, end=10, wait=0),
        1: Task(bay=1, crane=0, start=5, end=15, wait=0),
    }
    ok, violations = check_feasible(instance, tasks)
    assert not ok


def test_detects_non_crossing_violation():
    instance = _instance(n_bays=4, n_cranes=2, safety_margin=1)
    # Kran 0 (links) arbeitet an Bay 3, Kran 1 (rechts) an Bay 0 - zur gleichen Zeit: physisch
    # unmöglich, muss als Verletzung erkannt werden.
    tasks = {
        3: Task(bay=3, crane=0, start=0, end=10, wait=0),
        0: Task(bay=0, crane=1, start=0, end=10, wait=0),
    }
    ok, violations = check_feasible(instance, tasks)
    assert not ok


def test_margin_respected_is_feasible():
    instance = _instance(n_bays=4, n_cranes=2, safety_margin=1)
    tasks = {
        0: Task(bay=0, crane=0, start=0, end=10, wait=0),
        1: Task(bay=1, crane=0, start=10, end=20, wait=0),
        2: Task(bay=2, crane=1, start=0, end=10, wait=0),
        3: Task(bay=3, crane=1, start=10, end=20, wait=0),
    }
    ok, violations = check_feasible(instance, tasks)
    assert ok, violations


def test_margin_violation_when_too_close_and_overlapping():
    instance = _instance(n_bays=4, n_cranes=2, safety_margin=2)
    # Bay 1 (Kran 0) und Bay 2 (Kran 1) liegen nur 1 Bay auseinander, Margin verlangt 2 - bei
    # zeitlicher Überlappung ist das eine Verletzung.
    tasks = {
        0: Task(bay=0, crane=0, start=0, end=5, wait=0),
        1: Task(bay=1, crane=0, start=5, end=15, wait=0),
        2: Task(bay=2, crane=1, start=5, end=15, wait=0),
        3: Task(bay=3, crane=1, start=15, end=25, wait=0),
    }
    ok, violations = check_feasible(instance, tasks)
    assert not ok
