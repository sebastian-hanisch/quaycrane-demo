"""Exakter Referenzlöser (Google OR-Tools CP-SAT) für das Quay-Crane-Scheduling-Problem.

Modell: jede Bay wird genau einem Kran zugewiesen (x[i][c]) und bekommt Start-/Endzeit
(start[i]/end[i], Dauer fix). Zwei Arten paarweiser Constraints zwischen je zwei Bays i<j
(Bay-Index == Position auf der Schiffsseite):

- Gleicher Kran: die beiden Aufgaben dürfen sich zeitlich nicht überlappen und brauchen
  zusätzlich die Fahrzeit zwischen den Bays als Rüstzeit dazwischen (Sequencing mit
  sequenzabhängigen Rüstzeiten, klassisch über Reihenfolge-Bools "i vor j" / "j vor i").
- Unterschiedliche Kräne: Non-Crossing (Kim & Park 2004). Da die Kranreihenfolge auf der
  Schiene fix ist (Kranindex == physische Position), unterscheiden wir zwei Fälle: die
  Zuordnung ist "konsistent" (linkere Bay bekommt einen Kran mit kleinerem oder gleichem
  Index) - dann reicht bei zeitlicher Übrschneidung schon der Sicherheitsabstand in Bays;
  oder "gekreuzt" (linkere Bay bekommt den Kran mit dem größeren Index) - das ist eine
  physische Unmöglichkeit und wird bei zeitlicher Überschneidung komplett verboten.

Minimiert wird primär der Makespan (= Schiffsliegezeit); als lexikografisches
Tie-Breaking-Ziel zusätzlich die Summe aller Endzeiten. Ohne dieses zweite Ziel ist dem Solver
unter mehreren gleich-optimalen Makespan-Lösungen jede davon gleich lieb - er kann (und tut es
in der Praxis, je nachdem welcher der parallelen Suchpfade zuerst eine optimale Lösung findet)
eine mit unnötiger Wartezeit auf einem unkritischen Kran zurückgeben, obwohl eine
wartezeitfreie Lösung mit demselben Makespan existiert. Das zweite Ziel drückt jede Aufgabe so
früh wie möglich, ohne den Makespan zu verschlechtern, und eliminiert solche Artefakte."""

import time
from dataclasses import dataclass

from ortools.sat.python import cp_model

from quaycrane_evaluation import finalize_tasks

SCALE = 10  # interne Zeitauflösung: 1 CP-SAT-Einheit = 0.1 Minuten


@dataclass
class ExactResult:
    feasible: bool
    optimal: bool
    tasks: dict
    makespan: float
    wall_time_ms: float


def solve_exact(instance, time_limit_seconds=8):
    t0 = time.perf_counter()
    n, k = instance.n_bays, instance.n_cranes
    model = cp_model.CpModel()

    def scaled(x):
        return round(x * SCALE)

    durations = [scaled(b.duration) for b in instance.bays]
    total_work = sum(durations)
    max_travel = scaled(instance.travel_time_per_bay) * max(1, n)
    horizon = total_work + n * max_travel + 1

    x = {(i, c): model.NewBoolVar(f"x_{i}_{c}") for i in range(n) for c in range(k)}
    for i in range(n):
        model.AddExactlyOne(x[i, c] for c in range(k))

    crane_of = [model.NewIntVar(0, k - 1, f"crane_of_{i}") for i in range(n)]
    for i in range(n):
        model.Add(crane_of[i] == sum(c * x[i, c] for c in range(k)))

    start = [model.NewIntVar(0, horizon, f"start_{i}") for i in range(n)]
    end = [model.NewIntVar(0, horizon, f"end_{i}") for i in range(n)]
    for i in range(n):
        model.Add(end[i] == start[i] + durations[i])
        for c in range(k):
            travel0 = scaled(instance.travel_time(instance.crane_start_positions[c], i))
            model.Add(start[i] >= travel0).OnlyEnforceIf(x[i, c])

    for i in range(n):
        for j in range(i + 1, n):
            i_before_j = model.NewBoolVar(f"ibj_{i}_{j}")
            j_before_i = model.NewBoolVar(f"jbi_{i}_{j}")
            model.Add(end[i] <= start[j]).OnlyEnforceIf(i_before_j)
            model.Add(end[i] > start[j]).OnlyEnforceIf(i_before_j.Not())
            model.Add(end[j] <= start[i]).OnlyEnforceIf(j_before_i)
            model.Add(end[j] > start[i]).OnlyEnforceIf(j_before_i.Not())
            model.Add(i_before_j + j_before_i <= 1)

            same = model.NewBoolVar(f"same_{i}_{j}")
            model.Add(crane_of[i] == crane_of[j]).OnlyEnforceIf(same)
            model.Add(crane_of[i] != crane_of[j]).OnlyEnforceIf(same.Not())

            travel_ij = scaled(instance.travel_time(i, j))
            model.AddBoolOr([i_before_j, j_before_i]).OnlyEnforceIf(same)
            model.Add(end[i] + travel_ij <= start[j]).OnlyEnforceIf([same, i_before_j])
            model.Add(end[j] + travel_ij <= start[i]).OnlyEnforceIf([same, j_before_i])

            if k > 1:
                crossed = model.NewBoolVar(f"crossed_{i}_{j}")
                model.Add(crane_of[i] > crane_of[j]).OnlyEnforceIf(crossed)
                model.Add(crane_of[i] <= crane_of[j]).OnlyEnforceIf(crossed.Not())

                model.AddBoolOr([i_before_j, j_before_i]).OnlyEnforceIf([same.Not(), crossed])

                margin_ok = (i + instance.safety_margin) <= j
                if not margin_ok:
                    model.AddBoolOr([i_before_j, j_before_i]).OnlyEnforceIf([same.Not(), crossed.Not()])

    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, end)

    # Lexikografisches Tie-Breaking: unter allen Lösungen mit optimalem Makespan die mit der
    # kleinsten Summe aller Endzeiten waehlen (siehe Docstring oben). tie_break_weight ist eine
    # sichere obere Schranke fuer die Summe aller Endzeiten (jede einzelne <= horizon, n Aufgaben)
    # plus 1 - so kostet ein einziger Zeitschritt mehr Makespan garantiert mehr, als das
    # Tie-Breaking-Ziel je einsparen koennte, ändert also nie die primäre Optimallösung.
    tie_break_weight = n * horizon + 1
    model.Minimize(makespan * tie_break_weight + sum(end))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    wall_time_ms = (time.perf_counter() - t0) * 1000

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ExactResult(feasible=False, optimal=False, tasks={}, makespan=0.0, wall_time_ms=wall_time_ms)

    raw = {}
    for i in range(n):
        c = next(c for c in range(k) if solver.Value(x[i, c]))
        raw[i] = (c, solver.Value(start[i]) / SCALE, solver.Value(end[i]) / SCALE)
    tasks = finalize_tasks(instance, raw)

    return ExactResult(
        feasible=True,
        optimal=status == cp_model.OPTIMAL,
        tasks=tasks,
        makespan=solver.Value(makespan) / SCALE,
        wall_time_ms=wall_time_ms,
    )
