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
        3: Task(bay=3, crane=0, start=1.0, end=11.0, wait=0),     # Fahrzeit von der Startposition 1.0 zu Bay 3 beträgt 1.0
        0: Task(bay=0, crane=1, start=1.5, end=11.5, wait=0),     # von 3.0 zu Bay 0: 1.5
    }
    ok, violations = check_feasible(instance, tasks)
    assert not ok


def test_margin_respected_is_feasible():
    instance = _instance(n_bays=4, n_cranes=2, safety_margin=1)
    # Startpositionen 1.0 und 3.0, Fahrzeit 0.5 je Bay: jede Fahrt zur nächsten Bay braucht 0.5 min
    tasks = {
        0: Task(bay=0, crane=0, start=0.5, end=10.5, wait=0),
        1: Task(bay=1, crane=0, start=11.0, end=21.0, wait=0),
        2: Task(bay=2, crane=1, start=0.5, end=10.5, wait=0),
        3: Task(bay=3, crane=1, start=11.0, end=21.0, wait=0),
    }
    ok, violations = check_feasible(instance, tasks)
    assert ok, violations


def test_margin_violation_when_too_close_and_overlapping():
    instance = _instance(n_bays=4, n_cranes=2, safety_margin=2)
    # Bay 1 (Kran 0) und Bay 2 (Kran 1) liegen nur 1 Bay auseinander, Margin verlangt 2 - bei
    # zeitlicher Überlappung ist das eine Verletzung.
    tasks = {
        0: Task(bay=0, crane=0, start=0.5, end=5.5, wait=0),
        1: Task(bay=1, crane=0, start=6.0, end=16.0, wait=0),
        2: Task(bay=2, crane=1, start=6.0, end=16.0, wait=0),
        3: Task(bay=3, crane=1, start=16.5, end=26.5, wait=0),
    }
    ok, violations = check_feasible(instance, tasks)
    assert not ok
    assert all("Fahrzeit" not in v for v in violations)       # nur der Sicherheitsabstand ist verletzt, die Fahrzeiten stimmen


def test_detects_a_crane_that_is_faster_than_its_travel_time():
    # Regression (Orakel-Prüfung): der Prüfer ließ Zeitpläne zu, in denen ein Kran ohne Fahrzeit zwischen den Bays springt (ein Kran, vier Bays, keine Rüstzeit)
    instance = _instance(n_bays=4, n_cranes=1)
    end, tasks = 0.0, {}
    for i, b in enumerate(instance.bays):
        tasks[i] = Task(bay=i, crane=0, start=end, end=end + b.duration, wait=0)
        end += b.duration
    ok, violations = check_feasible(instance, tasks)
    assert not ok and any("Fahrzeit" in v for v in violations)
    # mit genau der Fahrzeit (auch von der Startposition zur ersten Bay) ist derselbe Plan zulässig
    pos, end, tasks = instance.crane_start_positions[0], 0.0, {}
    for i, b in enumerate(instance.bays):
        start = end + instance.travel_time(pos, i)
        tasks[i] = Task(bay=i, crane=0, start=start, end=start + b.duration, wait=0)
        pos, end = i, start + b.duration
    assert check_feasible(instance, tasks) == (True, [])
